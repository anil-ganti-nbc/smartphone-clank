"""
Simulate ~30 days of collector activity for observability validation.
No live internet. Fixture-driven conditions only.
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console
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

console = Console()

COLLECTORS = [
    "samsung_us_support_sitemap",
    "samsung_us_owners_product",
    "fcc",
]


def simulate_day(rec: MetricsRecorder, day: datetime, rng: random.Random) -> list:
    records = []
    for name in COLLECTORS:
        roll = rng.random()
        ctx = rec.start(name, source_name=name, run_reason="demo")
        # scenario weights
        if roll < 0.05:
            # blocked
            ctx.status = "blocked"
            ctx.http_failures = 3
            ctx.pages_requested = 5
            ctx.notes = "simulated_blocked"
        elif roll < 0.10:
            # parser breakage
            ctx.status = "partial"
            ctx.pages_requested = 10
            ctx.pages_fetched = 10
            ctx.http_requests = 10
            ctx.parser_failures = 5
            ctx.candidates_found = 0
            ctx.notes = "simulated_parser_breakage"
        elif roll < 0.15:
            # HTTP outage
            ctx.status = "failed"
            ctx.pages_requested = 8
            ctx.http_requests = 8
            ctx.http_failures = 8
            ctx.notes = "simulated_http_outage"
        elif roll < 0.25:
            # quiet day
            ctx.status = "success"
            ctx.pages_requested = 6
            ctx.pages_fetched = 6
            ctx.http_requests = 6
            ctx.candidates_found = 2
            ctx.valid_devices = 2
            ctx.notes = "quiet_day"
        else:
            # healthy
            ctx.status = "success"
            pages = rng.randint(5, 15)
            ctx.pages_requested = pages
            ctx.pages_fetched = pages
            ctx.http_requests = pages
            ctx.bytes_downloaded = pages * rng.randint(50_000, 300_000)
            ctx.candidates_found = rng.randint(3, 20)
            ctx.valid_devices = max(0, ctx.candidates_found - rng.randint(0, 3))
            ctx.new_devices = rng.randint(0, 2)
            ctx.updated_devices = rng.randint(0, 4)
            ctx.evidence_added = ctx.new_devices + ctx.updated_devices
            ctx.meaningful_changes = rng.randint(0, 3)
            ctx.alerts_sent = 1 if ctx.new_devices else 0
            ctx.notes = "healthy"
        # backdate timestamps
        ctx.started_at = day + timedelta(hours=rng.randint(0, 20))
        # fake duration via finishing immediately; duration_ms from wall clock is tiny —
        # patch after finish
        r = rec.finish(ctx)
        # overwrite duration for simulation realism
        r.duration_ms = rng.randint(200, 8000) if ctx.status == "success" else rng.randint(500, 15000)
        if "parser" in (ctx.notes or ""):
            r.duration_ms = rng.randint(1000, 4000)
        if "runtime" in (ctx.notes or ""):
            r.duration_ms = 20000
        r.started_at = ctx.started_at
        r.finished_at = ctx.started_at + timedelta(milliseconds=r.duration_ms or 0)
        records.append(r)
    return records


def run_demo(days: int = 30, seed: int = 42) -> int:
    console.print(f"[bold cyan]Long-run simulation — {days} days[/bold cyan]")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    rec = MetricsRecorder(session)
    rng = random.Random(seed)
    start = datetime.utcnow() - timedelta(days=days)

    for i in range(days):
        day = start + timedelta(days=i)
        simulate_day(rec, day, rng)
        if i % 7 == 6:
            for c in COLLECTORS:
                rec.recompute_rolling(c)
    session.commit()

    # Force a slow-source and zero-candidate regression day on last day
    ctx = rec.start("samsung_us_support_sitemap", "samsung_us_support_sitemap", run_reason="demo")
    ctx.status = "success"
    ctx.pages_fetched = 10
    ctx.http_requests = 10
    ctx.candidates_found = 0
    ctx.notes = "forced_zero_candidates"
    r = rec.finish(ctx)
    r.duration_ms = 25000
    session.commit()

    console.print(f"Total run records: {session.query(CollectorRunRecord).count()}")

    for c in COLLECTORS:
        s = rec.collector_summary(c)
        h = s["health"]
        console.print(
            f"  {c:32} score={h['score']:3} {h['label']:20} "
            f"runs={s['total_runs']} avg_ms={s['avg_runtime_ms']}"
        )
        for f in h["factors"][:3]:
            console.print(f"    factor: {f}")

    report = daily_report(session, day=datetime.utcnow())
    # use last simulated calendar day approximately
    md = format_daily_report_md(report)
    console.print()
    console.print(md)
    console.print("[bold green]Long-run simulation complete.[/bold green]")
    session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_demo())
