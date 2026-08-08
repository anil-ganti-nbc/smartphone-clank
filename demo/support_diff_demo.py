"""
Full dry-run lifecycle for support-page change detection.

Simulates Events 1–8 without touching live websites.
Prints classifications, confidence, timeline, and Discord dry-run payloads.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ensure project root on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import load_settings
from database.session import get_session_factory, init_db, session_scope
from database.models import Device, TimelineEvent, Alias, Snapshot, PageMonitor
from collectors.support_monitor import SupportPageMonitor
from knowledge.fixtures.support_pages import (
    SAMSUNG_NEW_PAGE,
    SAMSUNG_FORMAT_ONLY,
    SAMSUNG_MANUAL_ADDED,
    SAMSUNG_VARIANT_AND_IMAGES,
    SAMSUNG_MARKETING_NAME,
    SAMSUNG_US_VARIANT,
    URL_MAIN,
    URL_US,
)
from pipeline import IntelligencePipeline
from models.schemas import Discovery

console = Console()


def banner(title: str):
    console.print()
    console.print(Panel(title, style="bold cyan"))


def show_result(label: str, result, discoveries: list):
    console.print(f"[bold]{label}[/bold]")
    console.print(f"  classifications: {result.classifications}")
    console.print(f"  meaningful:      {result.meaningful}")
    if result.details:
        # compact details
        d = {k: v for k, v in result.details.items() if v}
        console.print(f"  details:         {json.dumps(d, default=str)[:300]}")
    console.print(f"  discoveries:     {len(discoveries)}")
    for disc in discoveries:
        console.print(f"    → {disc.model_number}  weight={disc.raw.get('weight')}  marketing={disc.marketing_name}")


def dry_run_discord(device: Device, event_label: str, old_conf: int, result_cls: list):
    name = device.marketing_name or device.model_number
    lines = [
        f"**📄 Support Page Updated**",
        f"",
        f"**Device:** {name}",
        f"**Model:** `{device.model_number}`",
        f"**Confidence:** {old_conf} → **{device.confidence}**",
        f"**Classifications:** {', '.join(result_cls)}",
        f"**Source:** Samsung Support (demo)",
    ]
    console.print(Panel("\n".join(lines), title=f"Discord dry-run · {event_label}", border_style="green"))


def run_demo(config_path: str = "config/config.yaml"):
    settings = load_settings(config_path)
    # Shared in-memory DB (StaticPool) so all sessions see the same data
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from database.models import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    settings.raw.setdefault("database", {})["url"] = "sqlite://"
    pipeline = IntelligencePipeline(settings, session_factory)

    norm = (settings.get("support_page_normalization") or {}).get("samsung", {})
    ignore = norm.get("ignore_selectors")
    strip = set(norm.get("strip_query_parameters") or [])
    removal = settings.get("page_removal") or {}
    weights = settings.get("support_change_weights")

    def process_html(html: Optional[str], status: int, url: str, model: str, event_name: str):
        with session_scope(session_factory) as session:
            mon = SupportPageMonitor(
                session,
                collector_name="samsung_support",
                manufacturer="samsung",
                ignore_selectors=ignore,
                strip_query_params=strip or None,
                removal_cfg=removal,
                change_weights=weights,
            )
            result, snap, discoveries = mon.process_fetch(
                url, html, status, model_number=model
            )
            show_result(event_name, result, discoveries)

            # feed discoveries into intelligence pipeline (same session)
            old_devices = {d.model_number: d.confidence for d in session.query(Device).all()}
            if discoveries:
                new_c, upd_c = pipeline.process_discoveries(discoveries, session)
                console.print(f"  pipeline: new={new_c} updated={upd_c}")
            else:
                console.print("  pipeline: no discoveries emitted")

            # show device state
            if result.meaningful:
                for disc in discoveries:
                    dev = (
                        session.query(Device)
                        .filter(Device.model_number == disc.model_number.upper())
                        .first()
                    )
                    if dev:
                        session.refresh(dev)
                        old_c = old_devices.get(dev.model_number, 0)
                        dry_run_discord(dev, event_name, old_c, result.classifications)
            return result

    # ------------------------------------------------------------------
    banner("Event 1 — NEW support page for SM-S957B")
    r1 = process_html(SAMSUNG_NEW_PAGE, 200, URL_MAIN, "SM-S957B", "Event 1 NEW_PAGE")

    banner("Event 2 — FORMAT_ONLY (analytics + whitespace)")
    r2 = process_html(SAMSUNG_FORMAT_ONLY, 200, URL_MAIN, "SM-S957B", "Event 2 FORMAT_ONLY")
    assert not r2.meaningful, f"format-only must not be meaningful, got {r2.classifications}"

    banner("Event 3 — User manual added")
    r3 = process_html(SAMSUNG_MANUAL_ADDED, 200, URL_MAIN, "SM-S957B", "Event 3 DOWNLOAD_ADDED")
    assert r3.meaningful
    assert "DOWNLOAD_ADDED" in r3.classifications

    banner("Event 4 — Regional variants + product images")
    r4 = process_html(SAMSUNG_VARIANT_AND_IMAGES, 200, URL_MAIN, "SM-S957B", "Event 4 variants+images")

    banner("Event 4b — Separate US variant page SM-S957U")
    r4b = process_html(SAMSUNG_US_VARIANT, 200, URL_US, "SM-S957U", "Event 4b SM-S957U")

    banner("Event 5 — Marketing name in title")
    r5 = process_html(SAMSUNG_MARKETING_NAME, 200, URL_MAIN, "SM-S957B", "Event 5 TITLE_CHANGED")
    assert "TITLE_CHANGED" in r5.classifications or r5.meaningful

    banner("Event 6 — Temporary 500")
    r6 = process_html(None, 500, URL_MAIN, "SM-S957B", "Event 6 FETCH_ERROR")
    assert "FETCH_ERROR" in r6.classifications
    assert not r6.meaningful

    banner("Event 7 — Persistent 404s (threshold=3)")
    for i in range(3):
        r7 = process_html(None, 404, URL_MAIN, "SM-S957B", f"Event 7 404 #{i+1}")
    assert "PAGE_REMOVED" in r7.classifications or r7.details.get("consecutive", 0) >= 3

    banner("Event 8 — Page restored")
    r8 = process_html(SAMSUNG_MARKETING_NAME, 200, URL_MAIN, "SM-S957B", "Event 8 PAGE_RESTORED")
    assert "PAGE_RESTORED" in r8.classifications or r8.meaningful

    # ------------------------------------------------------------------
    banner("Final device dossier")
    with session_scope(session_factory) as session:
        devices = session.query(Device).order_by(Device.model_number).all()
        for dev in devices:
            console.print()
            console.print(f"[bold green]{dev.marketing_name or dev.model_number}[/bold green]")
            console.print(f"  model:        {dev.model_number}")
            console.print(f"  manufacturer: {dev.manufacturer}")
            console.print(f"  family:       {dev.family_name or '—'}")
            console.print(f"  tier:         {dev.product_tier or '—'}")
            console.print(f"  variant:      {dev.variant_label or '—'}")
            console.print(f"  confidence:   {dev.confidence}")
            console.print(f"  is_variant:   {dev.is_variant}")
            console.print(f"  family_id:    {dev.family_id or '—'}")

            aliases = session.query(Alias).filter(Alias.device_id == dev.id).all()
            if aliases:
                console.print("  aliases:")
                for a in aliases:
                    console.print(f"    [{a.alias_type}] {a.value}")

            events = (
                session.query(TimelineEvent)
                .filter(TimelineEvent.device_id == dev.id)
                .order_by(TimelineEvent.occurred_at)
                .all()
            )
            if events:
                console.print("  timeline:")
                for ev in events:
                    ts = ev.occurred_at.strftime("%Y-%m-%d %H:%M") if ev.occurred_at else "?"
                    console.print(f"    {ts}  {ev.source or ev.event_type}  {ev.title or ''}")

            console.print("  evidence:")
            for e in dev.evidence:
                console.print(
                    f"    {e.source:20}  +{e.confidence_contribution:3}  "
                    f"(orig {getattr(e, 'original_weight', e.confidence_contribution)})"
                )

        snaps = session.query(Snapshot).order_by(Snapshot.fetched_at).all()
        console.print()
        console.print(f"[bold]Snapshots stored:[/bold] {len(snaps)}")
        for s in snaps:
            console.print(
                f"  {s.fetched_at.strftime('%H:%M:%S') if s.fetched_at else '?'}  "
                f"status={s.status_code}  meaningful={s.meaningful}  "
                f"cls={s.classifications}  model={s.model_number}"
            )

    console.print()
    console.print("[bold green]Demo complete.[/bold green]  Demo DB: in-memory")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_demo())
