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
    from database.session import init_db, get_session_factory

    log_dir = ROOT / "runtime" / "logs"
    setup_runtime_logging(log_dir, os.environ.get("CLANK_LOG_LEVEL", "INFO"))
    log = logging.getLogger("clank.runtime")

    config = os.environ.get("CLANK_CONFIG", "config/config.yaml")
    settings = load_settings(config)
    init_db(settings.database_url)
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

    scheduler = BlockingScheduler()
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
