"""Architecture generator for arch_discovery."""

from __future__ import annotations

import random
from typing import Any, List, Optional
import torch
import torch.nn as nn
from .building_blocks import MultiHeadSelfAttention, SSMBlock, RecurrentBlock, DifferentiableRouter
from .novel import BaseNovelNet


class GeneratedArchitecture(BaseNovelNet):
    def __init__(
        self,
        vocab_size: int = 128,
        d_model: int = 256,
        block_specs: Optional[List[str]] = None,
        use_router: bool = False,
    ) -> None:
        super().__init__("GeneratedArchitecture", vocab_size, d_model)
        self.block_specs = block_specs or ["attention", "ssm"]
        self.use_router = use_router

        self.blocks = nn.ModuleList()
        for spec in self.block_specs:
            if spec == "attention":
                self.blocks.append(MultiHeadSelfAttention(d_model))
            elif spec == "ssm":
                self.blocks.append(SSMBlock(d_model))
            elif spec == "recurrent":
                self.blocks.append(RecurrentBlock(d_model))

        if self.use_router and len(self.blocks) > 1:
            self.router = DifferentiableRouter(d_model, n_paths=len(self.blocks))
        else:
            self.router = None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.emb(x)
        if self.router is not None:
            paths = []
            for block in self.blocks:
                out = block(h)
                if isinstance(out, tuple):
                    out = out[0]
                paths.append(out)
            h, _ = self.router(h, paths)
        else:
            for block in self.blocks:
                out = block(h)
                if isinstance(out, tuple):
                    out = out[0]
                h = h + out

        return self.head(h)


class ArchitectureGenerator:
    def __init__(self, registry: Any, seed: int = 42) -> None:
        self.registry = registry
        self.rng = random.Random(seed)

    def generate_random(self, n: int = 5, d_model: int = 128, max_params: int = 50_000_000) -> List[str]:
        generated_names = []
        possible_blocks = ["attention", "ssm", "recurrent"]

        for i in range(n):
            name = f"GeneratedArch_{i+1}"
            num_blocks = self.rng.randint(1, 3)
            block_specs = [self.rng.choice(possible_blocks) for _ in range(num_blocks)]
            use_router = self.rng.choice([True, False])

            class _DynamicGeneratedArch(GeneratedArchitecture):
                def __init__(self, vocab_size: int = 128, d_model: int = d_model, **kwargs):
                    super().__init__(vocab_size=vocab_size, d_model=d_model, block_specs=block_specs, use_router=use_router)
                    self.name = name

            _DynamicGeneratedArch.__name__ = name
            self.registry.register(_DynamicGeneratedArch, description=f"Random generated architecture {name}")
            generated_names.append(name)

        return generated_names
