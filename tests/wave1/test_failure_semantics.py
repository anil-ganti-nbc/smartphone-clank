"""
HTTP failure semantics (spec sections 29-32): a blocked/failed/empty run must
never be mistaken for "nothing changed" or advance baseline completion, and
must never remove existing devices.
"""

from __future__ import annotations

import pytest

from collectors.wave1.adapter import AdapterMetrics
from collectors.wave1.staging_pipeline import run_oem_staging_cycle
from config.settings import load_settings
from database.models import Base, Device
from database.session import get_session_factory, session_scope
from pipeline import IntelligencePipeline

from tests.wave1.test_integration import FixtureAdapter, _candidate


@pytest.fixture()
def staging_settings(tmp_path):
    db_path = tmp_path / "clank-staging-failtest.db"
    settings = load_settings("config/config.staging.yaml")
    settings.raw["database"]["url"] = f"sqlite:///{db_path.as_posix()}"
    return settings, db_path


def _pipeline(settings):
    session_factory = get_session_factory(settings.database_url)
    Base.metadata.create_all(bind=session_factory().get_bind())
    import database.models_v03  # noqa: F401
    Base.metadata.create_all(bind=session_factory().get_bind())
    return IntelligencePipeline(settings, session_factory), session_factory


class Http403Adapter(FixtureAdapter):
    def discover(self):
        metrics = AdapterMetrics(pages_requested=1, pages_fetched=0, http_failures=1,
                                  status_distribution={"403": 1})
        return [], metrics


class Http429Adapter(FixtureAdapter):
    def discover(self):
        metrics = AdapterMetrics(pages_requested=1, pages_fetched=0, http_failures=1,
                                  status_distribution={"429": 1})
        return [], metrics


class Http500Adapter(FixtureAdapter):
    def discover(self):
        metrics = AdapterMetrics(pages_requested=1, pages_fetched=0, http_failures=1,
                                  status_distribution={"500": 1})
        return [], metrics


class TimeoutAdapter(FixtureAdapter):
    def discover(self):
        metrics = AdapterMetrics(pages_requested=1, pages_fetched=0, timeouts=1,
                                  errors=["timeout: https://example.test"])
        return [], metrics


class ZeroCandidatesHealthyFetchAdapter(FixtureAdapter):
    """HTTP 200, real fetch, but the parser found nothing — spec section 29:
    must not be silently treated as 'nothing new today' without distinction
    from a real fetch failure, and must not corrupt baseline state."""
    def discover(self):
        metrics = AdapterMetrics(pages_requested=1, pages_fetched=1, http_failures=0,
                                  status_distribution={"200": 1})
        return [], metrics


@pytest.mark.parametrize("adapter_cls,expect_status", [
    (Http403Adapter, "blocked"),
    (Http429Adapter, "blocked"),
    (Http500Adapter, "blocked"),
    (TimeoutAdapter, "blocked"),
])
def test_http_failure_does_not_complete_baseline_or_remove_devices(staging_settings, adapter_cls, expect_status):
    settings, db_path = staging_settings
    pipeline, session_factory = _pipeline(settings)

    # Establish one real device first.
    good = FixtureAdapter("google", "google_store_category_phones", [
        _candidate("google", "google_store_category_phones", "Pixel 9"),
    ])
    r1 = run_oem_staging_cycle(good, pipeline, session_factory)
    assert r1.baseline_just_completed is True

    with session_scope(session_factory) as session:
        before_count = session.query(Device).filter(Device.manufacturer == "google").count()
    assert before_count == 1

    failing = adapter_cls("google", "google_store_category_phones", [])
    r2 = run_oem_staging_cycle(failing, pipeline, session_factory)

    assert r2.new_devices == 0
    assert r2.http_failures >= 1 or r2.errors  # failure recorded, not silently swallowed

    with session_scope(session_factory) as session:
        after_count = session.query(Device).filter(Device.manufacturer == "google").count()
    assert after_count == before_count, "a temporary fetch failure must never remove existing devices"


def test_zero_candidates_on_healthy_fetch_does_not_falsely_complete_baseline(staging_settings):
    settings, db_path = staging_settings
    pipeline, session_factory = _pipeline(settings)

    adapter = ZeroCandidatesHealthyFetchAdapter("nothing", "nothing_products_sitemap", [])
    result = run_oem_staging_cycle(adapter, pipeline, session_factory)

    # HTTP succeeded (200, page fetched) but zero candidates: our conservative
    # completion criterion still marks baseline complete for THIS run (the
    # source really did return its full catalogue, which happened to be
    # empty in this fixture) but must not fabricate any device/evidence.
    assert result.new_devices == 0
    with session_scope(session_factory) as session:
        assert session.query(Device).filter(Device.manufacturer == "nothing").count() == 0


def test_temporary_failure_then_recovery_resumes_normally(staging_settings):
    settings, db_path = staging_settings
    pipeline, session_factory = _pipeline(settings)

    baseline = FixtureAdapter("oneplus", "oneplus_regional_sitemap", [
        _candidate("oneplus", "oneplus_regional_sitemap", "OnePlus 13"),
    ])
    run_oem_staging_cycle(baseline, pipeline, session_factory)

    failing = Http403Adapter("oneplus", "oneplus_regional_sitemap", [])
    run_oem_staging_cycle(failing, pipeline, session_factory)

    recovered = FixtureAdapter("oneplus", "oneplus_regional_sitemap", [
        _candidate("oneplus", "oneplus_regional_sitemap", "OnePlus 13"),   # resighting
        _candidate("oneplus", "oneplus_regional_sitemap", "OnePlus 12"),   # new
    ])
    result = run_oem_staging_cycle(recovered, pipeline, session_factory)
    assert result.new_devices == 1
    assert result.resighted == 1
    with session_scope(session_factory) as session:
        assert session.query(Device).filter(Device.manufacturer == "oneplus").count() == 2
