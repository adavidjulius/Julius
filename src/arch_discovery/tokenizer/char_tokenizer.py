"""Character-level tokenizer for arch_discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Union
import torch


class CharTokenizer:
    """Character tokenizer supporting special tokens and sliding windows."""

    def __init__(self) -> None:
        self.pad_id = 0
        self.bos_id = 1
        self.eos_id = 2
        self.unk_id = 3

        self._special_tokens = ["<pad>", "<bos>", "<eos>", "<unk>"]
        self.char2id = {tok: i for i, tok in enumerate(self._special_tokens)}
        self.id2char = {i: tok for i, tok in enumerate(self._special_tokens)}

    @property
    def vocab_size(self) -> int:
        return len(self.id2char)

    def build_vocab(self, texts: List[str]) -> None:
        chars = sorted(list(set("".join(texts))))
        for c in chars:
            if c not in self.char2id:
                new_id = len(self.char2id)
                self.char2id[c] = new_id
                self.id2char[new_id] = c

    def encode(
        self,
        text: str,
        add_bos: bool = False,
        add_eos: bool = False,
        max_length: Union[int, None] = None,
    ) -> List[int]:
        ids = []
        if add_bos:
            ids.append(self.bos_id)

        for c in text:
            ids.append(self.char2id.get(c, self.unk_id))

        if add_eos:
            ids.append(self.eos_id)

        if max_length is not None:
            if len(ids) > max_length:
                ids = ids[:max_length]
            else:
                ids += [self.pad_id] * (max_length - len(ids))

        return ids

    def decode(self, ids: Union[List[int], torch.Tensor], skip_special: bool = True) -> str:
        if isinstance(ids, torch.Tensor):
            ids = ids.tolist()

        res = []
        for i in ids:
            if skip_special and i in (self.pad_id, self.bos_id, self.eos_id, self.unk_id):
                continue
            res.append(self.id2char.get(i, ""))
        return "".join(res)

    def sliding_windows(self, text: str, window_size: int = 16, stride: int = 8) -> torch.Tensor:
        ids = [self.char2id.get(c, self.unk_id) for c in text]
        if len(ids) < window_size:
            ids += [self.pad_id] * (window_size - len(ids))

        windows = []
        for start in range(0, len(ids) - window_size + 1, stride):
            windows.append(ids[start : start + window_size])

        if not windows:
            windows.append(ids[:window_size])

        return torch.tensor(windows, dtype=torch.long)

    def save(self, path: Union[str, Path]) -> None:
        p = Path(path)
        data = {
            "char2id": self.char2id,
            "id2char": {str(k): v for k, v in self.id2char.items()},
        }
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Union[str, Path]) -> CharTokenizer:
        tok = cls()
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        tok.char2id = data["char2id"]
        tok.id2char = {int(k): v for k, v in data["id2char"].items()}
        return tok
