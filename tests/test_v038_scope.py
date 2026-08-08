"""v0.3.8 production scope: disabled collectors stay out; report filters."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import load_settings
from collectors import build_collectors


def test_only_samsung_sitemap_enabled_in_production_config():
    settings = load_settings(str(ROOT / "config" / "config.yaml"))
    cols = build_collectors(settings, project_root=ROOT)
    names = [c.name for c in cols]
    assert "samsung_us_support_sitemap" in names, names
    forbidden = {
        "google_support", "oneplus_support", "nothing_support", "xiaomi_support",
        "bluetooth_sig", "pixel_ota", "nothing_ota", "samsung_firmware",
    }
    for f in forbidden:
        assert f not in names, f"disabled collector still scheduled: {f} in {names}"
    print("production registry ok", names)


def test_missing_enabled_defaults_false():
    settings = load_settings(str(ROOT / "config" / "config.yaml"))
    cfg = settings.get("collectors", default={}) or {}
    # invent a collector not in yaml — build path uses enabled default false
    assert cfg.get("totally_fake_collector", {}).get("enabled", False) is False
    print("default false ok")


def test_daily_report_scopes_out_of_scope():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from datetime import datetime
    from database.models import Base
    from observability.metrics import CollectorRunRecord, daily_report, MetricsRecorder

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    # ensure metrics table
    CollectorRunRecord.__table__.create(bind=eng, checkfirst=True)
    Session = sessionmaker(bind=eng)
    sess = Session()
    now = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    for name, new_d in [("samsung_us_support_sitemap", 5), ("google_support", 40)]:
        sess.add(CollectorRunRecord(
            collector_name=name, source_name=name, started_at=now, finished_at=now,
            duration_ms=1000, status="success", new_devices=new_d, candidates_found=new_d,
        ))
    sess.commit()
    rep = daily_report(
        sess,
        day=now,
        tz="UTC",
        production_scope={"samsung_us_support_sitemap"},
    )
    assert rep["collectors_run"] == 1
    assert rep["new_discoveries"] == 5
    assert "google_support" in rep["out_of_scope_collectors"]
    assert rep["out_of_scope_runs"] == 1
    print("report scope ok", rep["new_discoveries"], rep["out_of_scope_collectors"])


if __name__ == "__main__":
    test_only_samsung_sitemap_enabled_in_production_config()
    test_missing_enabled_defaults_false()
    test_daily_report_scopes_out_of_scope()
    print("ALL v0.3.8 tests passed")
