"""
Collector registry for production runtime.

Authoritative Samsung sources: config/samsung_sources.yaml
Safe default: only LIVE_VALIDATED (and optionally LIVE_PARTIAL) run automatically.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from collectors.base import BaseCollector
from collectors.bluetooth_sig import BluetoothSIGCollector
from collectors.samsung_support import SamsungSupportCollector
from collectors.samsung.sitemap_collector import SamsungSitemapCollector
from collectors.generic_support import GenericSupportCollector
from collectors.firmware import SamsungFirmwareCollector, PixelOTACollector, NothingOTACollector
from collectors.samsung_owners import SamsungOwnersCollector

logger = logging.getLogger("clank.collectors")

SAFE_LIVE_STATUSES = {"LIVE_VALIDATED"}
OPTIONAL_PARTIAL = {"LIVE_PARTIAL"}
REJECT_STATUSES = {
    "BLOCKED",
    "UNSUPPORTED",
    "FIXTURE_ONLY",
    "UNAVAILABLE",
    "NOT_RELEVANT",
}


def _load_samsung_sources(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    path = root / "config" / "samsung_sources.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    samsung = data.get("samsung") or data
    return samsung if isinstance(samsung, dict) else {}


def _source_entries(samsung_cfg: dict) -> dict[str, dict]:
    sources = samsung_cfg.get("sources") or {}
    return sources if isinstance(sources, dict) else {}


# Samsung source IDs that actually have a wired collector implementation in
# build_collectors() below. A source can be LIVE_VALIDATED in samsung_sources.yaml
# and still have no code behind it (e.g. samsung_us_owners_product) — being
# "validated" describes the source, not the existence of a runnable collector.
# production_scope() must never advertise a source nothing can actually run.
RUNNABLE_SAMSUNG_SOURCE_IDS = {"samsung_us_support_sitemap", "samsung_support"}

# SOAK sources: implemented, validated against live surfaces, but holding NO
# production promotion record. They are excluded from RUNNABLE (so production
# scope can never execute them) and are only registered when a caller passes
# include_soak=True — wired for staging environments in runtime/run_once.py.
# Notification authority stays suppressed by policy regardless of environment:
# see alerts/source_maturity.py.
SOAK_SAMSUNG_SOURCE_IDS = {"samsung_us_owners_product"}


def production_scope(settings, project_root: Path | None = None) -> set[str]:
    """
    Collector IDs allowed to run automatically in production.

    Default policy (samsung_only=True, the safe default): samsung_us_support_sitemap
    plus any other Samsung source in config/samsung_sources.yaml that is both
    demonstrably LIVE_VALIDATED *and* has a real collector implementation
    (RUNNABLE_SAMSUNG_SOURCE_IDS) — a validated-but-unimplemented source is not
    in scope, since nothing can run it. Everything else — every non-Samsung
    collector, every experimental/certification/OTA collector — is out of scope
    regardless of its `enabled` flag in config.yaml. This is the enforcement
    point: a future config regression that flips a non-Samsung collector's
    `enabled` back to true cannot bring it back into production without also
    being added here.
    """
    samsung_only = bool(settings.get("production", "samsung_only", default=True))
    scope = {"samsung_us_support_sitemap"}
    if not samsung_only:
        return None  # None means "no scope restriction" — explicit opt-out only
    samsung_cfg = _load_samsung_sources(project_root)
    for source_id, src in _source_entries(samsung_cfg).items():
        if source_id not in RUNNABLE_SAMSUNG_SOURCE_IDS:
            continue
        status = (src.get("validation_status") or "").upper()
        if status == "LIVE_VALIDATED":
            scope.add(source_id)
    return scope


def _eligible(
    collector_id: str,
    *,
    cfg: dict,
    scope: set[str] | None,
    validation_status: str | None = None,
    reject_statuses: set[str] = REJECT_STATUSES,
    safe_statuses: set[str] = SAFE_LIVE_STATUSES,
    partial_statuses: set[str] = OPTIONAL_PARTIAL,
    allow_partial: bool = False,
) -> tuple[bool, str]:
    """
    Universal collector eligibility gate. Fails closed: any missing or
    ambiguous signal excludes the collector rather than defaulting it in.
    """
    if scope is not None and collector_id not in scope:
        return False, "out_of_production_scope"
    if cfg is None:
        return False, "no_config_entry"
    if cfg.get("enabled") is not True:
        return False, "disabled_in_config"
    if validation_status is not None:
        status = validation_status.upper()
        if status in reject_statuses:
            return False, f"rejected_status:{status}"
        if status in safe_statuses:
            return True, f"ok:{status}"
        if allow_partial and status in partial_statuses:
            return True, f"ok_partial:{status}"
        return False, f"status_not_allowed:{status}"
    return True, "ok"


def build_collectors(
    settings,
    *,
    allow_partial: bool = False,
    include_soak: bool = False,
    project_root: Path | None = None,
) -> list[BaseCollector]:
    collectors_cfg = settings.get("collectors", default={}) or {}
    manufacturers = getattr(settings, "manufacturers", None) or settings.get(
        "manufacturers", default=["samsung", "google", "oneplus", "nothing", "xiaomi"]
    )
    http_cfg = settings.get("http", default={}) or {}
    common = {
        "user_agent": http_cfg.get("user_agent", "SmartphoneIntelClank/0.3.6"),
        "min_delay": float(http_cfg.get("min_delay_seconds", 1.5)),
    }

    scope = production_scope(settings, project_root)
    registry: list[BaseCollector] = []
    skipped: list[tuple[str, str]] = []

    def add(name: str, cls, **extra):
        cfg = collectors_cfg.get(name, {}) or {}
        ok, reason = _eligible(name, cfg=cfg if name in collectors_cfg else None, scope=scope)
        if not ok:
            skipped.append((name, reason))
            return
        kwargs = {
            **common,
            "timeout": cfg.get("timeout", 30),
            "max_retries": cfg.get("max_retries", 3),
            **extra,
        }
        registry.append(cls(**kwargs))

    samsung_cfg = _load_samsung_sources(project_root)
    kill = bool(samsung_cfg.get("kill_switch") or samsung_cfg.get("disabled"))
    sources = _source_entries(samsung_cfg)

    if not kill:
        sm_id = "samsung_us_support_sitemap"
        sm_src = sources.get(sm_id) or {}
        sm_cfg = collectors_cfg.get(sm_id) or {}
        # samsung_us_support_sitemap defaults enabled=True (production baseline discovery
        # collector) unless config.yaml explicitly says otherwise.
        sm_cfg_effective = {**sm_cfg, "enabled": sm_cfg.get("enabled", True)}
        status = (sm_src.get("validation_status") or "LIVE_VALIDATED").upper()
        ok, reason = _eligible(
            sm_id, cfg=sm_cfg_effective, scope=scope, validation_status=status,
            allow_partial=allow_partial,
        )
        if not ok:
            skipped.append((sm_id, reason))
        else:
            max_fetches = int(
                sm_cfg.get("max_product_fetches")
                or sm_src.get("max_requests_per_run")
                or 15
            )
            registry.append(
                SamsungSitemapCollector(
                    **common,
                    timeout=sm_cfg.get("timeout", 30),
                    max_product_fetches=max_fetches,
                    min_refetch_hours=float(sm_cfg.get("min_refetch_hours", 12)),
                    failed_retry_minutes=float(sm_cfg.get("failed_retry_minutes", 180)),
                )
            )
            logger.info("Registered production discovery collector: %s (%s)", sm_id, status)

        leg_id = "samsung_support"
        leg_cfg = collectors_cfg.get(leg_id) or {}
        leg_src = sources.get(leg_id) or {}
        leg_status = (leg_src.get("validation_status") or "LIVE_PARTIAL").upper()
        ok, reason = _eligible(
            leg_id, cfg=leg_cfg if leg_id in collectors_cfg else None, scope=scope,
            validation_status=leg_status, allow_partial=allow_partial,
        )
        if leg_cfg.get("enabled") is not True:
            skipped.append((leg_id, "disabled_by_default_secondary"))
        elif not ok:
            skipped.append((leg_id, reason))
        else:
            col = SamsungSupportCollector(
                **common,
                timeout=leg_cfg.get("timeout", 30),
                max_retries=leg_cfg.get("max_retries", 3),
            )
            col.capability = "monitoring"  # type: ignore[attr-defined]
            col.validation_status = leg_status  # type: ignore[attr-defined]
            registry.append(col)
    else:
        skipped.append(("samsung_*", "kill_switch"))

    if include_soak and not kill:
        for soak_id in sorted(SOAK_SAMSUNG_SOURCE_IDS):
            src = sources.get(soak_id) or {}
            status = (src.get("validation_status") or "").upper()
            cfg = collectors_cfg.get(soak_id) or {}
            if src.get("enabled") is not True:
                skipped.append((soak_id, "soak_disabled_in_registry"))
                continue
            if status not in SAFE_LIVE_STATUSES | OPTIONAL_PARTIAL:
                skipped.append((soak_id, f"soak_status_not_allowed:{status}"))
                continue
            col = SamsungOwnersCollector(
                **common,
                timeout=cfg.get("timeout", 30),
                max_retries=cfg.get("max_retries", 3),
            )
            col.capability = "discovery"  # type: ignore[attr-defined]
            col.validation_status = status  # type: ignore[attr-defined]
            col.maturity = "soak"  # type: ignore[attr-defined]
            registry.append(col)
            logger.info("Registered SOAK collector: %s (%s) — notifications suppressed by policy", soak_id, status)

    add("bluetooth_sig", BluetoothSIGCollector, manufacturers=manufacturers)
    add("samsung_firmware", SamsungFirmwareCollector)
    add("pixel_ota", PixelOTACollector)
    add("nothing_ota", NothingOTACollector)
    for oem in ["google", "oneplus", "nothing", "xiaomi"]:
        add(f"{oem}_support", GenericSupportCollector, oem=oem)

    for name, reason in skipped:
        logger.info("Collector skipped: %s (%s)", name, reason)

    return registry


def describe_registry(settings, **kwargs) -> list[dict]:
    cols = build_collectors(settings, **kwargs)
    return [
        {
            "collector_id": c.name,
            "class": c.__class__.__name__,
            "capability": getattr(c, "capability", "unknown"),
            "validation_status": getattr(c, "validation_status", "unknown"),
            "source_type": str(getattr(c, "source_type", "")),
        }
        for c in cols
    ]
