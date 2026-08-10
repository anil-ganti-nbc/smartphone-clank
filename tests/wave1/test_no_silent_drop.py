"""
Scope-unification phase: reproduces the exact Motorola incident
(docs/wave2/MOTOROLA_CANARY_REPORT.md) end-to-end through the real staging
pipeline and proves it can no longer produce a false-complete baseline.

Before this phase: a manufacturer missing from settings.manufacturers
caused pipeline.process_discoveries() to silently drop every discovery,
while collectors/wave1/staging_pipeline.py::run_oem_staging_cycle() still
marked the source's baseline complete (because the fetch succeeded and
candidates validated fine — the drop happened one layer downstream,
invisibly). The next run would then treat every "already seen" device as
genuinely new and fire real newsroom alerts for devices never actually
persisted.

After this phase: process_discoveries() reports dropped_out_of_scope, and
run_oem_staging_cycle() refuses to mark baseline complete whenever
validated candidates existed but nothing was accepted — see
docs/infra/PRODUCTION_SCOPE_AUDIT.md Part 5/6.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from collectors.wave1.adapter import AdapterMetrics, DiscoveryAdapter, DiscoveryResult
from collectors.wave1.staging_pipeline import run_oem_staging_cycle
from config.settings import load_settings
from database.models import Base
from database.session import get_session_factory, session_scope
from pipeline import IntelligencePipeline

import database.models_v03  # noqa: F401


class _FixtureAdapter(DiscoveryAdapter):
    def __init__(self, manufacturer, source_name, candidates, **kwargs):
        kwargs.setdefault("user_agent", "test")
        super().__init__(**kwargs)
        self.manufacturer = manufacturer
        self.source_name = source_name
        self._candidates = candidates

    def discover(self):
        metrics = AdapterMetrics(pages_requested=1, pages_fetched=1, candidates_found=len(self._candidates))
        return list(self._candidates), metrics


def _cand(m, s, i):
    return DiscoveryResult(
        manufacturer=m, source=s, source_url=f"https://example.test/{s}",
        canonical_url=f"https://example.test/{s}/{i}", region="us",
        candidate_identifier=i, raw_reference=i,
    )


def _build_pipeline(db_name, manufacturers):
    import tempfile
    settings = load_settings("config/config.staging.yaml")
    db_path = Path(tempfile.mkdtemp()) / db_name
    settings.raw["database"]["url"] = f"sqlite:///{db_path.as_posix()}"
    settings.raw["manufacturers"] = manufacturers
    settings.raw.setdefault("discord", {})["enabled"] = False

    session_factory = get_session_factory(settings.database_url)
    Base.metadata.create_all(bind=session_factory().get_bind())
    return IntelligencePipeline(settings, session_factory), session_factory


def test_manufacturer_missing_from_settings_prevents_false_baseline_completion():
    # settings.manufacturers deliberately omits "motorola" — the exact
    # incident precondition — even though the adapter/validator both
    # produce real, valid candidates.
    pipeline, session_factory = _build_pipeline(
        "no-silent-drop-incident.db",
        manufacturers=["samsung", "google", "oneplus", "nothing", "xiaomi"],  # motorola OMITTED
    )

    candidates = [
        _cand("motorola", "motorola_regional_sitemap", "Razr 2026"),
        _cand("motorola", "motorola_regional_sitemap", "Moto G Power 2026"),
    ]
    r = run_oem_staging_cycle(
        _FixtureAdapter("motorola", "motorola_regional_sitemap", candidates),
        pipeline, session_factory,
    )

    assert r.valid == 2, "candidates must still validate fine — the bug is downstream of validation"
    assert r.dropped_out_of_scope == 2, "both candidates must be visibly reported as dropped"
    assert r.new_devices == 0
    assert r.updated_devices == 0
    assert r.resighted == 0
    assert r.baseline_just_completed is False, (
        "THE FIX: baseline must not complete when validated candidates existed "
        "but the pipeline accepted none of them"
    )

    with session_scope(session_factory) as session:
        device_count = session.execute(
            text("SELECT COUNT(*) FROM devices WHERE manufacturer='motorola'")
        ).scalar()
        alerts = session.execute(text("SELECT COUNT(*) FROM alerts")).scalar()
    assert device_count == 0, "zero devices must be persisted — nothing to falsely claim as baselined"
    assert alerts == 0

    # A second cycle with the misconfiguration still in place: baseline
    # still not marked complete (proves this isn't a one-time miss, it's a
    # stable refusal), and still zero devices — no drift, no partial state.
    r2 = run_oem_staging_cycle(
        _FixtureAdapter("motorola", "motorola_regional_sitemap", candidates),
        pipeline, session_factory,
    )
    assert r2.baseline_just_completed is False
    assert r2.dropped_out_of_scope == 2
    with session_scope(session_factory) as session:
        device_count = session.execute(
            text("SELECT COUNT(*) FROM devices WHERE manufacturer='motorola'")
        ).scalar()
    assert device_count == 0


def test_fixing_the_manufacturer_list_allows_a_correct_baseline():
    """Once settings.manufacturers is corrected (the actual fix applied in
    docs/wave2/MOTOROLA_CANARY_REPORT.md), the same candidates baseline
    normally — proving the fix doesn't just refuse forever, it recovers
    cleanly once the misconfiguration is corrected."""
    pipeline, session_factory = _build_pipeline(
        "no-silent-drop-fixed.db",
        manufacturers=["samsung", "google", "oneplus", "nothing", "xiaomi", "motorola"],
    )

    candidates = [
        _cand("motorola", "motorola_regional_sitemap", "Razr 2026"),
        _cand("motorola", "motorola_regional_sitemap", "Moto G Power 2026"),
    ]
    r = run_oem_staging_cycle(
        _FixtureAdapter("motorola", "motorola_regional_sitemap", candidates),
        pipeline, session_factory,
    )

    assert r.dropped_out_of_scope == 0
    assert r.new_devices == 2
    assert r.baseline_just_completed is True

    with session_scope(session_factory) as session:
        device_count = session.execute(
            text("SELECT COUNT(*) FROM devices WHERE manufacturer='motorola'")
        ).scalar()
        alerts = session.execute(text("SELECT COUNT(*) FROM alerts")).scalar()
    assert device_count == 2
    assert alerts == 0  # correctly backfill-suppressed


def test_legitimate_zero_new_devices_does_not_trip_the_silent_drop_check():
    """The invariant must not be "at least one NEW device" — a fully
    resighted, already-baselined catalogue producing zero new/updated
    devices is normal and must not be flagged as a regression."""
    pipeline, session_factory = _build_pipeline(
        "no-silent-drop-legitimate-resight.db",
        manufacturers=["samsung", "google", "oneplus", "nothing", "xiaomi", "motorola"],
    )
    candidates = [_cand("motorola", "motorola_regional_sitemap", "Razr 2026")]

    r1 = run_oem_staging_cycle(
        _FixtureAdapter("motorola", "motorola_regional_sitemap", candidates),
        pipeline, session_factory,
    )
    assert r1.baseline_just_completed is True

    # Same candidate again — resighting only, zero new/updated. This must
    # NOT be treated as a silent drop even though new+updated == 0, because
    # resighted > 0 proves the pipeline is actually processing it.
    r2 = run_oem_staging_cycle(
        _FixtureAdapter("motorola", "motorola_regional_sitemap", candidates),
        pipeline, session_factory,
    )
    assert r2.new_devices == 0
    assert r2.updated_devices == 0
    assert r2.resighted == 1
    assert r2.dropped_out_of_scope == 0
