"""Trainer for arch_discovery neural architecture search."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import torch
import torch.nn as nn
import torch.optim as optim


class Trainer:
    """Trainer executing training steps, loss logging, and checkpointing for arch_discovery models."""

    def __init__(
        self,
        model: nn.Module,
        tokenizer: Any,
        train_data: torch.Tensor,
        val_data: Optional[torch.Tensor] = None,
        lr: float = 1e-3,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.train_data = train_data
        self.val_data = val_data
        self.optimizer = optim.AdamW(self.model.parameters(), lr=lr)
        self.criterion = nn.CrossEntropyLoss()

        self.train_losses: List[float] = []
        self.val_losses: List[tuple[int, float]] = []

    def train(self, steps: int = 10) -> Dict[str, Any]:
        self.model.train()
        n_samples = len(self.train_data)

        for step in range(1, steps + 1):
            batch = self.train_data[(step - 1) % n_samples]
            if batch.ndim == 1:
                batch = batch.unsqueeze(0)

            x = batch[:, :-1]
            y = batch[:, 1:]

            self.optimizer.zero_grad()
            out = self.model(x)

            if isinstance(out, tuple):
                logits = out[0]
            else:
                logits = out

            loss = self.criterion(logits.reshape(-1, logits.size(-1)), y.reshape(-1))
            loss.backward()
            self.optimizer.step()

            loss_val = float(loss.item())
            self.train_losses.append(loss_val)

            if self.val_data is not None and step % max(1, steps // 4) == 0:
                val_loss = self._evaluate_val()
                self.val_losses.append((step, val_loss))

        param_count = getattr(self.model, "parameter_count", lambda: sum(p.numel() for p in self.model.parameters()))()
        return {
            "architecture_name": getattr(self.model, "name", "Model"),
            "train_losses": self.train_losses,
            "val_losses": self.val_losses,
            "parameter_count": param_count,
        }

    def _evaluate_val(self) -> float:
        if self.val_data is None:
            return 0.0
        self.model.eval()
        total_loss = 0.0
        count = 0
        with torch.no_grad():
            for i in range(min(5, len(self.val_data))):
                batch = self.val_data[i]
                if batch.ndim == 1:
                    batch = batch.unsqueeze(0)
                x = batch[:, :-1]
                y = batch[:, 1:]
                out = self.model(x)
                logits = out[0] if isinstance(out, tuple) else out
                loss = self.criterion(logits.reshape(-1, logits.size(-1)), y.reshape(-1))
                total_loss += float(loss.item())
                count += 1
        self.model.train()
        return total_loss / max(1, count)

    def save_checkpoint(self, path: Union[str, Path]) -> None:
        p = Path(path)
        data = {
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "train_losses": self.train_losses,
            "val_losses": self.val_losses,
        }
        torch.save(data, str(p))

    def load_checkpoint(self, path: Union[str, Path]) -> None:
        p = Path(path)
        data = torch.load(str(p))
        self.model.load_state_dict(data["model_state_dict"])
        self.optimizer.load_state_dict(data["optimizer_state_dict"])
        self.train_losses = data.get("train_losses", [])
        self.val_losses = data.get("val_losses", [])
