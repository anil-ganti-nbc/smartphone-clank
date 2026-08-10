"""One-shot execution: the cloud-migration replacement for the
BlockingScheduler daemon (runtime/daemon.py).

Checks each registered collector's last recorded run (from
CollectorRunRecord -- already persisted for every attempt, success or
failure, by pipeline.py's own MetricsRecorder; not reconstructed from
anything in-memory) against its configured interval_minutes, runs exactly
the collectors that are due, once, then exits. Intended to be invoked
repeatedly by an external scheduler (cron/systemd timer).

Full behavioral mapping from the prior BlockingScheduler model:

  multiple independent cadences   -> preserved as-is: interval_minutes is
                                      still read from the same
                                      config.yaml/samsung_sources.yaml
  per-source schedules            -> preserved (same source)
  max_instances=1 (same collector)-> was actually an in-process-only
                                      guarantee already (APScheduler's job
                                      store is in-memory, so this never
                                      protected against two separate
                                      processes anyway); replaced by an
                                      external `flock` wrapper around the
                                      whole tick at the cron-invocation
                                      level (see deploy_run.sh on the
                                      Hetzner host) -- no lock code exists
                                      anywhere in this codebase today, so
                                      this is new safety, not a
                                      replacement for an existing
                                      in-app mechanism. See
                                      docs/SCHEDULER_MIGRATION.md.
  coalesce=True                   -> not needed: a tick either finds a
                                      collector due or it doesn't; there is
                                      no in-process missed-run queue to
                                      collapse under an external-scheduler
                                      model
  one-time DateTrigger startup    -> not needed: the first tick against a
  jobs (staggered 5/20/30s)          fresh/empty CollectorRunRecord table
                                      finds every collector due and runs
                                      all of them, giving equivalent
                                      first-run coverage without an
                                      explicit startup concept
  retry/backoff                   -> unchanged: this script does not retry
                                      failed collectors itself; a failed
                                      collector remains "due" (its last
                                      recorded run does not satisfy
                                      interval_minutes going forward from
                                      the failure) and will be attempted
                                      again on the next tick, same
                                      resilience the interval trigger
                                      always provided
  "daemon alive" heartbeat        -> never existed: dashboard/app.py's
                                      /healthz only ever checked DB
                                      connectivity, never daemon liveness
                                      -- nothing to preserve or fabricate

Does NOT change: collector scope, collector registry, config loading,
database initialization, or any collector/pipeline/normalization logic.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from runtime.daemon import setup_runtime_logging  # reuse, no duplication

log = logging.getLogger("clank.runtime.run_once")

EXIT_OK = 0
EXIT_UNKNOWN_COLLECTOR = 2
EXIT_ALL_FAILED = 1


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


def main(argv: list[str] | None = None) -> int:
    from collectors import build_collectors
    from config.settings import load_settings
    from database.session import get_session_factory, init_db
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
    init_db(settings.database_url)
    session_factory = get_session_factory(settings.database_url)
    pipeline = IntelligencePipeline(settings, session_factory)

    collectors = build_collectors(settings, project_root=ROOT)
    collectors_cfg = settings.get("collectors", default={}) or {}

    if not any(c.name == "samsung_us_support_sitemap" for c in collectors):
        log.error(
            "CRITICAL: samsung_us_support_sitemap not in production registry — "
            "discovery will not run. Check config and samsung_sources.yaml"
        )

    if args.collector:
        collectors = [c for c in collectors if c.name == args.collector]
        if not collectors:
            print(f"unknown collector: {args.collector}")
            return EXIT_UNKNOWN_COLLECTOR

    considered = len(collectors)
    ran = 0
    failed = 0
    session = session_factory()
    try:
        for col in collectors:
            cfg = collectors_cfg.get(col.name, {}) or {}
            interval = int(cfg.get("interval_minutes") or 180)
            due = args.force or is_due(session, col.name, interval)
            if not due:
                log.info("skip %s: not due (interval=%s min)", col.name, interval)
                continue
            log.info("job start %s", col.name)
            try:
                pipeline.run_collector(col, run_reason="production_scheduled")
                log.info("job done %s", col.name)
                ran += 1
            except Exception:
                log.exception("job failed %s", col.name)
                failed += 1
    finally:
        session.close()

    print(f"ran={ran} failed={failed} considered={considered}")
    return EXIT_ALL_FAILED if (considered and ran == 0 and failed > 0) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
