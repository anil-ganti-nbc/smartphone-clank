"""
Production runtime daemon.

Task Scheduler must invoke:
  .venv\\Scripts\\python.exe -m runtime.daemon

This process stays alive; APScheduler runs collectors.
Python owns rotating file logs — no PowerShell pipe handlers.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

VERSION = "0.3.6"


def setup_runtime_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    for name, fname in [
        ("runtime", "runtime.log"),
        ("runtime-error", "runtime-error.log"),
    ]:
        path = log_dir / fname
        handler = RotatingFileHandler(
            path, maxBytes=10_485_760, backupCount=10, encoding="utf-8"
        )
        handler.setFormatter(fmt)
        if "error" in name:
            handler.setLevel(logging.ERROR)
        root.addHandler(handler)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)
    root.addHandler(sh)


def main() -> int:
    from config.settings import load_settings
    from collectors import build_collectors, describe_registry
    from pipeline import IntelligencePipeline
    from database.session import get_session_factory
    from database.schema_guard import ensure_schema_or_refuse, SchemaError

    log_dir = ROOT / "runtime" / "logs"
    setup_runtime_logging(log_dir, os.environ.get("CLANK_LOG_LEVEL", "INFO"))
    log = logging.getLogger("clank.runtime")

    config = os.environ.get("CLANK_CONFIG", "config/config.yaml")
    settings = load_settings(config)
    # Production runtime never mutates schema on startup — see
    # docs/infra/MIGRATION_AUDIT.md. A behind-head database refuses to start
    # rather than silently create_all()-ing whatever happens to be importable
    # in this process at the moment (the exact mechanism that leaked
    # wave1_baseline_state into this database during Wave 1 development).
    try:
        ensure_schema_or_refuse(settings.database_url, context="runtime.daemon startup")
    except SchemaError as e:
        log.error("refusing to start: %s", e)
        return 1
    session_factory = get_session_factory(settings.database_url)
    pipeline = IntelligencePipeline(settings, session_factory)

    collectors = build_collectors(settings, project_root=ROOT)
    collectors_cfg = settings.get("collectors", default={}) or {}

    log.info(
        "startup version=%s pid=%s root=%s collectors=%s",
        VERSION,
        os.getpid(),
        ROOT,
        [c.name for c in collectors],
    )
    for row in describe_registry(settings, project_root=ROOT):
        log.info("registry %s", row)

    if not any(c.name == "samsung_us_support_sitemap" for c in collectors):
        log.error(
            "CRITICAL: samsung_us_support_sitemap not in production registry — "
            "discovery will not run. Check config and samsung_sources.yaml"
        )

    # Wave 1/Wave 2 production OEMs (see docs/wave1/PROMOTION_REPORT.md,
    # docs/wave2/MOTOROLA_CANARY_REPORT.md,
    # collectors/wave1/__init__.py::PRODUCTION_OEM_SCOPE). Double-gated: the
    # environment guard below refuses to hand back adapters against a
    # database that doesn't look like production, and
    # build_wave1_production_collectors() itself only returns OEMs in the
    # explicit allowlist regardless of what config.yaml enables.
    from runtime.environment import assert_db_matches_environment, EnvironmentMismatchError, PRODUCTION as ENV_PRODUCTION
    from collectors.wave1 import (
        build_wave1_production_collectors,
        assert_production_scope_or_refuse,
        ProductionScopeError,
    )

    # Fail-closed production-scope invariant (docs/infra/PRODUCTION_SCOPE_AUDIT.md
    # Part 4) — the exact class of bug the Motorola incident exposed: an OEM
    # approved in PRODUCTION_OEM_SCOPE but missing from config.yaml's
    # `manufacturers` allowlist would previously start up "successfully"
    # and silently drop every discovery. This must never be a warning.
    try:
        assert_production_scope_or_refuse(settings)
    except ProductionScopeError as e:
        log.error("%s", e)
        return 1
    log.info("production scope validation: OK")

    wave1_collectors = []
    try:
        assert_db_matches_environment(settings.database_url, ENV_PRODUCTION)
        wave1_collectors = build_wave1_production_collectors(settings)
    except EnvironmentMismatchError as e:
        log.error("wave1 production gate refused, no wave1 collectors will run: %s", e)
    if wave1_collectors:
        log.info("wave1 production collectors enabled: %s", [a.manufacturer for a in wave1_collectors])

    # Single-worker executor: collector jobs (Samsung's own registry plus any
    # wave1 production collectors above) share one IntelligencePipeline
    # instance, including DiscordAlerter.backfill — a mutable flag toggled
    # for the duration of each wave1 cycle. Running two jobs concurrently
    # could let one job's backfill state leak into another's alert decision.
    # Forcing strictly sequential execution removes that race entirely
    # (and incidentally avoids any concurrent-writer contention on SQLite).
    scheduler = BlockingScheduler(executors={"default": ThreadPoolExecutor(max_workers=1)})
    shutdown_reason = "unknown"

    def make_job(collector):
        def job():
            try:
                log.info("job start %s", collector.name)
                pipeline.run_collector(collector, run_reason="production_scheduled")
                log.info("job done %s", collector.name)
            except Exception:
                log.exception("job failed %s", collector.name)

        return job

    def make_wave1_job(adapter):
        def job():
            from collectors.wave1.staging_pipeline import run_oem_staging_cycle
            try:
                log.info("wave1 job start %s", adapter.manufacturer)
                result = run_oem_staging_cycle(
                    adapter, pipeline, session_factory, run_reason="production_scheduled"
                )
                log.info("wave1 job done %s %s", adapter.manufacturer, result)
            except Exception:
                # A wave1 OEM failing must never prevent Samsung (or any other
                # wave1 OEM) from running — see docs/wave1/PROMOTION_REPORT.md.
                log.exception("wave1 job failed %s", adapter.manufacturer)

        return job

    # Interval schedules
    for col in collectors:
        cfg = collectors_cfg.get(col.name, {}) or {}
        # sitemap interval from registry default 180
        interval = int(cfg.get("interval_minutes") or 180)
        if col.name == "samsung_us_support_sitemap":
            interval = int(cfg.get("interval_minutes") or 180)
        scheduler.add_job(
            make_job(col),
            trigger=IntervalTrigger(minutes=interval),
            id=col.name,
            name=col.name,
            max_instances=1,
            replace_existing=True,
            coalesce=True,
        )
        log.info("scheduled interval collector=%s every=%s min", col.name, interval)

    wave1_cfg = settings.get("wave1", default={}) or {}
    for adapter in wave1_collectors:
        oem_cfg = wave1_cfg.get(adapter.manufacturer, {}) or {}
        interval = int(oem_cfg.get("interval_minutes") or 45)
        jid = f"wave1_{adapter.manufacturer}"
        scheduler.add_job(
            make_wave1_job(adapter),
            trigger=IntervalTrigger(minutes=interval),
            id=jid,
            name=jid,
            max_instances=1,
            replace_existing=True,
            coalesce=True,
        )
        log.info("scheduled interval wave1 collector=%s every=%s min", adapter.manufacturer, interval)

    # Immediate startup runs (staggered)
    now = datetime.now()
    from datetime import timedelta

    startup_order = []
    for col in collectors:
        if col.name == "samsung_us_support_sitemap":
            startup_order.append((col, 5))
        elif getattr(col, "capability", "") == "monitoring":
            startup_order.append((col, 30))
        else:
            startup_order.append((col, 20))

    for col, delay_s in startup_order:
        run_at = now + timedelta(seconds=delay_s)
        jid = f"startup_{col.name}"
        scheduler.add_job(
            make_job(col),
            trigger=DateTrigger(run_date=run_at),
            id=jid,
            name=jid,
            max_instances=1,
            replace_existing=True,
        )
        log.info("scheduled startup collector=%s in %ss", col.name, delay_s)

    # Wave1 startup runs after Samsung's own startup run (Samsung's discovery
    # must not wait on Google) — staggered behind it, not concurrent with it.
    for i, adapter in enumerate(wave1_collectors):
        run_at = now + timedelta(seconds=40 + i * 20)
        jid = f"startup_wave1_{adapter.manufacturer}"
        scheduler.add_job(
            make_wave1_job(adapter),
            trigger=DateTrigger(run_date=run_at),
            id=jid,
            name=jid,
            max_instances=1,
            replace_existing=True,
        )
        log.info("scheduled startup wave1 collector=%s in %ss", adapter.manufacturer, 40 + i * 20)

    def _shutdown(signum, frame):
        nonlocal shutdown_reason
        shutdown_reason = f"signal_{signum}"
        log.info("shutdown requested reason=%s", shutdown_reason)
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            log.exception("scheduler shutdown error")

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("runtime entering scheduler loop")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        shutdown_reason = "keyboard_or_system_exit"
    finally:
        log.info("runtime exit reason=%s", shutdown_reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
