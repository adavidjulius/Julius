"""pytest configuration and module alias setup for tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Map src.arch_discovery to arch_discovery for direct module imports in test suite
try:
    import src.arch_discovery as _arch_discovery
    import src.arch_discovery.tokenizer.char_tokenizer as _char_tok
    import src.arch_discovery.architectures.building_blocks as _bblocks
    import src.arch_discovery.architectures.novel as _novel
    import src.arch_discovery.architectures.registry as _registry
    import src.arch_discovery.architectures.generator as _generator
    import src.arch_discovery.evaluation.evaluator as _evaluator
    import src.arch_discovery.training.trainer as _trainer

    sys.modules["arch_discovery"] = _arch_discovery
    sys.modules["arch_discovery.tokenizer"] = _arch_discovery.tokenizer
    sys.modules["arch_discovery.tokenizer.char_tokenizer"] = _char_tok
    sys.modules["arch_discovery.architectures"] = _arch_discovery.architectures
    sys.modules["arch_discovery.architectures.building_blocks"] = _bblocks
    sys.modules["arch_discovery.architectures.novel"] = _novel
    sys.modules["arch_discovery.architectures.registry"] = _registry
    sys.modules["arch_discovery.architectures.generator"] = _generator
    sys.modules["arch_discovery.evaluation"] = _arch_discovery.evaluation
    sys.modules["arch_discovery.evaluation.evaluator"] = _evaluator
    sys.modules["arch_discovery.training"] = _arch_discovery.training
    sys.modules["arch_discovery.training.trainer"] = _trainer
except Exception as exc:
    pass
