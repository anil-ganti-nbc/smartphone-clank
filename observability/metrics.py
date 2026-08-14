"""
Operational metrics — immutable collector run records, health scores, regression.
Does not change discovery or confidence logic.
"""

from __future__ import annotations

import logging
import os
try:
    import resource  # Unix only; unavailable on Windows
except ImportError:  # pragma: no cover
    resource = None  # type: ignore
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from statistics import mean, median
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, Integer, String, Text, Boolean, Index
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from database.models import Base, Device, Evidence, Snapshot

logger = logging.getLogger("clank.metrics")


def _uuid() -> str:
    return str(uuid4())


class CollectorRunRecord(Base):
    """Immutable append-only run metrics (extended v0.3.3)."""

    __tablename__ = "collector_run_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    collector_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="success")  # success|partial|degraded|unexpected_zero|failed|blocked
    pages_requested: Mapped[int] = mapped_column(Integer, default=0)
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    bytes_downloaded: Mapped[int] = mapped_column(Integer, default=0)
    http_requests: Mapped[int] = mapped_column(Integer, default=0)
    http_failures: Mapped[int] = mapped_column(Integer, default=0)
    parser_failures: Mapped[int] = mapped_column(Integer, default=0)
    candidates_found: Mapped[int] = mapped_column(Integer, default=0)
    valid_devices: Mapped[int] = mapped_column(Integer, default=0)
    new_devices: Mapped[int] = mapped_column(Integer, default=0)
    updated_devices: Mapped[int] = mapped_column(Integer, default=0)
    evidence_added: Mapped[int] = mapped_column(Integer, default=0)
    meaningful_changes: Mapped[int] = mapped_column(Integer, default=0)
    alerts_sent: Mapped[int] = mapped_column(Integer, default=0)
    maintenance_alerts_sent: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    cache_misses: Mapped[int] = mapped_column(Integer, default=0)
    resighted: Mapped[int] = mapped_column(Integer, default=0)  # fetched, no meaningful change
    # production_scheduled | production_manual | validation | demo | test | fixture
    run_reason: Mapped[str] = mapped_column(String(32), default="production_manual", index=True)
    peak_rss_kb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cpu_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_run_metrics_collector_started", "collector_name", "started_at"),
    )


class MetricsBaseline(Base):
    """Per-collector baseline for regression detection."""

    __tablename__ = "metrics_baselines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    collector_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    median_duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    median_candidates: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    median_pages_fetched: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    median_http_failures: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    thresholds: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class RollingStat(Base):
    """Precomputed rolling window stats."""

    __tablename__ = "rolling_stats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    collector_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    window: Mapped[str] = mapped_column(String(16), nullable=False)  # hour|day|week
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    avg_duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p95_duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discovery_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    alert_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    failure_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    parser_warning_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mtbf_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


DEFAULT_THRESHOLDS = {
    "runtime_multiplier": 2.0,
    "candidate_drop_ratio": 0.3,  # below 30% of median
    "pages_drop_ratio": 0.3,
    "http_failure_spike": 5,
    "parser_failure_spike": 3,
    "zero_discovery_with_healthy_fetch": True,
}


@dataclass
class RunContext:
    collector_name: str
    source_name: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    pages_requested: int = 0
    pages_fetched: int = 0
    bytes_downloaded: int = 0
    http_requests: int = 0
    http_failures: int = 0
    parser_failures: int = 0
    candidates_found: int = 0
    valid_devices: int = 0
    new_devices: int = 0
    updated_devices: int = 0
    evidence_added: int = 0
    meaningful_changes: int = 0
    alerts_sent: int = 0
    maintenance_alerts_sent: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    resighted: int = 0
    run_reason: str = "production_manual"
    notes: str = ""
    status: str = "success"
    _t0: float = field(default_factory=time.time)
    _cpu0: float = field(default_factory=lambda: time.process_time())


class MetricsRecorder:
    def __init__(self, session: Session, thresholds: dict | None = None):
        self.session = session
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    def start(self, collector_name: str, source_name: str = "", run_reason: str = "production_manual") -> RunContext:
        return RunContext(collector_name=collector_name, source_name=source_name, run_reason=run_reason)

    def finish(self, ctx: RunContext) -> CollectorRunRecord:
        finished = datetime.utcnow()
        duration_ms = int((time.time() - ctx._t0) * 1000)
        cpu_ms = int((time.process_time() - ctx._cpu0) * 1000)
        rss = None
        if resource is not None:
            try:
                rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
                # Linux reports KB; macOS bytes — store as reported
            except Exception:
                pass

        rec = CollectorRunRecord(
            collector_name=ctx.collector_name,
            source_name=ctx.source_name or None,
            started_at=ctx.started_at,
            finished_at=finished,
            duration_ms=duration_ms,
            status=ctx.status,
            pages_requested=ctx.pages_requested,
            pages_fetched=ctx.pages_fetched,
            bytes_downloaded=ctx.bytes_downloaded,
            http_requests=ctx.http_requests,
            http_failures=ctx.http_failures,
            parser_failures=ctx.parser_failures,
            candidates_found=ctx.candidates_found,
            valid_devices=ctx.valid_devices,
            new_devices=ctx.new_devices,
            updated_devices=ctx.updated_devices,
            evidence_added=ctx.evidence_added,
            meaningful_changes=ctx.meaningful_changes,
            alerts_sent=ctx.alerts_sent,
            maintenance_alerts_sent=ctx.maintenance_alerts_sent,
            cache_hits=ctx.cache_hits,
            cache_misses=ctx.cache_misses,
            resighted=ctx.resighted,
            run_reason=ctx.run_reason,
            peak_rss_kb=rss,
            cpu_time_ms=cpu_ms,
            notes=ctx.notes or None,
        )
        self.session.add(rec)
        self.session.flush()
        self._update_baseline(ctx.collector_name)
        self._check_regressions(rec)
        return rec

    def _runs(self, collector: str, since: datetime | None = None) -> list[CollectorRunRecord]:
        q = self.session.query(CollectorRunRecord).filter(
            CollectorRunRecord.collector_name == collector
        )
        if since:
            q = q.filter(CollectorRunRecord.started_at >= since)
        return q.order_by(CollectorRunRecord.started_at.desc()).all()

    def _update_baseline(self, collector: str) -> None:
        runs = self._runs(collector)[:50]
        if len(runs) < 3:
            return
        durs = [r.duration_ms for r in runs if r.duration_ms is not None]
        cands = [r.candidates_found for r in runs]
        pages = [r.pages_fetched for r in runs]
        fails = [r.http_failures for r in runs]
        bl = (
            self.session.query(MetricsBaseline)
            .filter(MetricsBaseline.collector_name == collector)
            .first()
        )
        if not bl:
            bl = MetricsBaseline(collector_name=collector, thresholds=self.thresholds)
            self.session.add(bl)
        if durs:
            bl.median_duration_ms = float(median(durs))
        if cands:
            bl.median_candidates = float(median(cands))
        if pages:
            bl.median_pages_fetched = float(median(pages))
        if fails:
            bl.median_http_failures = float(median(fails))
        bl.sample_count = len(runs)
        bl.updated_at = datetime.utcnow()

    def _check_regressions(self, rec: CollectorRunRecord) -> list[str]:
        issues = []
        bl = (
            self.session.query(MetricsBaseline)
            .filter(MetricsBaseline.collector_name == rec.collector_name)
            .first()
        )
        if not bl or bl.sample_count < 5:
            return issues
        th = {**self.thresholds, **(bl.thresholds or {})}
        if (
            bl.median_duration_ms
            and rec.duration_ms
            and rec.duration_ms > bl.median_duration_ms * float(th.get("runtime_multiplier", 2.0))
        ):
            issues.append(
                f"runtime_regression: {rec.duration_ms}ms vs median {bl.median_duration_ms:.0f}ms"
            )
        if (
            bl.median_candidates
            and bl.median_candidates > 0
            and rec.candidates_found < bl.median_candidates * float(th.get("candidate_drop_ratio", 0.3))
        ):
            issues.append(
                f"candidate_collapse: {rec.candidates_found} vs median {bl.median_candidates:.1f}"
            )
        if (
            bl.median_pages_fetched
            and bl.median_pages_fetched > 0
            and rec.pages_fetched < bl.median_pages_fetched * float(th.get("pages_drop_ratio", 0.3))
            and rec.status != "blocked"
        ):
            issues.append(
                f"pages_collapse: {rec.pages_fetched} vs median {bl.median_pages_fetched:.1f}"
            )
        if rec.http_failures >= int(th.get("http_failure_spike", 5)):
            issues.append(f"http_failure_spike: {rec.http_failures}")
        if rec.parser_failures >= int(th.get("parser_failure_spike", 3)):
            issues.append(f"parser_failure_spike: {rec.parser_failures}")
        if (
            th.get("zero_discovery_with_healthy_fetch")
            and rec.pages_fetched > 0
            and rec.http_failures == 0
            and rec.candidates_found == 0
            and (bl.median_candidates or 0) > 2
        ):
            issues.append("zero_candidates_despite_healthy_fetch")
        if issues:
            rec.notes = ((rec.notes or "") + " | REGRESSION: " + "; ".join(issues)).strip(" |")
            logger.warning(f"[{rec.collector_name}] regressions: {issues}")
        return issues

    def health_score(
        self,
        collector: str,
        *,
        in_scope: bool | None = None,
        expected_interval_minutes: float | None = None,
    ) -> dict[str, Any]:
        """Deterministic 0-100 score with explainable factors.

        in_scope=False (an out-of-production collector — see collectors.production_scope)
        short-circuits to a non-numeric N/A score: it never competed for a
        "Healthy" label in the first place, regardless of what its raw runs look like.
        """
        if in_scope is False:
            return {"score": None, "label": "N/A", "factors": [{"reason": "out_of_scope"}], "last_status": None}

        factors: list[dict] = []
        score = 100
        recent = self._runs(collector, since=datetime.utcnow() - timedelta(days=7))
        if not recent:
            return {"score": 0, "label": "unknown", "factors": [{"reason": "no_runs", "delta": -100}]}

        last = recent[0]

        if expected_interval_minutes:
            stale_after = timedelta(minutes=expected_interval_minutes * 2)
            age = datetime.utcnow() - last.started_at
            if age > stale_after:
                factors.append({
                    "reason": "stale",
                    "delta": None,
                    "value": round(age.total_seconds() / 3600, 1),
                })
                score = min(score, 40)
        if last.status == "blocked":
            score -= 79
            factors.append({"reason": "blocked", "delta": -79})
        elif last.status == "failed":
            score -= 40
            factors.append({"reason": "last_run_failed", "delta": -40})
        elif last.status == "partial":
            score -= 15
            factors.append({"reason": "last_run_partial", "delta": -15})
        elif last.status == "degraded":
            score -= 40
            factors.append({"reason": "last_run_degraded", "delta": -40})
        elif last.status == "unexpected_zero":
            score -= 50
            factors.append({"reason": "unexpected_zero", "delta": -50})

        fails = sum(1 for r in recent if r.status in ("failed", "blocked", "unexpected_zero"))
        if recent:
            fail_rate = fails / len(recent)
            if fail_rate > 0.5:
                d = -30
                score += d
                factors.append({"reason": "high_failure_rate", "delta": d, "value": round(fail_rate, 2)})
            elif fail_rate > 0.2:
                d = -15
                score += d
                factors.append({"reason": "elevated_failure_rate", "delta": d, "value": round(fail_rate, 2)})

        parser = sum(r.parser_failures for r in recent)
        if parser >= 5:
            d = -20
            score += d
            factors.append({"reason": "parser_failures", "delta": d, "value": parser})
        elif parser >= 1:
            d = -8
            score += d
            factors.append({"reason": "minor_parser_warnings", "delta": d, "value": parser})

        bl = (
            self.session.query(MetricsBaseline)
            .filter(MetricsBaseline.collector_name == collector)
            .first()
        )
        if bl and bl.median_candidates and bl.median_candidates > 2:
            avg_c = mean([r.candidates_found for r in recent[:10]])
            if avg_c < bl.median_candidates * 0.3:
                d = -26
                score += d
                factors.append({"reason": "candidate_count_low", "delta": d, "value": round(avg_c, 1)})

        http_f = sum(r.http_failures for r in recent[:5])
        if http_f >= 10:
            d = -25
            score += d
            factors.append({"reason": "repeated_http_failures", "delta": d, "value": http_f})

        if len(recent) < 3 and score >= 75:
            # A collector that ran once or twice and never failed hasn't earned
            # "Healthy" yet — it's unproven, not degraded. Note it, don't punish the score.
            factors.append({"reason": "insufficient_run_history", "delta": None, "value": len(recent)})

        score = max(0, min(100, score))
        if score >= 90:
            label = "Healthy"
        elif score >= 75:
            label = "Minor issues"
        elif score >= 50:
            label = "Degraded"
        elif score >= 25:
            label = "Unhealthy"
        else:
            label = "Blocked / critical"
        if len(recent) < 3 and label in ("Healthy", "Minor issues"):
            label = "Provisional"
        return {"score": score, "label": label, "factors": factors, "last_status": last.status}

    def recompute_rolling(self, collector: str) -> list[RollingStat]:
        out = []
        windows = {
            "hour": timedelta(hours=1),
            "day": timedelta(days=1),
            "week": timedelta(days=7),
        }
        for name, delta in windows.items():
            runs = self._runs(collector, since=datetime.utcnow() - delta)
            if not runs:
                continue
            durs = sorted([r.duration_ms for r in runs if r.duration_ms is not None])
            p95 = durs[int(len(durs) * 0.95)] if durs else None
            success = sum(1 for r in runs if r.status == "success")
            fails = sum(1 for r in runs if r.status in ("failed", "blocked"))
            discoveries = sum(r.new_devices + r.updated_devices for r in runs)
            alerts = sum(r.alerts_sent for r in runs)
            parser_w = sum(1 for r in runs if r.parser_failures > 0)
            mtbf = None
            if fails > 0 and len(runs) > 1:
                span_h = max(
                    (runs[0].started_at - runs[-1].started_at).total_seconds() / 3600.0,
                    0.01,
                )
                mtbf = span_h / fails
            # delete prior for window
            self.session.query(RollingStat).filter(
                RollingStat.collector_name == collector, RollingStat.window == name
            ).delete()
            st = RollingStat(
                collector_name=collector,
                window=name,
                avg_duration_ms=mean(durs) if durs else None,
                p95_duration_ms=float(p95) if p95 is not None else None,
                run_count=len(runs),
                success_rate=success / len(runs),
                discovery_rate=discoveries / len(runs),
                alert_rate=alerts / len(runs),
                failure_rate=fails / len(runs),
                parser_warning_rate=parser_w / len(runs),
                mtbf_hours=mtbf,
            )
            self.session.add(st)
            out.append(st)
        return out

    def database_health(self, db_path: str | None = None) -> dict[str, Any]:
        size = None
        if db_path and os.path.exists(db_path):
            size = os.path.getsize(db_path)
        return {
            "database_bytes": size,
            "devices": self.session.query(Device).count(),
            "evidence": self.session.query(Evidence).count(),
            "snapshots": self.session.query(Snapshot).count(),
            "run_metrics": self.session.query(CollectorRunRecord).count(),
        }

    def collector_summary(
        self,
        collector: str,
        *,
        in_scope: bool | None = None,
        expected_interval_minutes: float | None = None,
    ) -> dict[str, Any]:
        runs = self._runs(collector)
        day = [r for r in runs if r.started_at >= datetime.utcnow() - timedelta(days=1)]
        health = self.health_score(
            collector, in_scope=in_scope, expected_interval_minutes=expected_interval_minutes
        )
        durs = [r.duration_ms for r in runs if r.duration_ms is not None]
        return {
            "collector": collector,
            "health": health,
            "last_successful": next(
                (r.finished_at.isoformat() for r in runs if r.status == "success" and r.finished_at),
                None,
            ),
            "avg_runtime_ms": mean(durs) if durs else None,
            "median_runtime_ms": median(durs) if durs else None,
            "runs_24h": len(day),
            "success_rate_24h": (
                sum(1 for r in day if r.status == "success") / len(day) if day else None
            ),
            "parser_failures_24h": sum(r.parser_failures for r in day),
            "http_failures_24h": sum(r.http_failures for r in day),
            "meaningful_discoveries_24h": sum(r.meaningful_changes for r in day),
            "alerts_24h": sum(r.alerts_sent for r in day),
            "avg_pages_fetched": mean([r.pages_fetched for r in runs[:20]]) if runs else None,
            "avg_candidates": mean([r.candidates_found for r in runs[:20]]) if runs else None,
            "total_runs": len(runs),
        }


PRODUCTION_RUN_REASONS = ("production_scheduled", "production_manual")


def _day_bounds_utc(day: datetime | None, tz: str) -> tuple[datetime, datetime, datetime]:
    """Compute [start, end) in UTC for the calendar day `day` falls on in `tz`.

    Storage stays UTC throughout — only the bucketing boundary moves.
    """
    if tz.upper() == "UTC":
        anchor = day or datetime.utcnow()
        start = datetime(anchor.year, anchor.month, anchor.day)
        return start, start + timedelta(days=1), start

    from zoneinfo import ZoneInfo
    zone = ZoneInfo(tz)
    anchor_utc = (day or datetime.utcnow()).replace(tzinfo=ZoneInfo("UTC"))
    anchor_local = anchor_utc.astimezone(zone)
    local_start = datetime(anchor_local.year, anchor_local.month, anchor_local.day, tzinfo=zone)
    local_end = local_start + timedelta(days=1)
    return (
        local_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
        local_end.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
        local_start.replace(tzinfo=None),
    )


def daily_report(
    session: Session,
    day: datetime | None = None,
    *,
    tz: str = "Asia/Kolkata",
    production_scope: set[str] | None = None,
    include_reasons: tuple[str, ...] = PRODUCTION_RUN_REASONS,
) -> dict[str, Any]:
    """
    Aggregate collector_run_metrics for one calendar day, bucketed in `tz`
    (default Asia/Kolkata — the operator's local day, not UTC).

    `production_scope` (see collectors.production_scope) restricts headline
    numbers and health tables to in-scope collectors; runs from out-of-scope
    collectors are reported separately, never folded into headline counts.
    `include_reasons` further restricts headline numbers to real production
    activity (production_scheduled/production_manual) — runs tagged demo,
    test, validation, or fixture are excluded from headline counts entirely
    and reported under `baseline_or_nonproduction_runs`.
    """
    start_utc, end_utc, local_date = _day_bounds_utc(day, tz)
    runs_all = (
        session.query(CollectorRunRecord)
        .filter(CollectorRunRecord.started_at >= start_utc, CollectorRunRecord.started_at < end_utc)
        .all()
    )

    out_of_scope = []
    scoped = runs_all
    if production_scope is not None:
        scoped = [r for r in runs_all if r.collector_name in production_scope]
        out_of_scope = [r for r in runs_all if r.collector_name not in production_scope]

    non_production = [r for r in scoped if r.run_reason not in include_reasons]
    runs = [r for r in scoped if r.run_reason in include_reasons]

    collectors = sorted({r.collector_name for r in runs})
    rec = MetricsRecorder(session)
    success = sum(1 for r in runs if r.status == "success")

    def _in_scope(name: str) -> bool:
        return production_scope is None or name in production_scope

    by_collector = {c: rec.collector_summary(c, in_scope=_in_scope(c)) for c in collectors}
    slowest = max(runs, key=lambda r: r.duration_ms or 0, default=None)
    fastest = min(
        (r for r in runs if r.duration_ms is not None),
        key=lambda r: r.duration_ms or 0,
        default=None,
    )

    expected = sorted(production_scope) if production_scope is not None else []
    running = sorted({r.collector_name for r in runs} | {r.collector_name for r in non_production})
    missing = sorted(set(expected) - set(running))

    # An expected production collector that never ran this window is itself an
    # attention-worthy fact — surface it in by_collector/attention even though
    # it has no runs to summarize, instead of it silently vanishing from the report.
    for c in missing:
        by_collector[c] = {
            "collector": c,
            "health": {"score": None, "label": "MISSING", "factors": [{"reason": "no_runs_in_window"}]},
            "last_successful": None,
            "runs_24h": 0,
            "success_rate_24h": None,
            "total_runs": 0,
        }

    attention = [
        c for c, s in by_collector.items()
        if c in missing or (s["health"]["score"] is not None and s["health"]["score"] < 75)
    ]

    from alerts.delivery import channel_summary
    newsroom_alerts = channel_summary(session, "newsroom", start=start_utc, end=end_utc)
    maintenance_alerts = channel_summary(session, "maintenance", start=start_utc, end=end_utc)

    db = rec.database_health()
    return {
        "date": local_date.date().isoformat(),
        "timezone": tz,
        "collectors_run": len(collectors),
        "total_runs": len(runs),
        "success_rate": (success / len(runs)) if runs else None,
        "expected_collectors": expected,
        "running_collectors": running,
        "missing_collectors": missing,
        "new_discoveries": sum(r.new_devices for r in runs),
        "updated_devices": sum(r.updated_devices for r in runs),
        "resighted": sum(r.resighted for r in runs),
        "baseline_or_nonproduction_runs": len(non_production),
        "baseline_or_nonproduction_reasons": sorted({r.run_reason for r in non_production}),
        "newsroom_alerts": newsroom_alerts,
        "maintenance_alerts": maintenance_alerts,
        "database": db,
        "slowest": (
            {"collector": slowest.collector_name, "ms": slowest.duration_ms} if slowest else None
        ),
        "fastest": (
            {"collector": fastest.collector_name, "ms": fastest.duration_ms} if fastest else None
        ),
        "attention": attention,
        "by_collector": by_collector,
        "out_of_scope_collectors": sorted({r.collector_name for r in out_of_scope}),
        "out_of_scope_runs": len(out_of_scope),
    }


def format_daily_report_md(report: dict) -> str:
    lines = [
        f"# Clank Daily Operational Report — {report['date']} ({report.get('timezone', 'Asia/Kolkata')})",
        "",
        f"- Collectors run: **{report['collectors_run']}**",
        f"- Total runs: **{report['total_runs']}**",
        f"- Success rate: **{report['success_rate']}**" if report["success_rate"] is not None else "- Success rate: n/a",
        "",
        "## Expected vs running",
    ]
    if report.get("expected_collectors"):
        for c in report["expected_collectors"]:
            mark = "[OK]" if c in report.get("running_collectors", []) else "[MISSING]"
            lines.append(f"- {mark} `{c}`")
    else:
        lines.append("- No production scope configured")
    lines += [
        "",
        "## Discoveries",
        f"- New discoveries: **{report['new_discoveries']}**",
        f"- Updated devices (meaningful change): **{report['updated_devices']}**",
        f"- Re-sightings (no change): **{report['resighted']}**",
        f"- Baseline/non-production runs excluded from above: **{report['baseline_or_nonproduction_runs']}**"
        + (f" ({', '.join(report['baseline_or_nonproduction_reasons'])})" if report.get("baseline_or_nonproduction_reasons") else ""),
        "",
        "## Alerts",
    ]
    for label, key in (("Newsroom", "newsroom_alerts"), ("Maintenance", "maintenance_alerts")):
        a = report.get(key) or {}
        lines.append(
            f"- {label}: eligible={a.get('eligible', 0)} attempted={a.get('attempted', 0)} "
            f"delivered={a.get('delivered', 0)} suppressed={a.get('suppressed', 0)} failed={a.get('failed', 0)}"
        )
    lines += [
        "",
        f"DB devices/evidence/snapshots: {report['database'].get('devices')}/{report['database'].get('evidence')}/{report['database'].get('snapshots')}",
        "",
        "## Attention required",
    ]
    if report["attention"]:
        for c in report["attention"]:
            h = report["by_collector"][c]["health"]
            lines.append(f"- **{c}** score={h['score']} ({h['label']})")
    else:
        lines.append("- None")
    lines += ["", "## Per collector"]
    for c, s in report["by_collector"].items():
        lines.append(
            f"- `{c}` health={s['health']['score']} ({s['health']['label']}) runs_24h={s['runs_24h']} "
            f"success={s['success_rate_24h']} avg_ms={s.get('avg_runtime_ms')}"
        )
    if report.get("slowest"):
        lines.append(f"\nSlowest: {report['slowest']}")
    if report.get("fastest"):
        lines.append(f"Fastest: {report['fastest']}")
    if report.get("out_of_scope_collectors"):
        lines += [
            "",
            "## Out of production scope (runs ignored in headline)",
            f"- Collectors: {', '.join('`'+c+'`' for c in report['out_of_scope_collectors'])}",
            f"- Runs excluded: {report.get('out_of_scope_runs', 0)}",
        ]
    lines.append(f"\nTimezone: {report.get('timezone', 'Asia/Kolkata')}")
    return "\n".join(lines) + "\n"
