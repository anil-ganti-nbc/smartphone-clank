"""
Wave 1 staging-only collector registry.

Deliberately NOT wired into collectors/__init__.py::build_collectors() or
collectors/__init__.py::production_scope() — those remain the Samsung-only
production gate. This registry is only ever invoked from main.py's
`--environment staging` path, which has already asserted the database_url
looks like a staging path (runtime/environment.py) before this module is
imported.
"""

from __future__ import annotations

import logging

from collectors.wave1.adapter import DiscoveryAdapter
from collectors.wave1.google.discovery import GoogleStoreDiscoveryAdapter
from collectors.wave1.nothing.discovery import NothingSitemapDiscoveryAdapter
from collectors.wave1.oneplus.discovery import OnePlusSitemapDiscoveryAdapter
from collectors.wave1.xiaomi.discovery import XiaomiSitemapDiscoveryAdapter

logger = logging.getLogger("clank.collectors.wave1")

# Populated as each OEM adapter reaches a runnable state during Wave 1
# development. An OEM absent here has not yet earned a wired adapter —
# absence is the safe default, matching the production registry's
# fail-closed philosophy (collectors/__init__.py::_eligible).
ADAPTER_REGISTRY: dict[str, type[DiscoveryAdapter]] = {
    "google": GoogleStoreDiscoveryAdapter,
    "oneplus": OnePlusSitemapDiscoveryAdapter,
    "nothing": NothingSitemapDiscoveryAdapter,
    "xiaomi": XiaomiSitemapDiscoveryAdapter,
}


def build_wave1_collectors(settings) -> list[DiscoveryAdapter]:
    wave1_cfg = settings.get("wave1", default={}) or {}
    http_cfg = settings.get("http", default={}) or {}
    common = {
        "user_agent": http_cfg.get("user_agent", "SmartphoneIntelClank-Staging/0.1"),
        "min_delay": float(http_cfg.get("min_delay_seconds", 1.5)),
    }
    out: list[DiscoveryAdapter] = []
    for oem, cls in ADAPTER_REGISTRY.items():
        oem_cfg = wave1_cfg.get(oem, {}) or {}
        if not oem_cfg.get("enabled", False):
            continue
        out.append(cls(**common, max_fetches_per_run=int(oem_cfg.get("max_fetches_per_run", 20))))
    return out


def run_wave1_once(settings, session_factory) -> None:
    """
    Run every enabled Wave 1 adapter once, report-only (spec section 32: collectors
    answer "what appeared", not "is it newsworthy"). Intentionally does not touch
    entity_resolution/confidence services directly — see docs/wave1/ for the plan
    to route validated results through the same resolver Samsung uses, once an
    OEM has a wired validator + adapter.
    """
    adapters = build_wave1_collectors(settings)
    if not adapters:
        logger.info("wave1: no adapters enabled/wired yet")
        return
    for adapter in adapters:
        try:
            results, metrics = adapter.discover()
            logger.info(
                "wave1[%s/%s]: %d candidates, %d fetched, %d failures",
                adapter.manufacturer, adapter.source_name,
                len(results), metrics.pages_fetched, metrics.http_failures,
            )
        except Exception as e:
            logger.warning("wave1[%s]: adapter failed: %s", adapter.source_name, e)
