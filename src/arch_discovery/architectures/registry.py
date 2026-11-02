"""Architecture registry and history tracker for arch_discovery."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type


class ArchitectureRegistry:
    """Registry for discovering, building, and tracking neural architecture experiments."""

    def __init__(self) -> None:
        self._registry: Dict[str, Type] = {}
        self._descriptions: Dict[str, str] = {}
        self._tags: Dict[str, List[str]] = {}
        self._history: List[Dict[str, Any]] = []

    def register(self, model_cls: Type, description: str = "", tags: Optional[List[str]] = None) -> None:
        name = getattr(model_cls, "__name__", str(model_cls))
        self._registry[name] = model_cls
        self._descriptions[name] = description
        self._tags[name] = tags or []

    def build(self, name: str, **kwargs) -> Any:
        if name not in self._registry:
            raise ValueError(f"Architecture '{name}' not found in registry.")
        cls = self._registry[name]
        instance = cls(**kwargs)
        setattr(instance, "name", name)
        return instance

    def list_architectures(self) -> Dict[str, Type]:
        return dict(self._registry)

    def record_result(self, name: str, metrics: Dict[str, Any]) -> None:
        entry = {"architecture": name, **metrics}
        self._history.append(entry)

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def best_so_far(self, metric: str = "train_loss") -> Optional[Dict[str, Any]]:
        if not self._history:
            return None

        if metric == "composite_score":
            return max(self._history, key=lambda x: x.get("composite_score", 0.0))

        # Default: pick entry with minimum loss or highest composite score
        valid_entries = [e for e in self._history if metric in e or "train_loss" in e or "val_loss" in e or "composite_score" in e]
        if not valid_entries:
            return self._history[-1]

        return min(valid_entries, key=lambda x: x.get("train_loss", x.get("val_loss", 999.0)))
