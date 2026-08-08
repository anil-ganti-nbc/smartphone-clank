"""v0.3.9 production scope lock, run provenance, and report integrity tests."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collectors import build_collectors, production_scope, _eligible
from config.settings import Settings, load_settings
from database.models import Base
from observability.metrics import MetricsRecorder, CollectorRunRecord, daily_report, _day_bounds_utc


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_production_scope_defaults_samsung_only():
    settings = load_settings("config/config.yaml")
    scope = production_scope(settings, project_root=ROOT)
    assert scope is not None
    assert "samsung_us_support_sitemap" in scope
    assert "google_support" not in scope
    assert "bluetooth_sig" not in scope
    print("production_scope defaults samsung-only: ok")


def test_config_regression_cannot_reenable_oem_collector():
    settings = load_settings("config/config.yaml")
    settings.raw.setdefault("collectors", {})["google_support"] = {"enabled": True}
    cols = build_collectors(settings, project_root=ROOT)
    assert not any("google" in c.name for c in cols)
    print("config regression blocked: ok")


def test_eligible_fails_closed_on_missing_config():
    ok, reason = _eligible("some_collector", cfg=None, scope={"some_collector"})
    assert ok is False
    assert reason == "no_config_entry"
    print("fail-closed on missing config: ok")


def test_eligible_fails_closed_out_of_scope():
    ok, reason = _eligible("google_support", cfg={"enabled": True}, scope={"samsung_us_support_sitemap"})
    assert ok is False
    assert reason == "out_of_production_scope"
    print("fail-closed out of scope: ok")


def test_config_local_overlay_deep_merge():
    import yaml
    local_path = ROOT / "config" / "config.local.yaml"
    assert not local_path.exists(), "test requires no local overlay present"
    s1 = Settings(config_path="config/config.yaml").load()
    assert s1.local_config_loaded is None
    baseline_discord_enabled = s1.get("discord", "enabled")

    local_path.write_text("collectors:\n  samsung_support:\n    enabled: true\n", encoding="utf-8")
    try:
        s2 = Settings(config_path="config/config.yaml").load()
        assert s2.local_config_loaded is not None
        assert s2.get("collectors", "samsung_support", default={}).get("enabled") is True
        assert s2.get("discord", "enabled") == baseline_discord_enabled  # base untouched
    finally:
        local_path.unlink()
    print("config.local.yaml deep merge: ok")


def test_health_score_out_of_scope_is_na():
    session = _session()
    rec = MetricsRecorder(session)
    ctx = rec.start("google_support", run_reason="production_manual")
    ctx.status = "success"
    rec.finish(ctx)
    session.commit()
    h = rec.health_score("google_support", in_scope=False)
    assert h["score"] is None
    assert h["label"] == "N/A"
    print("out-of-scope health N/A: ok")


def test_health_score_needs_run_history_for_healthy():
    session = _session()
    rec = MetricsRecorder(session)
    ctx = rec.start("samsung_us_support_sitemap", run_reason="production_manual")
    ctx.status = "success"
    rec.finish(ctx)
    session.commit()
    h = rec.health_score("samsung_us_support_sitemap", in_scope=True)
    assert h["score"] == 100
    assert h["label"] != "Healthy"  # single run — provisional, not proven healthy
    print("single-run not auto-healthy: ok")


def test_run_reason_defaults():
    session = _session()
    rec = MetricsRecorder(session)
    ctx = rec.start("samsung_us_support_sitemap")  # no run_reason passed
    assert ctx.run_reason == "production_manual"
    ctx2 = rec.start("samsung_us_support_sitemap", run_reason="production_scheduled")
    assert ctx2.run_reason == "production_scheduled"
    print("run_reason defaults: ok")


def test_daily_report_ist_day_boundary():
    session = _session()
    rec = MetricsRecorder(session)
    # 2026-08-08 19:00 UTC = 2026-08-09 00:30 IST -> belongs to the *next* IST day
    ctx = rec.start("samsung_us_support_sitemap", run_reason="production_manual")
    ctx.status = "success"
    m = rec.finish(ctx)
    m.started_at = datetime(2026, 8, 8, 19, 0, 0)
    session.commit()

    scope = {"samsung_us_support_sitemap"}
    rep_aug8 = daily_report(session, datetime(2026, 8, 8, 12, 0, 0), tz="Asia/Kolkata", production_scope=scope)
    rep_aug9 = daily_report(session, datetime(2026, 8, 9, 12, 0, 0), tz="Asia/Kolkata", production_scope=scope)
    assert rep_aug8["total_runs"] == 0
    assert rep_aug9["total_runs"] == 1
    print("IST day boundary: ok")


def test_daily_report_uses_webhook_delivery_not_alerts_sent():
    session = _session()
    from database.models import WebhookDelivery
    rec = MetricsRecorder(session)
    ctx = rec.start("samsung_us_support_sitemap", run_reason="production_manual")
    ctx.status = "success"
    ctx.alerts_sent = 999  # deliberately wrong — report must not read this
    rec.finish(ctx)
    session.add(WebhookDelivery(
        channel="newsroom", reason="new_model", test_mode=False,
        eligible=True, suppressed=False, attempted=True, delivered=True,
    ))
    session.commit()

    scope = {"samsung_us_support_sitemap"}
    rep = daily_report(session, datetime.utcnow(), tz="UTC", production_scope=scope)
    assert rep["newsroom_alerts"]["delivered"] == 1
    assert "alerts_sent" not in rep
    print("report sources alerts from WebhookDelivery: ok")


def test_baseline_runs_excluded_from_headline():
    session = _session()
    rec = MetricsRecorder(session)
    ctx = rec.start("samsung_us_support_sitemap", run_reason="demo")
    ctx.status = "success"
    ctx.new_devices = 5
    rec.finish(ctx)
    session.commit()

    scope = {"samsung_us_support_sitemap"}
    rep = daily_report(session, datetime.utcnow(), tz="UTC", production_scope=scope)
    assert rep["new_discoveries"] == 0
    assert rep["baseline_or_nonproduction_runs"] == 1
    print("demo/baseline runs excluded from headline: ok")


def run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
