"""
Wave 1 collector registry.

Deliberately NOT wired into collectors/__init__.py::build_collectors() or
collectors/__init__.py::production_scope() — those remain the Samsung-only
gate for that separate registry. This module's own `build_wave1_collectors()`
is invoked from main.py's `--environment staging` path, which has already
asserted the database_url looks like a staging path (runtime/environment.py)
before this module is imported.

`WAVE1_PRODUCTION_SCOPE` / `build_wave1_production_collectors()` below are the
analogous explicit allowlist for every OEM (Wave 1 or Wave 2) approved for
production — Google, Nothing, OnePlus (Wave 1), Motorola, Honor (Wave 2) —
each promoted after its own canary. See docs/wave1/PROMOTION_REPORT.md,
docs/wave2/MOTOROLA_CANARY_REPORT.md, and docs/wave2/HONOR_CANARY_REPORT.md.
A config typo flipping `wave1.xiaomi.enabled` (or any OEM's `enabled`) to
true in production's config.yaml is not sufficient by itself to bring it
into production; only adding it to this allowlist does. This mirrors
collectors/__init__.py::production_scope()'s own philosophy for Samsung.
Xiaomi remains deliberately excluded — KEEP_STAGING, its source oscillated
200/403 during qualification. Oppo/Vivo/Realme/ASUS remain excluded — see
docs/wave2/WAVE2_RANKING.md.

Known naming debt (documented, not fixed — see
docs/wave2/POST_WAVE2_COMPLEXITY_AUDIT.md Q2): this module and
`WAVE1_PRODUCTION_SCOPE` are named for Wave 1 but now also gate Wave 2 OEMs
(Motorola as of this phase). A rename to a Wave-agnostic name like
`PRODUCTION_OEM_SCOPE` was considered and deliberately deferred — the
mechanism is simple, correct, and well-tested as-is; renaming it now would
be a cosmetic refactor during a production-affecting canary, which
engineering principle #1/#20 (complexity budget) argues against. Revisit
this rename in a dedicated, low-risk mission if a third wave ever begins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from collectors.wave1.adapter import DiscoveryAdapter
from collectors.wave1.google.discovery import GoogleStoreDiscoveryAdapter
from collectors.wave1.nothing.discovery import NothingSitemapDiscoveryAdapter
from collectors.wave1.oneplus.discovery import OnePlusSitemapDiscoveryAdapter
from collectors.wave1.xiaomi.discovery import XiaomiSitemapDiscoveryAdapter
from collectors.wave2.motorola.discovery import MotorolaSitemapDiscoveryAdapter
from collectors.wave2.honor.discovery import HonorSitemapDiscoveryAdapter
from collectors.wave2.oppo.discovery import OppoSitemapDiscoveryAdapter
from collectors.wave2.realme.discovery import RealmeSitemapDiscoveryAdapter

logger = logging.getLogger("clank.collectors.wave1")

# Populated as each OEM adapter reaches a runnable state during Wave 1 (or
# Wave 2) development. An OEM absent here has not yet earned a wired
# adapter — absence is the safe default, matching the production
# registry's fail-closed philosophy (collectors/__init__.py::_eligible).
ADAPTER_REGISTRY: dict[str, type[DiscoveryAdapter]] = {
    "google": GoogleStoreDiscoveryAdapter,
    "oneplus": OnePlusSitemapDiscoveryAdapter,
    "nothing": NothingSitemapDiscoveryAdapter,
    "xiaomi": XiaomiSitemapDiscoveryAdapter,
    "motorola": MotorolaSitemapDiscoveryAdapter,
    "honor": HonorSitemapDiscoveryAdapter,
    "oppo": OppoSitemapDiscoveryAdapter,
    "realme": RealmeSitemapDiscoveryAdapter,
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


# The explicit production allowlist. Expand one OEM at a time, only after
# that OEM's own canary — see docs/wave1/PROMOTION_REPORT.md,
# docs/wave1/GOOGLE_CANARY_REPORT.md, docs/wave1/NOTHING_CANARY_REPORT.md,
# docs/wave1/ONEPLUS_CANARY_REPORT.md. Never edit this set as a side effect
# of a config change; it is the deliberate second gate config alone cannot
# satisfy. Xiaomi is deliberately absent — KEEP_STAGING.
WAVE1_PRODUCTION_SCOPE: set[str] = {"google", "nothing", "oneplus", "motorola", "honor", "oppo", "realme"}

# Preferred name going forward (docs/infra/PRODUCTION_SCOPE_AUDIT.md Part 3)
# — literally the same object, not a second source of truth. New code
# should reference PRODUCTION_OEM_SCOPE; WAVE1_PRODUCTION_SCOPE is kept for
# every existing call site/test/docstring rather than a disruptive rename.
PRODUCTION_OEM_SCOPE = WAVE1_PRODUCTION_SCOPE


def build_wave1_production_collectors(settings) -> list[DiscoveryAdapter]:
    """Production-safe subset of build_wave1_collectors(): only OEMs both
    `enabled: true` in config AND present in PRODUCTION_OEM_SCOPE. Callers
    (runtime/daemon.py) must additionally assert the database_url is a real
    production path before scheduling anything this returns — see
    runtime.environment.assert_db_matches_environment."""
    return [a for a in build_wave1_collectors(settings) if a.manufacturer in PRODUCTION_OEM_SCOPE]


@dataclass
class OEMScopeStatus:
    """Per-OEM answer to the five independent truths that must agree for
    every approved production OEM (docs/infra/PRODUCTION_SCOPE_AUDIT.md
    Part 2-4). This is exactly the set of checks that would have caught the
    Motorola incident before startup: `approved=True` but
    `manufacturer_configured=False` is precisely what happened."""
    oem: str
    approved: bool                  # in PRODUCTION_OEM_SCOPE
    manufacturer_configured: bool   # in settings.manufacturers (pipeline.py's gate)
    adapter_registered: bool        # in ADAPTER_REGISTRY
    config_enabled: bool            # wave1.<oem>.enabled: true
    scheduled: bool                 # would build_wave1_production_collectors() return it

    @property
    def ok(self) -> bool:
        if not self.approved:
            return True  # not approved -> no requirements on it
        return (
            self.manufacturer_configured
            and self.adapter_registered
            and self.config_enabled
            and self.scheduled
        )


@dataclass
class ScopeValidationResult:
    statuses: list[OEMScopeStatus] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.statuses)

    @property
    def mismatches(self) -> list[OEMScopeStatus]:
        return [s for s in self.statuses if not s.ok]

    def render(self) -> str:
        lines = ["Production scope validation", ""]
        approved = [s for s in self.statuses if s.approved]
        lines.append("Approved:")
        lines += [f"  {s.oem}" for s in approved] or ["  (none)"]
        lines.append("")
        lines.append("Configured manufacturers:")
        lines += [f"  {s.oem}" for s in approved if s.manufacturer_configured] or ["  (none)"]
        lines.append("")
        lines.append("Registered adapters:")
        lines += [f"  {s.oem}" for s in approved if s.adapter_registered] or ["  (none)"]
        lines.append("")
        lines.append("Scheduled:")
        lines += [f"  {s.oem}" for s in approved if s.scheduled] or ["  (none)"]
        lines.append("")
        mism = self.mismatches
        if not mism:
            lines.append("Mismatch:")
            lines.append("  NONE")
        else:
            for s in mism:
                lines.append("PRODUCTION SCOPE ERROR")
                lines.append("")
                lines.append(f"OEM: {s.oem}")
                lines.append("")
                lines.append(f"approved_in_scope: {str(s.approved).lower()}")
                lines.append(f"manufacturer_enabled: {str(s.manufacturer_configured).lower()}")
                lines.append(f"adapter_registered: {str(s.adapter_registered).lower()}")
                lines.append(f"config_enabled: {str(s.config_enabled).lower()}")
                lines.append(f"scheduled: {str(s.scheduled).lower()}")
                lines.append("")
        return "\n".join(lines)


class ProductionScopeError(RuntimeError):
    """Raised by runtime/daemon.py at startup when validate_production_scope()
    finds any approved OEM in an inconsistent state. Fail-closed by design —
    see docs/infra/PRODUCTION_SCOPE_AUDIT.md Part 4. Never degrade this to a
    warning; a mismatch here is exactly the Motorola incident's precondition."""


def validate_production_scope(settings) -> ScopeValidationResult:
    """The single fail-closed check: for every OEM in PRODUCTION_OEM_SCOPE,
    do settings.manufacturers, ADAPTER_REGISTRY, wave1.<oem>.enabled, and
    build_wave1_production_collectors() all agree? Used both by
    runtime/daemon.py at startup (refuses to start on mismatch) and by
    `main.py production validate` (read-only diagnostic)."""
    wave1_cfg = settings.get("wave1", default={}) or {}
    manufacturers = set(getattr(settings, "manufacturers", None) or settings.get("manufacturers", default=[]))
    scheduled_oems = {a.manufacturer for a in build_wave1_production_collectors(settings)}

    result = ScopeValidationResult()
    all_known = sorted(PRODUCTION_OEM_SCOPE | set(ADAPTER_REGISTRY.keys()))
    for oem in all_known:
        oem_cfg = wave1_cfg.get(oem, {}) or {}
        result.statuses.append(OEMScopeStatus(
            oem=oem,
            approved=oem in PRODUCTION_OEM_SCOPE,
            manufacturer_configured=oem in manufacturers,
            adapter_registered=oem in ADAPTER_REGISTRY,
            config_enabled=bool(oem_cfg.get("enabled", False)),
            scheduled=oem in scheduled_oems,
        ))
    return result


def assert_production_scope_or_refuse(settings) -> None:
    """Fail-closed startup gate — see runtime/daemon.py::main(). Raises
    ProductionScopeError (never a warning) if any approved OEM's gates
    disagree."""
    result = validate_production_scope(settings)
    if not result.ok:
        raise ProductionScopeError(
            "Refusing production startup — production scope mismatch:\n\n" + result.render()
        )



# Xiaomi is intentionally excluded from the shared intelligence pipeline in
# this phase — KEEP_STAGING per operator instruction (best identified source
# demonstrated unstable live 200/403 behavior within a single session; a
# blocked/unstable source is a source-quality problem, not something to
# integrate around). Its adapter and validator remain exercised, just never
# baselined into Device/Evidence/confidence.
INTEGRATED_OEMS = {"google", "oneplus", "nothing", "motorola", "honor", "oppo", "realme"}


def run_wave1_once(settings, session_factory, pipeline=None) -> dict:
    """
    Run every enabled Wave 1 adapter once. google/oneplus/nothing go through
    the full shared intelligence pipeline (see collectors/wave1/staging_pipeline.py);
    xiaomi is discovery-only (never baselined) per its KEEP_STAGING status.

    One OEM's adapter crashing must not prevent the others from running
    (spec section 62) — each OEM cycle is isolated in its own try/except.

    Returns {oem: OEMCycleResult|None} for callers/tests that want the numbers.
    """
    from collectors.wave1.staging_pipeline import run_oem_staging_cycle

    adapters = build_wave1_collectors(settings)
    if not adapters:
        logger.info("wave1: no adapters enabled/wired yet")
        return {}

    outcomes: dict = {}
    for adapter in adapters:
        oem = adapter.manufacturer
        try:
            if oem in INTEGRATED_OEMS:
                if pipeline is None:
                    raise ValueError("run_wave1_once requires `pipeline` to integrate google/oneplus/nothing")
                outcomes[oem] = run_oem_staging_cycle(adapter, pipeline, session_factory)
            else:
                results, metrics = adapter.discover()
                logger.info(
                    "wave1[quarantined:%s/%s]: %d candidates, %d fetched, %d failures "
                    "(discovery-only, not baselined into intelligence DB)",
                    oem, adapter.source_name,
                    len(results), metrics.pages_fetched, metrics.http_failures,
                )
                outcomes[oem] = None
        except Exception as e:
            logger.exception("wave1[%s]: cycle failed, other OEMs continue: %s", oem, e)
            outcomes[oem] = None
    return outcomes
