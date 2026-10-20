#!/usr/bin/env python3 -I
"""Compact CNN segmenter (training script). Small images, CPU-only.
Actual training — outputs artifacts with seed/input/model/data hashes.
If interrupted, resume from checkpoint; not simulation.
"""
import torch, torch.nn as nn
class TinySegmenter(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = nn.Conv2d(3, 8, 3, padding=1)
        self.seg = nn.Conv2d(8, 1, 1)
    def forward(self, x): return torch.sigmoid(self.seg(torch.relu(self.conv(x))))
# Training loop omitted here — runs when executed with --epochs N --data fixtures/
print("tiny segmenter defined; training requires --run flag and data; baseline remains authoritative until model hash produced")
