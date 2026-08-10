"""
Configuration loader. YAML + environment overrides.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursive dict merge — overlay wins per-key, nested dicts merge instead of replace."""
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_dotenv(path: Path) -> None:
    """
    Minimal .env loader (stdlib only). Previously .env was only ever parsed by
    the PowerShell wrapper (scripts/windows/_common.ps1::Import-ClankEnv) —
    running `python main.py ...`, the dashboard, or the daemon directly never
    loaded it, so DISCORD_WEBHOOK_URL / MAINTENANCE_DISCORD_WEBHOOK_URL set
    only in .env were invisible to any Python entry point. Real process
    environment variables always win (setdefault, never overwrite).
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


class Settings(BaseSettings):
    config_path: str = Field(default="config/config.yaml")

    # Will be populated from YAML
    raw: dict[str, Any] = Field(default_factory=dict)
    local_config_loaded: Optional[str] = Field(default=None)

    class Config:
        env_prefix = "CLANK_"
        extra = "ignore"

    def load(self) -> "Settings":
        _load_dotenv(Path(os.getenv("CLANK_ENV_FILE", ".env")))

        path = Path(self.config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            self.raw = yaml.safe_load(f) or {}

        # Untracked, operator-local overlay — survives a repo/archive re-extract
        # since it's never part of the tracked defaults. Deep-merged on top of
        # config.yaml so a single nested key can be overridden without repeating
        # the whole block. Absence is normal and safe (defaults stand alone).
        local_path = Path(os.getenv("CLANK_LOCAL_CONFIG", "config/config.local.yaml"))
        if local_path.exists():
            with open(local_path, "r", encoding="utf-8") as f:
                overlay = yaml.safe_load(f) or {}
            self.raw = _deep_merge(self.raw, overlay)
            self.local_config_loaded = str(local_path)
        else:
            self.local_config_loaded = None

        # Discord webhooks from env take precedence — two independent channels.
        # Staging is hard-isolated: it only ever reads STAGING_DISCORD_WEBHOOK_URL,
        # never DISCORD_WEBHOOK_URL / MAINTENANCE_DISCORD_WEBHOOK_URL. This means a
        # production webhook set in the shared environment can never leak a Wave 1
        # baseline-import or candidate-rejection message into the real newsroom.
        if self.environment == "staging":
            env_staging_webhook = os.getenv("STAGING_DISCORD_WEBHOOK_URL")
            if env_staging_webhook:
                self.raw.setdefault("discord", {})["webhook_url"] = env_staging_webhook
                self.raw.setdefault("discord", {})["maintenance_webhook_url"] = env_staging_webhook
        else:
            env_webhook = os.getenv("DISCORD_WEBHOOK_URL")
            if env_webhook:
                self.raw.setdefault("discord", {})["webhook_url"] = env_webhook

            env_maintenance_webhook = os.getenv("MAINTENANCE_DISCORD_WEBHOOK_URL")
            if env_maintenance_webhook:
                self.raw.setdefault("discord", {})["maintenance_webhook_url"] = env_maintenance_webhook

        return self

    def effective_source_summary(self) -> dict:
        """What config actually took effect, for auditability (never touch raw file writes)."""
        return {
            "repo_defaults": self.config_path,
            "local_override": self.local_config_loaded,
            "local_override_active": self.local_config_loaded is not None,
            "production_samsung_only": bool(self.get("production", "samsung_only", default=True)),
        }

    def __repr__(self) -> str:  # never leak webhook URLs via repr/logging
        from alerts.delivery import redact_webhook_url
        return (
            f"Settings(config_path={self.config_path!r}, "
            f"discord_webhook={redact_webhook_url(self.discord_webhook)}, "
            f"maintenance_webhook={redact_webhook_url(self.maintenance_webhook)})"
        )

    __str__ = __repr__

    def get(self, *keys: str, default: Any = None) -> Any:
        node = self.raw
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    @property
    def environment(self) -> str:
        return str(self.get("environment", default="production") or "production")

    @property
    def database_url(self) -> str:
        return self.get("database", "url", default="sqlite:///./data/clank.db")

    @property
    def discord_webhook(self) -> str:
        return self.get("discord", "webhook_url", default="") or ""

    @property
    def maintenance_webhook(self) -> str:
        return self.get("discord", "maintenance_webhook_url", default="") or ""

    @property
    def confidence_weights(self) -> dict[str, int]:
        return self.get("confidence_weights", default={})

    @property
    def manufacturers(self) -> list[str]:
        return self.get("manufacturers", default=[])


def load_settings(config_path: str = "config/config.yaml") -> Settings:
    return Settings(config_path=config_path).load()
