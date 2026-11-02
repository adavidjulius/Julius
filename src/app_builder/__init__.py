"""
Julius Build — Prompt-to-App Generation Pipeline.

Exports the core builder, spec, and record types.
"""
from .spec import AppSpec, VerificationStatus, FeatureTestResult
from .record import AppGenerationRecord
from .builder import AppBuilder

__all__ = [
    "AppSpec",
    "VerificationStatus",
    "FeatureTestResult",
    "AppGenerationRecord",
    "AppBuilder",
]
