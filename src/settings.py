"""
Julius Validated Settings & Configuration Management (WS4.1).

Implements strict schema validation using Pydantic Settings,
documented precedence rules (CLI > ENV > project toml > user toml > defaults),
secrets masking, and feature flags.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


class ProviderSettings(BaseModel):
    """Configuration for LLM providers."""
    default_provider: str = Field(default="nvidia", description="Default LLM provider")
    fallback: List[str] = Field(
        default_factory=lambda: ["nvidia", "ollama"],
        description="Explicit fallback order when primary provider fails",
    )
    timeout_seconds: float = Field(default=60.0, description="Total HTTP timeout in seconds")
    connect_timeout_seconds: float = Field(default=10.0, description="Connection timeout in seconds")
    stream_idle_timeout_seconds: float = Field(default=30.0, description="Stream idle timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts on retryable errors")
    circuit_breaker_threshold: int = Field(default=5, description="Consecutive errors to trip circuit breaker")
    circuit_breaker_cooldown: float = Field(default=60.0, description="Circuit breaker cooldown in seconds")
    data_residency: Literal["any", "local_only"] = Field(
        default="any",
        description="Data residency policy: 'local_only' blocks all external cloud fallbacks",
    )

    # Provider API keys (masked in serialization)
    openai_api_key: Optional[SecretStr] = None
    anthropic_api_key: Optional[SecretStr] = None
    gemini_api_key: Optional[SecretStr] = None
    deepseek_api_key: Optional[SecretStr] = None
    xai_api_key: Optional[SecretStr] = None
    moonshot_api_key: Optional[SecretStr] = None
    perplexity_api_key: Optional[SecretStr] = None
    nvidia_api_key: Optional[SecretStr] = None

    # Custom base URLs
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    deepseek_base_url: str = "https://api.deepseek.com"
    xai_base_url: str = "https://api.x.ai/v1"
    moonshot_base_url: str = "https://api.moonshot.cn/v1"
    perplexity_base_url: str = "https://api.perplexity.ai"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    ollama_host: str = "http://127.0.0.1:11434"

    def get(self, key: str, default: Any = None) -> Any:
        """Dictionary-like accessor for compatibility."""
        return getattr(self, key, default)


class TelemetrySettings(BaseModel):
    """Telemetry and observability configuration (Strictly Opt-In)."""
    enabled: bool = Field(default=False, description="Whether OpenTelemetry/external metrics are enabled")
    otlp_endpoint: Optional[str] = Field(default=None, description="OTLP collector endpoint (if enabled)")
    log_format: Literal["text", "json"] = Field(default="text", description="Log format: 'text' or 'json'")
    log_level: str = Field(default="INFO", description="Logging level")
    metrics_port: int = Field(default=9090, description="Local Prometheus metrics port")
    cost_tracking_enabled: bool = Field(default=True, description="Enable local cost tracking")
    max_daily_budget_usd: float = Field(default=25.0, description="Maximum daily token cost budget before alert")


class SandboxSettings(BaseModel):
    """Execution sandbox and safety isolation configuration."""
    tier: Literal[0, 1, 2, 3] = Field(
        default=1,
        description="Sandbox Tier: 0=Read-only, 1=Workspace (Default), 2=Container, 3=Host",
    )
    container_image: str = Field(default="ghcr.io/julius-agent/sandbox:latest", description="Docker sandbox image")
    container_memory_limit: str = Field(default="1g", description="Memory limit for container sandbox")
    container_cpu_limit: float = Field(default=2.0, description="CPU cores limit for container sandbox")
    network_enabled: bool = Field(default=False, description="Whether sandboxed code execution has internet access")
    max_bash_timeout_seconds: int = Field(default=60, description="Maximum execution time for bash commands")
    allowed_host_paths: List[str] = Field(
        default_factory=list,
        description="Explicit directories allowed for Tier 3 host access",
    )


class SecuritySettings(BaseModel):
    """Security, taint tracking, and secrets management."""
    deny_by_default: bool = Field(default=True, description="Enforce strict deny-by-default on all tool operations")
    secrets_scanner_fail_closed: bool = Field(default=True, description="Block operations if secret scanner fails")
    taint_tracking_enabled: bool = Field(default=True, description="Tag untrusted data and restrict autonomous egress")
    daemon_loopback_only: bool = Field(default=True, description="Bind daemon exclusively to 127.0.0.1 / localhost")
    daemon_port: int = Field(default=8000, description="Daemon HTTP listening port")
    require_origin_check: bool = Field(default=True, description="Validate Host and Origin headers to block DNS rebinding")


class AgentBudgetSettings(BaseModel):
    """Safety limits on autonomous loops."""
    max_steps: int = Field(default=50, description="Maximum action steps per autonomous task")
    max_wall_time_seconds: int = Field(default=900, description="Maximum wall-clock execution time (15 mins)")
    max_tokens_per_run: int = Field(default=500_000, description="Maximum tokens allowed for a single task run")
    max_cost_usd_per_run: float = Field(default=5.0, description="Maximum cost in USD per task run")
    max_consecutive_tool_errors: int = Field(default=5, description="Stop after consecutive tool execution errors")
    loop_detection_window: int = Field(default=4, description="Detect repeated tool calls in this history window")


class FeatureFlags(BaseModel):
    """Local feature toggles."""
    enable_vcs_worktrees: bool = True
    enable_semantic_search: bool = True
    enable_mcp_plugins: bool = True
    enable_voice: bool = True
    enable_audit_chain_v2: bool = True


class Settings(BaseSettings):
    """
    Primary Julius Settings.

    Configured via:
      1. Explicit CLI arguments
      2. Environment variables (prefix JULIUS_, e.g. JULIUS_SANDBOX__TIER=2)
      3. Project configuration: .julius/config.toml
      4. User configuration: ~/.julius/config.toml
      5. Built-in defaults
    """
    model_config = SettingsConfigDict(
        env_prefix="JULIUS_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    workspace_dir: str = Field(default_factory=lambda: str(Path.cwd()), description="Active workspace path")
    providers: ProviderSettings = Field(default_factory=ProviderSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    budgets: AgentBudgetSettings = Field(default_factory=AgentBudgetSettings)
    features: FeatureFlags = Field(default_factory=FeatureFlags)

    @property
    def active_provider(self) -> str:
        """Active or default LLM provider name."""
        return self.providers.default_provider

    @active_provider.setter
    def active_provider(self, val: str) -> None:
        self.providers.default_provider = str(val).lower().strip()

    @classmethod
    def load_resolved(
        cls,
        workspace: Optional[str] = None,
        cli_overrides: Optional[Dict[str, Any]] = None,
    ) -> Settings:
        """
        Load resolved configuration respecting precedence:
        CLI > ENV > .julius/config.toml > ~/.julius/config.toml > defaults.
        """
        resolved_dict: Dict[str, Any] = {}

        # 1. User config: ~/.julius/config.toml
        user_cfg = Path.home() / ".julius" / "config.toml"
        if user_cfg.exists() and tomllib:
            try:
                with open(user_cfg, "rb") as f:
                    resolved_dict.update(tomllib.load(f))
            except Exception:
                pass

        # 2. Project config: <workspace>/.julius/config.toml
        ws_root = Path(workspace).resolve() if workspace else Path.cwd()
        proj_cfg = ws_root / ".julius" / "config.toml"
        if proj_cfg.exists() and tomllib:
            try:
                with open(proj_cfg, "rb") as f:
                    proj_data = tomllib.load(f)
                    # For security: secrets must not be read from project config file
                    if "providers" in proj_data:
                        for k in list(proj_data["providers"].keys()):
                            if "key" in k.lower() or "secret" in k.lower():
                                del proj_data["providers"][k]
                    resolved_dict.update(proj_data)
            except Exception:
                pass

        # 3. Handle common alias environment variables for providers
        env_updates: Dict[str, Any] = {}
        prov_updates: Dict[str, Any] = {}
        if os.getenv("OLLAMA_HOST"):
            prov_updates["ollama_host"] = os.getenv("OLLAMA_HOST")
        if os.getenv("OPENAI_API_KEY"):
            prov_updates["openai_api_key"] = os.getenv("OPENAI_API_KEY")
        if os.getenv("ANTHROPIC_API_KEY"):
            prov_updates["anthropic_api_key"] = os.getenv("ANTHROPIC_API_KEY")
        if os.getenv("GEMINI_API_KEY"):
            prov_updates["gemini_api_key"] = os.getenv("GEMINI_API_KEY")
        if os.getenv("DEEPSEEK_API_KEY"):
            prov_updates["deepseek_api_key"] = os.getenv("DEEPSEEK_API_KEY")
        if os.getenv("NVIDIA_API_KEY") or os.getenv("NVIDIA_NIM_API_KEY"):
            prov_updates["nvidia_api_key"] = os.getenv("NVIDIA_API_KEY") or os.getenv("NVIDIA_NIM_API_KEY")

        if prov_updates:
            if "providers" not in resolved_dict:
                resolved_dict["providers"] = {}
            resolved_dict["providers"].update(prov_updates)

        # 4. Apply CLI overrides
        if cli_overrides:
            for k, v in cli_overrides.items():
                if v is not None:
                    if "__" in k:
                        section, subk = k.split("__", 1)
                        if section not in resolved_dict:
                            resolved_dict[section] = {}
                        resolved_dict[section][subk] = v
                    else:
                        resolved_dict[k] = v

        if workspace:
            resolved_dict["workspace_dir"] = str(Path(workspace).resolve())

        # Instantiate settings with BaseSettings (automatically applies JULIUS_* env vars)
        return cls(**resolved_dict)

    def mask_secrets_dump(self) -> Dict[str, Any]:
        """Return dict representation with all sensitive secrets masked."""
        data = self.model_dump()
        if "providers" in data:
            prov = data["providers"]
            for k, v in prov.items():
                if "key" in k.lower() and v:
                    prov[k] = "********"
        return data


# Global singleton instance cache
_GLOBAL_SETTINGS: Optional[Settings] = None


def get_settings(workspace: Optional[str] = None, refresh: bool = False) -> Settings:
    """Retrieve global cached settings or load resolved settings."""
    global _GLOBAL_SETTINGS
    if _GLOBAL_SETTINGS is None or refresh or workspace:
        _GLOBAL_SETTINGS = Settings.load_resolved(workspace=workspace)
    return _GLOBAL_SETTINGS

