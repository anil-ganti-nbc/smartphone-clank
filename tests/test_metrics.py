"""Observability / metrics tests — offline fixtures only."""

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
from observability.metrics import (
    MetricsRecorder,
    CollectorRunRecord,
    daily_report,
    format_daily_report_md,
)


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_healthy(rec: MetricsRecorder, n: int = 10, candidates: int = 10):
    for i in range(n):
        ctx = rec.start("test_collector")
        ctx.status = "success"
        ctx.pages_fetched = 5
        ctx.http_requests = 5
        ctx.candidates_found = candidates
        ctx.valid_devices = candidates - 1
        r = rec.finish(ctx)
        r.duration_ms = 1000 + i * 10
        r.started_at = datetime.utcnow() - timedelta(hours=n - i)


def test_record_immutable_runs():
    s = _session()
    rec = MetricsRecorder(s)
    ctx = rec.start("c1")
    ctx.pages_fetched = 3
    ctx.candidates_found = 2
    r = rec.finish(ctx)
    s.commit()
    assert s.query(CollectorRunRecord).count() == 1
    assert r.status == "success"
    print("immutable run ok")


def test_health_score_blocked():
    s = _session()
    rec = MetricsRecorder(s)
    _seed_healthy(rec, 5)
    ctx = rec.start("test_collector")
    ctx.status = "blocked"
    ctx.http_failures = 5
    rec.finish(ctx)
    h = rec.health_score("test_collector")
    assert h["score"] < 50
    assert any(f["reason"] == "blocked" for f in h["factors"])
    print("blocked health ok", h["score"])


def test_regression_candidate_collapse():
    s = _session()
    rec = MetricsRecorder(s)
    _seed_healthy(rec, 8, candidates=20)
    s.commit()
    ctx = rec.start("test_collector")
    ctx.status = "success"
    ctx.pages_fetched = 5
    ctx.http_requests = 5
    ctx.candidates_found = 0  # collapse
    r = rec.finish(ctx)
    assert r.notes and "REGRESSION" in r.notes
    print("candidate collapse regression ok", r.notes)


def test_daily_report():
    s = _session()
    rec = MetricsRecorder(s)
    _seed_healthy(rec, 3)
    s.commit()
    report = daily_report(s)
    assert report["total_runs"] >= 3
    md = format_daily_report_md(report)
    assert "Daily Operational Report" in md
    print("daily report ok")


def test_fixture_conditions():
    s = _session()
    rec = MetricsRecorder(s)
    scenarios = [
        ("healthy", "success", 0, 10, 0),
        ("parser", "partial", 4, 0, 0),
        ("http", "failed", 0, 0, 6),
        ("blocked", "blocked", 0, 0, 3),
        ("zero_cand", "success", 0, 0, 0),
    ]
    for name, status, parser, cands, http_f in scenarios:
        ctx = rec.start("fixture_collector")
        ctx.status = status
        ctx.parser_failures = parser
        ctx.candidates_found = cands
        ctx.pages_fetched = 5 if status != "failed" else 0
        ctx.http_failures = http_f
        ctx.notes = name
        rec.finish(ctx)
    assert s.query(CollectorRunRecord).count() == len(scenarios)
    print("fixture conditions ok")


if __name__ == "__main__":
    test_record_immutable_runs()
    test_health_score_blocked()
    test_regression_candidate_collapse()
    test_daily_report()
    test_fixture_conditions()
    print("\nAll metrics tests passed")
