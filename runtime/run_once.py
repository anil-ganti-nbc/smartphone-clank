"""Run one production source once under external source-level scheduling.

Each systemd timer invokes exactly one source.  A non-blocking per-source
lock replaces APScheduler ``max_instances=1``.  A blocking shared execution
lock intentionally serializes the complete run because today's SQLite
database uses rollback-journal mode and the entity/alert pipeline has not
proved concurrent logical writes safe.  Unlike the former single-worker
APScheduler queue, every due source has its own live service/process while it
waits, so a long Samsung run cannot make another source's due execution
disappear through ``misfire_grace_time``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from runtime.daemon import setup_runtime_logging  # reuse, no duplication
from runtime.locks import FileLock, lock_directory, safe_lock_name
from runtime.provenance import source_revision

log = logging.getLogger("clank.runtime.run_once")

EXIT_OK = 0
EXIT_UNKNOWN_COLLECTOR = 2
EXIT_ALL_FAILED = 1


@dataclass(frozen=True)
class ScheduledTarget:
    source_id: str
    interval_minutes: int
    run: Callable[[], object]


def _last_run_at(session, collector_name: str):
    from sqlalchemy import desc, select

    from pipeline import CollectorRunRecord

    row = session.execute(
        select(CollectorRunRecord)
        .where(CollectorRunRecord.collector_name == collector_name)
        .order_by(desc(CollectorRunRecord.started_at))
        .limit(1)
    ).scalar_one_or_none()
    return row.started_at if row else None


def is_due(session, collector_name: str, interval_minutes: int) -> bool:
    """A collector with no recorded run is due immediately -- this is what
    gives a fresh deployment the same first-run coverage the old
    DateTrigger startup jobs provided, without a separate concept."""
    last = _last_run_at(session, collector_name)
    if last is None:
        return True
    return datetime.utcnow() >= last + timedelta(minutes=interval_minutes)


def build_targets(
    settings, pipeline, session_factory, *, project_root: Path = ROOT,
    run_reason: str = "production_scheduled",
) -> list[ScheduledTarget]:
    """Build exactly the accepted production scope from both registries.

    SOAK collectors (collectors.SOAK_SAMSUNG_SOURCE_IDS) are included only
    when running against a staging environment: they have no promotion
    record and can never be scheduled from a production runtime. Their
    notification authority stays suppressed by policy regardless
    (alerts/source_maturity.py), so even a staging misconfiguration cannot
    reach production channels."""
    from collectors import build_collectors
    from collectors.wave1 import (
        assert_production_scope_or_refuse,
        build_wave1_production_collectors,
    )
    from collectors.wave1.staging_pipeline import run_oem_staging_cycle
    from runtime.environment import PRODUCTION, STAGING, assert_db_matches_environment

    assert_db_matches_environment(settings.database_url, PRODUCTION)
    assert_production_scope_or_refuse(settings)

    targets: list[ScheduledTarget] = []
    collectors_cfg = settings.get("collectors", default={}) or {}
    for collector in build_collectors(settings, project_root=project_root):
        interval = int((collectors_cfg.get(collector.name) or {}).get("interval_minutes") or 180)
        targets.append(ScheduledTarget(
            source_id=collector.name,
            interval_minutes=interval,
            run=lambda collector=collector: pipeline.run_collector(
                collector, run_reason=run_reason
            ),
        ))

    wave_cfg = settings.get("wave1", default={}) or {}
    for adapter in build_wave1_production_collectors(settings):
        interval = int((wave_cfg.get(adapter.manufacturer) or {}).get("interval_minutes") or 45)
        targets.append(ScheduledTarget(
            source_id=adapter.source_name,
            interval_minutes=interval,
            run=lambda adapter=adapter: run_oem_staging_cycle(
                adapter, pipeline, session_factory, run_reason=run_reason
            ),
        ))
    return targets


def build_staging_targets(
    settings, pipeline, session_factory, *, project_root: Path = ROOT,
    run_reason: str = "staging_scheduled",
) -> list[ScheduledTarget]:
    """Staging-environment one-shot targets: production scope PLUS soak
    collectors. Refuses a non-staging database (same guard as production)."""
    from collectors import build_collectors
    from runtime.environment import STAGING, assert_db_matches_environment

    assert_db_matches_environment(settings.database_url, STAGING)

    targets: list[ScheduledTarget] = []
    collectors_cfg = settings.get("collectors", default={}) or {}
    for collector in build_collectors(
        settings, project_root=project_root, include_soak=True
    ):
        interval = int((collectors_cfg.get(collector.name) or {}).get("interval_minutes") or 180)
        targets.append(ScheduledTarget(
            source_id=collector.name,
            interval_minutes=interval,
            run=lambda collector=collector: pipeline.run_collector(
                collector, run_reason=run_reason
            ),
        ))
    return targets


def run_target(target: ScheduledTarget, session_factory, database_url: str, *, force: bool) -> str:
    """Return ``ran``, ``not_due``, or ``already_running``; raise on failure."""
    locks = lock_directory(database_url)
    source_lock = FileLock(locks / f"source-{safe_lock_name(target.source_id)}.lock")
    if not source_lock.acquire(blocking=False):
        log.warning("skip %s: same-source invocation already running", target.source_id)
        return "already_running"
    try:
        execution_lock = FileLock(locks / "shared-execution.lock")
        log.info("waiting for shared execution lock source=%s", target.source_id)
        with execution_lock:
            session = session_factory()
            try:
                due = force or is_due(session, target.source_id, target.interval_minutes)
            finally:
                session.close()
            if not due:
                log.info(
                    "skip %s: not due (interval=%s min)",
                    target.source_id,
                    target.interval_minutes,
                )
                return "not_due"
            log.info("job start %s", target.source_id)
            target.run()
            log.info("job done %s", target.source_id)
            return "ran"
    finally:
        source_lock.release()


def main(argv: list[str] | None = None) -> int:
    from config.settings import load_settings
    from database.session import get_session_factory
    from database.schema_guard import ensure_schema_or_refuse, SchemaError
    from pipeline import IntelligencePipeline

    parser = argparse.ArgumentParser(description="Smartphone Clank one-shot collector runner")
    parser.add_argument("--collector", help="run only this collector")
    parser.add_argument(
        "--force", action="store_true", help="ignore the due-check for the selected collector(s)"
    )
    args = parser.parse_args(argv)

    log_dir = ROOT / "runtime" / "logs"
    setup_runtime_logging(log_dir, os.environ.get("CLANK_LOG_LEVEL", "INFO"))

    config_path = os.environ.get("CLANK_CONFIG", "config/config.yaml")
    settings = load_settings(config_path)
    log.info("startup source_revision=%s root=%s", source_revision(ROOT), ROOT)
    # See docs/infra/MIGRATION_AUDIT.md — this cloud one-shot entrypoint is a
    # production runtime path, same rule as runtime/daemon.py: refuse rather
    # than implicitly mutate schema.
    try:
        ensure_schema_or_refuse(settings.database_url, context="runtime.run_once startup")
    except SchemaError as e:
        log.error("refusing to start: %s", e)
        return 1
    session_factory = get_session_factory(settings.database_url)
    pipeline = IntelligencePipeline(settings, session_factory)

    try:
        targets = build_targets(settings, pipeline, session_factory)
    except Exception:
        log.exception("refusing to start: production target validation failed")
        return 1

    if not any(t.source_id == "samsung_us_support_sitemap" for t in targets):
        log.error(
            "CRITICAL: samsung_us_support_sitemap not in production registry — "
            "discovery will not run. Check config and samsung_sources.yaml"
        )

    if args.collector:
        targets = [target for target in targets if target.source_id == args.collector]
        if not targets:
            print(f"unknown collector: {args.collector}")
            return EXIT_UNKNOWN_COLLECTOR

    considered = len(targets)
    ran = 0
    failed = 0
    skipped = 0
    for target in targets:
        try:
            outcome = run_target(target, session_factory, settings.database_url, force=args.force)
            if outcome == "ran":
                ran += 1
            else:
                skipped += 1
        except Exception:
            log.exception("job failed %s", target.source_id)
            failed += 1

    print(f"ran={ran} failed={failed} skipped={skipped} considered={considered}")
    return EXIT_ALL_FAILED if (considered and ran == 0 and failed > 0) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
