"""
Julius Build — AppGenerationRecord.

Mirrors the app_generations SQLite table. Every generated app gets one of these.
It is never presented to the user without a verification_status field — the same
discipline enforced for execution_type in the research pipeline.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .spec import AppSpec, VerificationStatus, FeatureTestResult


@dataclass
class AppGenerationRecord:
    """
    Full record of one app generation run.

    verification_status is REQUIRED and must be one of:
      verified_working   — all core features exercised and confirmed
      partially_verified — app ran; some features confirmed, some not
      unverified         — app started but no feature confirmed
      failed             — install / startup / HTTP check failed
    """
    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Spec
    spec: AppSpec | None = None

    # Generation results
    stack: str = ""
    files_generated: list[str] = field(default_factory=list)
    output_dir: str = ""

    # Stage 4: verified execution results — all must be populated
    install_success: bool = False
    install_output: str = ""
    startup_success: bool = False
    startup_output: str = ""
    http_check_status: int | None = None    # HTTP status code of running app, or None if not reached
    screenshot_path: str | None = None      # Path to screenshot, or None
    feature_results: list[FeatureTestResult] = field(default_factory=list)

    # Port the dev server is running on (or was attempted on)
    port_used: int | None = None

    # Things that could not be implemented
    incomplete_items: list[str] = field(default_factory=list)

    # THE critical field — always set, never implied
    verification_status: VerificationStatus = "unverified"

    # Human-readable summary of what was and wasn't verified
    verification_summary: str = ""

    def compute_verification_status(self) -> VerificationStatus:
        """
        Derive the honest verification_status from the real evidence.
        This is called AFTER all Stage 4 steps complete, never before.
        """
        if not self.install_success:
            return "failed"
        if not self.startup_success:
            return "failed"
        if self.http_check_status is None or self.http_check_status >= 400:
            return "unverified"
        if not self.feature_results:
            return "unverified"
        verified_count = sum(1 for r in self.feature_results if r.verified)
        total = len(self.feature_results)
        if verified_count == total:
            return "verified_working"
        elif verified_count > 0:
            return "partially_verified"
        else:
            return "unverified"

    def finalize(self) -> None:
        """Set verification_status from evidence. Call only after all Stage 4 steps."""
        self.verification_status = self.compute_verification_status()

        lines = []
        if self.install_success:
            lines.append("✅ Install succeeded")
        else:
            lines.append("❌ Install failed")

        if self.startup_success:
            lines.append("✅ Dev server started")
        else:
            lines.append("❌ Dev server did not start")

        if self.http_check_status is not None:
            lines.append(f"✅ HTTP check: {self.http_check_status}" if self.http_check_status < 400
                         else f"❌ HTTP check: {self.http_check_status}")
        else:
            lines.append("❌ HTTP check: not reached")

        if self.screenshot_path:
            lines.append("✅ Screenshot captured")
        else:
            lines.append("⚠️ No screenshot")

        for r in self.feature_results:
            icon = "✅" if r.verified else "❌"
            lines.append(f"{icon} Feature: {r.feature} — {r.observed_result}")

        if self.incomplete_items:
            lines.append("")
            lines.append("⚠️ Incomplete items (not implemented):")
            for item in self.incomplete_items:
                lines.append(f"  - {item}")

        self.verification_summary = "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "timestamp": self.timestamp,
            "spec": self.spec.to_dict() if self.spec else {},
            "stack": self.stack,
            "files_generated": self.files_generated,
            "output_dir": self.output_dir,
            "install_success": self.install_success,
            "install_output": self.install_output,
            "startup_success": self.startup_success,
            "startup_output": self.startup_output,
            "http_check_status": self.http_check_status,
            "screenshot_path": self.screenshot_path,
            "feature_results": [
                {
                    "feature": r.feature,
                    "action_taken": r.action_taken,
                    "expected_result": r.expected_result,
                    "observed_result": r.observed_result,
                    "verified": r.verified,
                    "error": r.error,
                }
                for r in self.feature_results
            ],
            "port_used": self.port_used,
            "incomplete_items": self.incomplete_items,
            "verification_status": self.verification_status,
            "verification_summary": self.verification_summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AppGenerationRecord":
        spec = AppSpec.from_dict(d["spec"]) if d.get("spec") else None
        feature_results = [
            FeatureTestResult(
                feature=r["feature"],
                action_taken=r["action_taken"],
                expected_result=r["expected_result"],
                observed_result=r["observed_result"],
                verified=r["verified"],
                error=r.get("error"),
            )
            for r in d.get("feature_results", [])
        ]
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            project_id=d.get("project_id", ""),
            timestamp=d.get("timestamp", datetime.utcnow().isoformat()),
            spec=spec,
            stack=d.get("stack", ""),
            files_generated=d.get("files_generated", []),
            output_dir=d.get("output_dir", ""),
            install_success=d.get("install_success", False),
            install_output=d.get("install_output", ""),
            startup_success=d.get("startup_success", False),
            startup_output=d.get("startup_output", ""),
            http_check_status=d.get("http_check_status"),
            screenshot_path=d.get("screenshot_path"),
            feature_results=feature_results,
            port_used=d.get("port_used"),
            incomplete_items=d.get("incomplete_items", []),
            verification_status=d.get("verification_status", "unverified"),
            verification_summary=d.get("verification_summary", ""),
        )
