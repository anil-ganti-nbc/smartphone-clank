"""Tests for runtime/run_once.py's due-check logic -- the replacement for
APScheduler's IntervalTrigger under the one-shot cloud-migration model.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import Base
from observability.metrics import CollectorRunRecord, MetricsRecorder
from runtime.run_once import build_targets, is_due


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_collector_with_no_recorded_run_is_due_immediately():
    session = _session()
    assert is_due(session, "never_run_collector", interval_minutes=180) is True


def test_collector_run_recently_is_not_due():
    session = _session()
    rec = MetricsRecorder(session)
    ctx = rec.start("fresh_collector")
    ctx.started_at = datetime.utcnow()
    m = rec.finish(ctx)
    m.started_at = ctx.started_at
    session.commit()

    assert is_due(session, "fresh_collector", interval_minutes=180) is False


def test_collector_run_past_interval_is_due():
    session = _session()
    rec = MetricsRecorder(session)
    ctx = rec.start("stale_collector")
    ctx.started_at = datetime.utcnow() - timedelta(minutes=200)
    m = rec.finish(ctx)
    m.started_at = ctx.started_at
    session.commit()

    assert is_due(session, "stale_collector", interval_minutes=180) is True


def test_due_check_is_per_collector_not_global():
    session = _session()
    rec = MetricsRecorder(session)
    ctx = rec.start("recently_run")
    ctx.started_at = datetime.utcnow()
    m = rec.finish(ctx)
    m.started_at = ctx.started_at
    session.commit()

    assert is_due(session, "recently_run", interval_minutes=180) is False
    assert is_due(session, "some_other_collector", interval_minutes=180) is True


def test_failed_run_still_counts_for_due_check_no_special_retry():
    """A failed attempt still records a CollectorRunRecord (status=failed);
    run_once.py does not implement its own retry -- the collector simply
    remains subject to the same interval as a successful run, matching
    the resilience the old IntervalTrigger always provided (it never
    retried failed jobs faster than the interval either)."""
    session = _session()
    rec = MetricsRecorder(session)
    ctx = rec.start("flaky_collector")
    ctx.started_at = datetime.utcnow()
    ctx.status = "failed"
    m = rec.finish(ctx)
    m.started_at = ctx.started_at
    session.commit()

    assert is_due(session, "flaky_collector", interval_minutes=180) is False


def test_production_targets_include_every_current_source_and_cadence():
    from config.settings import load_settings

    settings = load_settings("config/config.yaml")
    targets = build_targets(settings, object(), lambda: None)
    assert {target.source_id: target.interval_minutes for target in targets} == {
        "samsung_us_support_sitemap": 180,
        "google_store_category_phones": 45,
        "nothing_products_sitemap": 90,
        "oneplus_regional_sitemap": 90,
        "motorola_regional_sitemap": 360,
        "honor_global_sitemap": 360,
        "oppo_global_sitemap": 360,
        "realme_regional_sitemap": 360,
    }


def test_target_builder_keeps_scheduled_default_and_allows_manual_reason(monkeypatch):
    from config.settings import load_settings

    settings = load_settings("config/config.yaml")
    reasons = []

    class Pipeline:
        def run_collector(self, collector, run_reason):
            reasons.append(run_reason)

    scheduled = build_targets(settings, Pipeline(), lambda: None)
    scheduled[0].run()
    manual = build_targets(
        settings, Pipeline(), lambda: None, run_reason="field_test_manual"
    )
    manual[0].run()

    assert reasons == ["production_scheduled", "field_test_manual"]
