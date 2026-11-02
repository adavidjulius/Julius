"""
Tests for the Architecture Discovery Framework

All tests are CPU-only and use synthetic data — no PDFs or GPU required.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest
torch = pytest.importorskip("torch")

# ── Tokenizer ───────────────────────────────────────────────────────────────


class TestCharTokenizer:
    def test_build_vocab(self):
        from arch_discovery.tokenizer.char_tokenizer import CharTokenizer

        tok = CharTokenizer()
        tok.build_vocab(["hello world", "test"])
        assert tok.vocab_size > 4  # special tokens + chars
        assert tok.pad_id == 0
        assert tok.bos_id == 1
        assert tok.eos_id == 2
        assert tok.unk_id == 3

    def test_encode_decode_roundtrip(self):
        from arch_discovery.tokenizer.char_tokenizer import CharTokenizer

        tok = CharTokenizer()
        tok.build_vocab(["abcdefghijklmnopqrstuvwxyz"])
        text = "hello"
        ids = tok.encode(text, add_bos=True, add_eos=True, max_length=16)
        decoded = tok.decode(ids, skip_special=True)
        assert "hello" in decoded

    def test_sliding_windows(self):
        from arch_discovery.tokenizer.char_tokenizer import CharTokenizer

        tok = CharTokenizer()
        tok.build_vocab(["abcdefghijklmnopqrstuvwxyz "])
        text = "the quick brown fox jumps over the lazy dog"
        windows = tok.sliding_windows(text, window_size=16, stride=8)
        assert windows.dim() == 2
        assert windows.size(1) == 16
        assert windows.size(0) >= 1

    def test_save_load(self):
        from arch_discovery.tokenizer.char_tokenizer import CharTokenizer

        tok = CharTokenizer()
        tok.build_vocab(["test"])
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        try:
            tok.save(path)
            tok2 = CharTokenizer.load(path)
            assert tok2.vocab_size == tok.vocab_size
        finally:
            path.unlink(missing_ok=True)


# ── Building blocks ─────────────────────────────────────────────────────────


class TestBuildingBlocks:
    def test_attention_shape(self):
        from arch_discovery.architectures.building_blocks import MultiHeadSelfAttention

        attn = MultiHeadSelfAttention(d_model=256, n_heads=8)
        x = torch.randn(2, 32, 256)
        out = attn(x)
        assert out.shape == x.shape

    def test_ssm_shape(self):
        from arch_discovery.architectures.building_blocks import SSMBlock

        ssm = SSMBlock(d_model=256)
        x = torch.randn(2, 32, 256)
        out = ssm(x)
        assert out.shape == x.shape

    def test_moe_shape_and_aux_loss(self):
        from arch_discovery.architectures.building_blocks import MoEBlock

        moe = MoEBlock(d_model=256, n_experts=4, top_k=2)
        x = torch.randn(2, 32, 256)
        out, aux_loss = moe(x)
        assert out.shape == x.shape
        assert aux_loss.ndim == 0  # scalar

    def test_recurrent_state(self):
        from arch_discovery.architectures.building_blocks import RecurrentBlock

        rec = RecurrentBlock(d_model=256)
        x = torch.randn(2, 32, 256)
        out, state = rec(x)
        assert out.shape == x.shape
        assert state.shape == (2, 256)

    def test_hybrid_fusion(self):
        from arch_discovery.architectures.building_blocks import HybridFusionBlock

        block = HybridFusionBlock(d_model=256, n_heads=8)
        x = torch.randn(2, 32, 256)
        out, state = block(x)
        assert out.shape == x.shape

    def test_differentiable_router(self):
        from arch_discovery.architectures.building_blocks import DifferentiableRouter

        router = DifferentiableRouter(d_model=256, n_paths=3)
        x = torch.randn(2, 32, 256)
        paths = [torch.randn(2, 32, 256) for _ in range(3)]
        out, weights = router(x, paths)
        assert out.shape == x.shape
        assert weights.shape == (2, 32, 3)
        # Weights should sum to ~1 per token
        assert torch.allclose(weights.sum(dim=-1), torch.ones(2, 32), atol=1e-5)


# ── Novel architectures ─────────────────────────────────────────────────────


class TestNovelArchitectures:
    def test_hybrid_fusion_net_forward(self):
        from arch_discovery.architectures.novel import HybridFusionNet

        model = HybridFusionNet(vocab_size=128, d_model=256, n_layers=2)
        x = torch.randint(0, 128, (2, 32))
        logits = model(x)
        assert logits.shape == (2, 32, 128)

    def test_routed_net_forward(self):
        from arch_discovery.architectures.novel import RoutedNet

        model = RoutedNet(vocab_size=128, d_model=256, n_layers=2)
        x = torch.randint(0, 128, (2, 32))
        logits = model(x)
        assert logits.shape == (2, 32, 128)

    def test_parallel_memory_net_forward(self):
        from arch_discovery.architectures.novel import ParallelMemoryNet

        model = ParallelMemoryNet(
            vocab_size=128, d_model=256, n_layers=2, memory_slots=32
        )
        x = torch.randint(0, 128, (2, 32))
        logits = model(x)
        assert logits.shape == (2, 32, 128)

    def test_all_under_param_budget(self):
        from arch_discovery.architectures.novel import (
            HybridFusionNet,
            RoutedNet,
            ParallelMemoryNet,
        )

        for cls in [HybridFusionNet, RoutedNet, ParallelMemoryNet]:
            model = cls(vocab_size=256, d_model=256, n_layers=4)
            n = model.parameter_count()
            assert n <= 10_000_000, f"{cls.__name__} has {n} params (limit 10M)"


# ── Registry ────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_register_and_build(self):
        from arch_discovery.architectures.registry import ArchitectureRegistry
        from arch_discovery.architectures.novel import HybridFusionNet

        reg = ArchitectureRegistry()
        reg.register(HybridFusionNet, description="Test", tags=["hybrid"])
        model = reg.build("HybridFusionNet", vocab_size=128, d_model=256, n_layers=2)
        assert model.name == "HybridFusionNet"

    def test_record_and_history(self):
        from arch_discovery.architectures.registry import ArchitectureRegistry

        reg = ArchitectureRegistry()
        reg.record_result("TestNet", {"train_loss": 0.5, "composite_score": 0.8})
        reg.record_result("TestNet2", {"train_loss": 0.3, "composite_score": 0.5})

        history = reg.get_history()
        assert len(history) == 2

        best = reg.best_so_far()
        assert best["architecture"] == "TestNet2"


# ── Generator ───────────────────────────────────────────────────────────────


class TestGenerator:
    def test_generate_random(self):
        from arch_discovery.architectures.registry import ArchitectureRegistry
        from arch_discovery.architectures.generator import ArchitectureGenerator

        reg = ArchitectureRegistry()
        gen = ArchitectureGenerator(reg, seed=42)
        names = gen.generate_random(n=5, d_model=128, max_params=50_000_000)
        assert len(names) == 5
        for name in names:
            model = reg.build(name, vocab_size=256, d_model=128, n_layers=2)
            assert model.parameter_count() <= 50_000_000

    def test_generated_architecture_forward(self):
        from arch_discovery.architectures.generator import GeneratedArchitecture

        model = GeneratedArchitecture(
            vocab_size=128,
            d_model=256,
            block_specs=["attention", "ssm", "recurrent"],
            use_router=True,
        )
        x = torch.randint(0, 128, (2, 32))
        logits = model(x)
        assert logits.shape == (2, 32, 128)


# ── Evaluator ───────────────────────────────────────────────────────────────


class TestEvaluator:
    def test_all_metrics_computed(self):
        from arch_discovery.architectures.novel import HybridFusionNet
        from arch_discovery.evaluation.evaluator import Evaluator
        from arch_discovery.tokenizer.char_tokenizer import CharTokenizer

        tok = CharTokenizer()
        tok.build_vocab(["test text"])

        model = HybridFusionNet(vocab_size=tok.vocab_size, d_model=128, n_layers=2)
        evaluator = Evaluator(model, tok)

        # Simulate a training log
        train_losses = [5.0] + [4.0] * 20 + [3.0] * 40 + [2.0] * 60 + [1.5] * 80
        training_log = {
            "architecture_name": "TestNet",
            "train_losses": train_losses,
            "val_losses": [(50, 2.5), (100, 2.0), (150, 1.8), (200, 1.7)],
        }

        val_windows = torch.randint(
            0, tok.vocab_size, (4, 128)
        )

        metrics = evaluator.evaluate(training_log, val_windows)

        assert metrics.train_loss > 0
        assert metrics.val_loss > 0
        assert metrics.convergence_speed_steps > 0
        assert metrics.training_stability_std >= 0
        assert metrics.parameter_count > 0
        assert metrics.composite_score > 0

    def test_convergence_speed(self):
        from arch_discovery.evaluation.evaluator import Evaluator

        losses = [10.0] * 10 + [5.0] * 20 + [1.0] * 30 + [0.5] * 40
        steps = Evaluator._convergence_speed(losses)
        assert 0 < steps <= len(losses)

    def test_training_stability(self):
        from arch_discovery.evaluation.evaluator import Evaluator

        # Stable tail
        stable = [5.0, 4.0, 3.0, 2.0, 1.9, 1.8, 1.8, 1.7]
        std_stable = Evaluator._training_stability(stable)
        # Noisy tail
        noisy = [5.0, 4.0, 3.0, 2.0, 0.5, 3.5, 0.8, 4.0]
        std_noisy = Evaluator._training_stability(noisy)
        assert std_noisy > std_stable


# ── Training smoke test ─────────────────────────────────────────────────────


class TestTrainingSmoke:
    def test_train_one_step(self):
        from arch_discovery.architectures.novel import HybridFusionNet
        from arch_discovery.tokenizer.char_tokenizer import CharTokenizer
        from arch_discovery.training.trainer import Trainer

        tok = CharTokenizer()
        tok.build_vocab(["hello world this is a test corpus for training"])

        # Create small synthetic dataset
        text = "hello world this is a test corpus for training " * 50
        windows = tok.sliding_windows(text, window_size=64, stride=32)

        model = HybridFusionNet(
            vocab_size=tok.vocab_size, d_model=64, n_layers=2, n_heads=4
        )

        trainer = Trainer(model, tok, windows, val_data=windows[:16])
        log = trainer.train(steps=10)

        assert "train_losses" in log
        assert len(log["train_losses"]) == 10
        assert log["train_losses"][-1] < 20.0  # should decrease from initial
        assert log["parameter_count"] > 0

    def test_checkpoint_save_load(self):
        from arch_discovery.architectures.novel import HybridFusionNet
        from arch_discovery.tokenizer.char_tokenizer import CharTokenizer
        from arch_discovery.training.trainer import Trainer
        import tempfile

        tok = CharTokenizer()
        tok.build_vocab(["test"])

        text = "test " * 100
        windows = tok.sliding_windows(text, window_size=32, stride=16)

        model = HybridFusionNet(
            vocab_size=tok.vocab_size, d_model=64, n_layers=2, n_heads=4
        )

        trainer = Trainer(model, tok, windows)
        trainer.train(steps=5)

        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            ckpt_path = Path(f.name)
        try:
            trainer.save_checkpoint(ckpt_path)
            assert ckpt_path.exists()

            # Load into a fresh model
            model2 = HybridFusionNet(
                vocab_size=tok.vocab_size, d_model=64, n_layers=2, n_heads=4
            )
            trainer2 = Trainer(model2, tok, windows)
            trainer2.load_checkpoint(ckpt_path)
            assert len(trainer2.train_losses) == 5
        finally:
            ckpt_path.unlink(missing_ok=True)


# ── Integration: full pipeline without PDFs ─────────────────────────────────


class TestIntegration:
    def test_end_to_end_synthetic(self):
        """Run the full pipeline on synthetic data — no real PDFs needed."""
        from arch_discovery.architectures.registry import ArchitectureRegistry
        from arch_discovery.architectures.novel import (
            HybridFusionNet,
            register_novel_architectures,
        )
        from arch_discovery.tokenizer.char_tokenizer import CharTokenizer
        from arch_discovery.training.trainer import Trainer
        from arch_discovery.evaluation.evaluator import Evaluator

        # 1. Registry
        reg = ArchitectureRegistry()
        register_novel_architectures(reg)
        assert len(reg.list_architectures()) >= 3

        # 2. Tokenizer on synthetic data
        synthetic_corpus = (
            "The quick brown fox jumps over the lazy dog. " * 100
            + "Machine learning is the study of algorithms that improve "
              "through experience. " * 100
            + "Mathematics is the language of the universe. " * 100
        )
        tok = CharTokenizer()
        tok.build_vocab([synthetic_corpus])

        # 3. Windows
        train_windows = tok.sliding_windows(
            synthetic_corpus, window_size=64, stride=32
        )
        val_text = "Validation data for testing generalization. " * 50
        val_windows = tok.sliding_windows(val_text, window_size=64, stride=32)

        # 4. Train & evaluate one architecture
        model = reg.build(
            "HybridFusionNet",
            vocab_size=tok.vocab_size,
            d_model=64,
            n_layers=2,
        )
        assert model.parameter_count() <= 10_000_000

        trainer = Trainer(model, tok, train_windows, val_windows)
        log = trainer.train(steps=20)

        evaluator = Evaluator(model, tok)
        metrics = evaluator.evaluate(log, val_windows)

        # 5. Verify all metrics are populated
        assert metrics.architecture_name == "HybridFusionNet"
        assert metrics.train_loss > 0
        assert metrics.parameter_count > 0
        assert metrics.convergence_speed_steps > 0
        assert metrics.composite_score > 0

        # 6. Record and check leaderboard
        reg.record_result("HybridFusionNet", {
            "train_loss": metrics.train_loss,
            "val_loss": metrics.val_loss,
            "composite_score": metrics.composite_score,
            "parameter_count": metrics.parameter_count,
            "convergence_speed_steps": metrics.convergence_speed_steps,
            "training_stability_std": metrics.training_stability_std,
            "gpu_memory_mb": metrics.gpu_memory_mb,
            "inference_tokens_per_sec": metrics.inference_tokens_per_sec,
            "generalization_gap": metrics.generalization_gap,
        })

        best = reg.best_so_far()
        assert best is not None
        assert best["architecture"] == "HybridFusionNet"
