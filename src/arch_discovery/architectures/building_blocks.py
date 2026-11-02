"""PyTorch building blocks for arch_discovery neural architecture search."""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class MultiHeadSelfAttention(nn.Module):
    def __init__(self, d_model: int = 256, n_heads: int = 8) -> None:
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.attn = nn.MultiheadAttention(embed_dim=d_model, num_heads=n_heads, batch_first=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.attn(x, x, x)
        return out


class SSMBlock(nn.Module):
    def __init__(self, d_model: int = 256, d_state: int = 16) -> None:
        super().__init__()
        self.d_model = d_model
        self.conv = nn.Conv1d(d_model, d_model, kernel_size=3, padding=1)
        self.proj = nn.Linear(d_model, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, T, D)
        y = self.conv(x.transpose(1, 2)).transpose(1, 2)
        return self.proj(F.silu(y))


class MoEBlock(nn.Module):
    def __init__(self, d_model: int = 256, n_experts: int = 4, top_k: int = 2) -> None:
        super().__init__()
        self.d_model = d_model
        self.n_experts = n_experts
        self.top_k = top_k
        self.gate = nn.Linear(d_model, n_experts)
        self.experts = nn.ModuleList([
            nn.Sequential(nn.Linear(d_model, d_model * 2), nn.GELU(), nn.Linear(d_model * 2, d_model))
            for _ in range(n_experts)
        ])

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        B, T, D = x.shape
        logits = self.gate(x)  # (B, T, n_experts)
        weights = F.softmax(logits, dim=-1)
        topk_weights, topk_indices = torch.topk(weights, self.top_k, dim=-1)

        out = torch.zeros_like(x)
        for i in range(self.top_k):
            w = topk_weights[..., i : i + 1]  # (B, T, 1)
            idx = topk_indices[..., i]  # (B, T)
            for exp_idx, expert in enumerate(self.experts):
                mask = (idx == exp_idx).unsqueeze(-1)
                exp_out = expert(x)
                out += w * exp_out * mask.float()

        aux_loss = (weights.mean(dim=(0, 1)) ** 2).sum()
        return out, aux_loss


class RecurrentBlock(nn.Module):
    def __init__(self, d_model: int = 256) -> None:
        super().__init__()
        self.d_model = d_model
        self.gru = nn.GRU(input_size=d_model, hidden_size=d_model, batch_first=True)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        out, h_n = self.gru(x)
        return out, h_n.squeeze(0)


class HybridFusionBlock(nn.Module):
    def __init__(self, d_model: int = 256, n_heads: int = 8) -> None:
        super().__init__()
        self.attn = MultiHeadSelfAttention(d_model, n_heads)
        self.ssm = SSMBlock(d_model)
        self.rec = RecurrentBlock(d_model)
        self.fusion = nn.Linear(d_model * 3, d_model)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        a = self.attn(x)
        s = self.ssm(x)
        r, state = self.rec(x)
        concat = torch.cat([a, s, r], dim=-1)
        out = self.fusion(concat)
        return out, state


class DifferentiableRouter(nn.Module):
    def __init__(self, d_model: int = 256, n_paths: int = 3) -> None:
        super().__init__()
        self.d_model = d_model
        self.n_paths = n_paths
        self.gate = nn.Linear(d_model, n_paths)

    def forward(self, x: torch.Tensor, paths: list[torch.Tensor]) -> tuple[torch.Tensor, torch.Tensor]:
        logits = self.gate(x)  # (B, T, n_paths)
        weights = F.softmax(logits, dim=-1)  # (B, T, n_paths)

        out = torch.zeros_like(x)
        for i, path in enumerate(paths):
            w = weights[..., i : i + 1]  # (B, T, 1)
            out += w * path

        return out, weights
