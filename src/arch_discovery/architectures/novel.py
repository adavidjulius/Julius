"""Novel neural network architectures for arch_discovery."""

from __future__ import annotations

import torch
import torch.nn as nn
from .building_blocks import HybridFusionBlock, SSMBlock, MultiHeadSelfAttention, DifferentiableRouter


class BaseNovelNet(nn.Module):
    def __init__(self, name: str, vocab_size: int, d_model: int) -> None:
        super().__init__()
        self.name = name
        self.vocab_size = vocab_size
        self.d_model = d_model
        self.emb = nn.Embedding(vocab_size, d_model)
        self.head = nn.Linear(d_model, vocab_size)

    def parameter_count(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class HybridFusionNet(BaseNovelNet):
    def __init__(self, vocab_size: int = 128, d_model: int = 256, n_layers: int = 2, n_heads: int = 8) -> None:
        super().__init__("HybridFusionNet", vocab_size, d_model)
        self.layers = nn.ModuleList([
            HybridFusionBlock(d_model, n_heads) for _ in range(n_layers)
        ])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.emb(x)
        for layer in self.layers:
            h, _ = layer(h)
        return self.head(h)


class RoutedNet(BaseNovelNet):
    def __init__(self, vocab_size: int = 128, d_model: int = 256, n_layers: int = 2) -> None:
        super().__init__("RoutedNet", vocab_size, d_model)
        self.attn_branches = nn.ModuleList([MultiHeadSelfAttention(d_model) for _ in range(n_layers)])
        self.ssm_branches = nn.ModuleList([SSMBlock(d_model) for _ in range(n_layers)])
        self.routers = nn.ModuleList([DifferentiableRouter(d_model, n_paths=2) for _ in range(n_layers)])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.emb(x)
        for attn, ssm, router in zip(self.attn_branches, self.ssm_branches, self.routers):
            p1 = attn(h)
            p2 = ssm(h)
            h, _ = router(h, [p1, p2])
        return self.head(h)


class ParallelMemoryNet(BaseNovelNet):
    def __init__(self, vocab_size: int = 128, d_model: int = 256, n_layers: int = 2, memory_slots: int = 32) -> None:
        super().__init__("ParallelMemoryNet", vocab_size, d_model)
        self.memory = nn.Parameter(torch.randn(1, memory_slots, d_model))
        self.layers = nn.ModuleList([MultiHeadSelfAttention(d_model) for _ in range(n_layers)])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, T = x.shape
        h = self.emb(x)
        mem = self.memory.expand(B, -1, -1)
        h = h + mem[:, :T, :] if T <= mem.size(1) else h
        for layer in self.layers:
            h = layer(h)
        return self.head(h)


def register_novel_architectures(registry: any) -> None:
    registry.register(HybridFusionNet, description="Hybrid fusion net", tags=["hybrid"])
    registry.register(RoutedNet, description="Differentiable routed net", tags=["routed"])
    registry.register(ParallelMemoryNet, description="Parallel memory net", tags=["memory"])
