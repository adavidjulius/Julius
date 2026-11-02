"""
Julius Build — App Spec and Verification Types.

AppSpec is extracted from a user's natural-language prompt before any code is written.
It becomes the checklist that Stage 4 (verified execution) checks against.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


# The four honest states — never presented without one of these
VerificationStatus = Literal[
    "verified_working",    # All core features exercised and confirmed
    "partially_verified",  # App ran; some features confirmed, some not
    "unverified",          # App started but no feature interaction confirmed
    "failed",              # Install, startup, or HTTP check failed
]


@dataclass
class FeatureTestResult:
    """Result of exercising one feature from the spec."""
    feature: str
    action_taken: str           # What Playwright did
    expected_result: str        # What success looks like
    observed_result: str        # What actually happened
    verified: bool              # True only if we positively confirmed the expected result
    error: str | None = None


@dataclass
class AppSpec:
    """
    Structured spec extracted from a user's prompt.
    Written to docs/app_spec_{name}.md before any code generation begins.
    """
    name: str                             # Slugified app name
    title: str                            # Human-readable app title
    description: str                      # User's original prompt
    features: list[str] = field(default_factory=list)     # Core feature list
    stack: str = "vite-vanilla"           # Chosen stack
    stack_reasoning: str = ""             # Why this stack
    data_layer: str = "none"              # none | mock | localStorage | backend
    screens: list[str] = field(default_factory=list)      # Core screens/views
    clarification_assumption: str = ""    # If anything ambiguous, what was assumed
    incomplete_items: list[str] = field(default_factory=list)  # Things that can't be built

    @property
    def slug(self) -> str:
        """URL/filesystem-safe name."""
        return re.sub(r"[^a-z0-9-]", "-", self.name.lower()).strip("-")

    def to_markdown(self) -> str:
        """Serialize to docs/app_spec_{name}.md format."""
        lines = [
            f"# App Spec: {self.title}",
            "",
            f"**Generated for prompt:** {self.description}",
            "",
            "## Stack Choice",
            f"**Stack:** `{self.stack}`",
            f"**Reasoning:** {self.stack_reasoning}",
            "",
            "## Core Features",
        ]
        for f in self.features:
            lines.append(f"- {f}")
        lines += [
            "",
            "## Screens / Views",
        ]
        for s in self.screens:
            lines.append(f"- {s}")
        lines += [
            "",
            f"## Data Layer",
            self.data_layer,
            "",
        ]
        if self.clarification_assumption:
            lines += [
                "## Interpretation Assumption",
                f"> {self.clarification_assumption}",
                "",
            ]
        if self.incomplete_items:
            lines += [
                "## ⚠️ Incomplete Items",
                "The following could NOT be fully implemented:",
            ]
            for item in self.incomplete_items:
                lines.append(f"- {item}")
        else:
            lines += ["## Incomplete Items", "None — all features are fully implemented."]
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, d: dict) -> "AppSpec":
        return cls(
            name=d.get("name", "app"),
            title=d.get("title", "App"),
            description=d.get("description", ""),
            features=d.get("features", []),
            stack=d.get("stack", "vite-vanilla"),
            stack_reasoning=d.get("stack_reasoning", ""),
            data_layer=d.get("data_layer", "none"),
            screens=d.get("screens", []),
            clarification_assumption=d.get("clarification_assumption", ""),
            incomplete_items=d.get("incomplete_items", []),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "features": self.features,
            "stack": self.stack,
            "stack_reasoning": self.stack_reasoning,
            "data_layer": self.data_layer,
            "screens": self.screens,
            "clarification_assumption": self.clarification_assumption,
            "incomplete_items": self.incomplete_items,
        }
