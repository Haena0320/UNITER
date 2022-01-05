import torch
import torch.nn as F
import torch.cuda.amp as amp
import torch.cuda.amp.autocast_mode

from model.pretrain_vcr import UniterForPretrainingForVCR
from prepro import PretrainDataForVCR, DataLoader, collate
from transformers import AdamW, get_linear_schedule_with_warmup

import json
import numpy as np
import pandas as pd
from tqdm import tqdm

from torch.utils.tensorboard import SummaryWriter

# random seed
torch.random.manual_seed(42)

# config 
batch_size = 128 #6144
val_batch_size = 8000,
num_train_steps = 10 #45000
warmup_steps = 4500
accum_steps = 1
valid_steps = 2000
learning_rate = 3e-05

# dataloader
train_dataset = PretrainDataForVCR(data_type='train')
train_dataloader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, collate_fn=collate,
                              prefetch_factor=5, num_workers=5)
val_dataset = PretrainDataForVCR(data_type='val')
train_dataloader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, collate_fn=collate,
                              prefetch_factor=5, num_workers=5)

# model
checkpoint = torch.load('pretrained/uniter-base.pt')
model = UniterForPretrainingForVCR.from_pretrained('config/uniter-base.json', checkpoint, img_dim=2048, img_label_dim=1601)
model.cuda()
model.train()

param_optimizer = list(model.named_parameters())
no_decay = ['bias', 'LayerNorm.bias', 'LayerNorm.weight']
optimizer_grouped_parameters = [
        {'params': [p for n, p in param_optimizer if not any(nd in n for nd in no_decay)], 'weight_decay': 0.01},
        {'params': [p for n, p in param_optimizer if any(nd in n for nd in no_decay)], 'weight_decay': 0.0}
    ]


# optimizer
optimizer = AdamW(optimizer_grouped_parameters, lr=learning_rate)
scheduler = get_linear_schedule_with_warmup(optimizer, 4500, num_train_steps)
scaler = amp.GradScaler()
loss_sum = 0
accum = 0


current_step = 0

breakValue = False

for epoch in range(100):
        for i, batch in enumerate(tqdm(train_dataloader)):
                task_prob = torch.rand(1)
                if task_prob > 0.66:
                        task = 'mlm'
                elif task_prob > 0.33:
                        task = 'mrc'
                else:
                        task = 'mrfr'

                with amp.autocast():
                        loss = model(batch, task=task, compute_loss=True)
                        loss = loss.mean()

                scaler.scale(loss).backward()

                loss_sum += loss.item()
                accum += 1

                if accum != accum_steps:
                        continue
                
                scaler.step(optimizer)
                scheduler.step()
                scaler.update()
                optimizer.zero_grad()

                accum = 0
                current_step += 1

                if current_step == num_train_steps: 
                        breakValue = True
                        break
        if breakValue:
                break


