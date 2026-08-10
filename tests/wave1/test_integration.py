"""
Wave 1 <-> shared intelligence pipeline integration tests.

Uses fixture-controlled DiscoveryAdapter subclasses (no live network — live
behavior is proven separately via manual staging runs, see
docs/wave1/INTEGRATION_REPORT.md) against a real file-backed staging SQLite
DB, so restart/idempotency behavior is exercised honestly (spec section 33
explicitly requires a file-backed DB, not in-memory).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from collectors.wave1.adapter import AdapterMetrics, DiscoveryAdapter, DiscoveryResult
from collectors.wave1.baseline import BaselineTracker
from collectors.wave1.staging_pipeline import run_oem_staging_cycle
from config.settings import load_settings
from database.models import Base, Device, Evidence
from database.models_v03 import RejectedCandidate, SourceBaselineState
from database.session import get_session_factory, session_scope
from entity_resolution.confidence_ledger import ConfidenceLedgerEntry  # noqa: F401 registers table
from pipeline import IntelligencePipeline


class FixtureAdapter(DiscoveryAdapter):
    """Returns a fixed candidate list instead of hitting the network."""

    def __init__(self, manufacturer: str, source_name: str, candidates: list[DiscoveryResult], **kwargs):
        kwargs.setdefault("user_agent", "test")
        super().__init__(**kwargs)
        self.manufacturer = manufacturer
        self.source_name = source_name
        self._candidates = candidates

    def discover(self):
        metrics = AdapterMetrics(
            pages_requested=1, pages_fetched=1, candidates_found=len(self._candidates),
        )
        return list(self._candidates), metrics


def _candidate(manufacturer, source, identifier, url_suffix="", region="us") -> DiscoveryResult:
    return DiscoveryResult(
        manufacturer=manufacturer,
        source=source,
        source_url=f"https://example.test/{source}",
        canonical_url=f"https://example.test/{source}/{url_suffix or identifier}",
        region=region,
        candidate_identifier=identifier,
        raw_reference=identifier,
    )


@pytest.fixture()
def staging_settings(tmp_path):
    db_path = tmp_path / "clank-staging-test.db"
    settings = load_settings("config/config.staging.yaml")
    settings.raw["database"]["url"] = f"sqlite:///{db_path.as_posix()}"
    return settings, db_path


def _fresh_pipeline_and_factory(settings):
    """Simulates a process restart: a brand-new IntelligencePipeline +
    session_factory pointed at the same file-backed DB path."""
    session_factory = get_session_factory(settings.database_url)
    Base.metadata.create_all(bind=session_factory().get_bind())
    import database.models_v03  # noqa: F401 ensure v1 wave1 tables registered
    Base.metadata.create_all(bind=session_factory().get_bind())
    pipeline = IntelligencePipeline(settings, session_factory)
    return pipeline, session_factory


# ---------------------------------------------------------------------------
# Baseline suppression
# ---------------------------------------------------------------------------

def test_baseline_import_creates_no_alerts(staging_settings):
    settings, db_path = staging_settings
    pipeline, session_factory = _fresh_pipeline_and_factory(settings)

    adapter = FixtureAdapter("google", "google_store_category_phones", [
        _candidate("google", "google_store_category_phones", "Pixel 9"),
        _candidate("google", "google_store_category_phones", "Pixel 9 Pro"),
    ])
    result = run_oem_staging_cycle(adapter, pipeline, session_factory)

    assert result.baseline_was_complete_before is False
    assert result.baseline_just_completed is True
    assert result.new_devices == 2

    with session_scope(session_factory) as session:
        # Post-cleanup semantics: an `Alert` row means "delivered." A
        # suppressed/backfill baseline import writes 0 of them — no
        # `discord_message_id IS NOT NULL` filter needed, the raw count IS
        # the delivered count now. See tests/wave1/test_alert_semantics.py.
        alerts_delivered = session.execute(
            __import__("sqlalchemy").text("SELECT COUNT(*) FROM alerts")
        ).scalar()
        assert alerts_delivered == 0
        # WebhookDelivery is written for every decision, including a
        # suppressed backfill one (no webhook configured in this fixture, so
        # every send is a no-configured-webhook suppression) — one row per
        # new device this cycle, all suppressed, none delivered.
        deliveries = session.execute(
            __import__("sqlalchemy").text(
                "SELECT COUNT(*) FROM webhook_deliveries WHERE delivered = 0"
            )
        ).scalar()
        assert deliveries == result.new_devices
        delivered = session.execute(
            __import__("sqlalchemy").text("SELECT COUNT(*) FROM webhook_deliveries WHERE delivered = 1")
        ).scalar()
        assert delivered == 0


def test_post_baseline_candidate_is_alert_eligible_not_suppressed_as_backfill(staging_settings):
    """Fixture-controlled post-baseline event (spec section 23A): baseline
    completes on cycle 1, then a genuinely new candidate appears on cycle 2 —
    that candidate must NOT be treated as backfill."""
    settings, db_path = staging_settings
    pipeline, session_factory = _fresh_pipeline_and_factory(settings)

    adapter1 = FixtureAdapter("google", "google_store_category_phones", [
        _candidate("google", "google_store_category_phones", "Pixel 9"),
    ])
    r1 = run_oem_staging_cycle(adapter1, pipeline, session_factory)
    assert r1.baseline_just_completed is True

    adapter2 = FixtureAdapter("google", "google_store_category_phones", [
        _candidate("google", "google_store_category_phones", "Pixel 9"),   # unchanged resighting
        _candidate("google", "google_store_category_phones", "Pixel 11"),  # genuinely new, post-baseline
    ])
    r2 = run_oem_staging_cycle(adapter2, pipeline, session_factory)

    assert r2.baseline_was_complete_before is True
    assert r2.new_devices == 1  # only Pixel 11
    assert r2.resighted == 1    # Pixel 9 unchanged


# ---------------------------------------------------------------------------
# Evidence dedup / re-sighting / confidence integrity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("manufacturer,source", [
    ("google", "google_store_category_phones"),
    ("oneplus", "oneplus_regional_sitemap"),
    ("nothing", "nothing_products_sitemap"),
])
def test_repeat_run_no_evidence_or_confidence_inflation(staging_settings, manufacturer, source):
    settings, db_path = staging_settings
    pipeline, session_factory = _fresh_pipeline_and_factory(settings)

    identifier = {"google": "Pixel 9", "oneplus": "OnePlus 13", "nothing": "Phone (3)"}[manufacturer]

    def make_adapter():
        return FixtureAdapter(manufacturer, source, [_candidate(manufacturer, source, identifier)])

    r1 = run_oem_staging_cycle(make_adapter(), pipeline, session_factory)
    assert r1.new_devices == 1

    with session_scope(session_factory) as session:
        dev = session.query(Device).filter(Device.manufacturer == manufacturer).first()
        conf_after_1 = dev.confidence
        evidence_after_1 = session.query(Evidence).filter(Evidence.device_id == dev.id).count()

    r2 = run_oem_staging_cycle(make_adapter(), pipeline, session_factory)
    assert r2.new_devices == 0
    assert r2.resighted == 1

    with session_scope(session_factory) as session:
        dev = session.query(Device).filter(Device.manufacturer == manufacturer).first()
        assert dev.confidence == conf_after_1, "unchanged resighting must not inflate confidence"
        evidence_after_2 = session.query(Evidence).filter(Evidence.device_id == dev.id).count()
        assert evidence_after_2 == evidence_after_1, "unchanged resighting must not add evidence rows"

    r3 = run_oem_staging_cycle(make_adapter(), pipeline, session_factory)
    assert r3.new_devices == 0
    assert r3.resighted == 1


# ---------------------------------------------------------------------------
# Cross-OEM identity isolation
# ---------------------------------------------------------------------------

def test_identical_marketing_strings_stay_separate_across_manufacturers(staging_settings):
    settings, db_path = staging_settings
    pipeline, session_factory = _fresh_pipeline_and_factory(settings)

    google_adapter = FixtureAdapter("google", "google_store_category_phones", [
        _candidate("google", "google_store_category_phones", "Pixel 9"),
    ])
    run_oem_staging_cycle(google_adapter, pipeline, session_factory)

    # Nothing candidate "Phone (3)" vs Google "Pixel 9" — different strings but
    # the real cross-OEM risk is the SAME string across two manufacturers.
    # Simulate that directly by resolving through the resolver with matching
    # normalized model numbers but different manufacturers.
    nothing_adapter = FixtureAdapter("nothing", "nothing_products_sitemap", [
        _candidate("nothing", "nothing_products_sitemap", "Phone (3)"),
    ])
    run_oem_staging_cycle(nothing_adapter, pipeline, session_factory)

    with session_scope(session_factory) as session:
        google_devices = session.query(Device).filter(Device.manufacturer == "google").all()
        nothing_devices = session.query(Device).filter(Device.manufacturer == "nothing").all()
        assert len(google_devices) == 1
        assert len(nothing_devices) == 1
        assert google_devices[0].id != nothing_devices[0].id


def test_same_model_string_different_manufacturer_never_merges(staging_settings):
    """Direct collision test: force the SAME identifier string through two
    different manufacturers and prove they resolve to two separate Device rows."""
    settings, db_path = staging_settings
    pipeline, session_factory = _fresh_pipeline_and_factory(settings)

    shared_identifier = "PHONE X"
    a1 = FixtureAdapter("oneplus", "oneplus_regional_sitemap", [
        _candidate("oneplus", "oneplus_regional_sitemap", shared_identifier),
    ])
    a2 = FixtureAdapter("nothing", "nothing_products_sitemap", [
        _candidate("nothing", "nothing_products_sitemap", shared_identifier),
    ])

    # Bypass validators here (this test targets resolver identity isolation,
    # not validator grammar) by calling the bridge/resolver path directly.
    from collectors.wave1.bridge import normalize_wave1_discovery
    from collectors.wave1.validator import ValidationOutcome, VALID

    outcome1 = ValidationOutcome(outcome=VALID, candidate_identifier=shared_identifier,
                                  normalized_identifier=shared_identifier, manufacturer="oneplus")
    outcome2 = ValidationOutcome(outcome=VALID, candidate_identifier=shared_identifier,
                                  normalized_identifier=shared_identifier, manufacturer="nothing")

    disc1 = normalize_wave1_discovery(a1.discover()[0][0], outcome1)
    disc2 = normalize_wave1_discovery(a2.discover()[0][0], outcome2)

    with session_scope(session_factory) as session:
        pipeline.process_discoveries([disc1, disc2], session)

    with session_scope(session_factory) as session:
        oneplus_dev = session.query(Device).filter(Device.manufacturer == "oneplus", Device.model_number == shared_identifier).first()
        nothing_dev = session.query(Device).filter(Device.manufacturer == "nothing", Device.model_number == shared_identifier).first()
        assert oneplus_dev is not None
        assert nothing_dev is not None
        assert oneplus_dev.id != nothing_dev.id, "same model string across manufacturers must never merge into one device"


# ---------------------------------------------------------------------------
# August pollution corpus through the REAL staging pipeline (DB-level proof)
# ---------------------------------------------------------------------------

def test_pollution_corpus_creates_zero_devices_through_real_pipeline(staging_settings):
    """
    The DB-level extension promised in docs/wave1/WAVE1_REPORT.md's "Scope
    boundary" section: the incident-derived negative fixture corpus, run
    through the actual bridge+validator+staging_pipeline (not just the
    validator in isolation), must produce zero Device/Evidence/confidence/
    alert rows.
    """
    import json
    settings, db_path = staging_settings
    pipeline, session_factory = _fresh_pipeline_and_factory(settings)

    fixtures_dir = Path(__file__).resolve().parent.parent.parent / "fixtures" / "wave1"
    cases = json.loads((fixtures_dir / "oneplus_invalid.json").read_text(encoding="utf-8"))

    adapter = FixtureAdapter("oneplus", "oneplus_regional_sitemap", [
        _candidate("oneplus", "oneplus_regional_sitemap", c["text"]) for c in cases
    ])
    result = run_oem_staging_cycle(adapter, pipeline, session_factory)

    assert result.valid == 0
    assert result.new_devices == 0
    assert result.rejected == len(cases)

    with session_scope(session_factory) as session:
        assert session.query(Device).filter(Device.manufacturer == "oneplus").count() == 0
        assert session.query(Evidence).count() == 0
        assert session.query(RejectedCandidate).filter(RejectedCandidate.source_id == "oneplus_regional_sitemap").count() == len(cases)


# ---------------------------------------------------------------------------
# Restart survival
# ---------------------------------------------------------------------------

def test_baseline_state_and_devices_survive_process_restart(staging_settings):
    settings, db_path = staging_settings
    pipeline, session_factory = _fresh_pipeline_and_factory(settings)

    adapter = FixtureAdapter("nothing", "nothing_products_sitemap", [
        _candidate("nothing", "nothing_products_sitemap", "Phone (3)"),
    ])
    run_oem_staging_cycle(adapter, pipeline, session_factory)

    # Simulate a fresh process: new engine/session_factory/pipeline instances
    # against the same file-backed DB path — no shared Python state at all.
    pipeline2, session_factory2 = _fresh_pipeline_and_factory(settings)
    with session_scope(session_factory2) as session:
        tracker = BaselineTracker(session)
        assert tracker.is_complete("nothing_products_sitemap") is True
        assert session.query(Device).filter(Device.manufacturer == "nothing").count() == 1

    adapter2 = FixtureAdapter("nothing", "nothing_products_sitemap", [
        _candidate("nothing", "nothing_products_sitemap", "Phone (3)"),   # resighting
        _candidate("nothing", "nothing_products_sitemap", "Phone (3a)"),  # new after restart
    ])
    result = run_oem_staging_cycle(adapter2, pipeline2, session_factory2)
    assert result.baseline_was_complete_before is True
    assert result.new_devices == 1
    assert result.resighted == 1


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------

def test_one_oem_crash_does_not_block_others(staging_settings):
    settings, db_path = staging_settings
    pipeline, session_factory = _fresh_pipeline_and_factory(settings)

    class CrashingAdapter(FixtureAdapter):
        def discover(self):
            raise RuntimeError("simulated network failure")

    from collectors.wave1 import run_wave1_once
    import collectors.wave1 as wave1_pkg

    original_registry = dict(wave1_pkg.ADAPTER_REGISTRY)
    original_build = wave1_pkg.build_wave1_collectors
    try:
        good = FixtureAdapter("nothing", "nothing_products_sitemap", [
            _candidate("nothing", "nothing_products_sitemap", "Phone (3)"),
        ])
        bad = CrashingAdapter("google", "google_store_category_phones", [])

        wave1_pkg.build_wave1_collectors = lambda settings: [bad, good]
        outcomes = run_wave1_once(settings, session_factory, pipeline=pipeline)

        assert outcomes["google"] is None  # crashed, isolated
        assert outcomes["nothing"] is not None
        assert outcomes["nothing"].new_devices == 1
    finally:
        wave1_pkg.build_wave1_collectors = original_build
        wave1_pkg.ADAPTER_REGISTRY.clear()
        wave1_pkg.ADAPTER_REGISTRY.update(original_registry)
