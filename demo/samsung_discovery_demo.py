"""
Fixture-based genuine discovery demo (v0.3.1).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.panel import Panel

from collectors.samsung.sitemap_discovery import SamsungSitemapDiscovery
from collectors.samsung.polling import transition
from collectors.samsung.model_validator import SamsungModelValidator
from entity_resolution.confidence_service import ConfidenceService
from alerts.maintenance import MaintenanceAlerter

console = Console()


def run_demo():
    console.print(Panel("Samsung Discovery Demo — sitemap → unknown URLs → models", style="bold cyan"))

    # 1–2 baseline: known URL set (seed)
    baseline_urls = {
        "https://www.samsung.com/us/support/mobile/phones/galaxy-s/galaxy-s24-ultra/",
        "https://www.samsung.com/us/support/mobile/phones/galaxy-s/galaxy-s24/",
        "https://www.samsung.com/us/support/mobile/phones/galaxy-z/galaxy-z-fold6/",
    }
    console.print(f"[bold]Baseline known URLs:[/bold] {len(baseline_urls)} (no newsroom alerts)")

    disc = SamsungSitemapDiscovery(
        fixtures_dir=str(ROOT / "fixtures/samsung"),
        known_urls=baseline_urls,
        max_product_fetches=5,
    )

    # 3 index adds unknown product URLs
    stats = disc.discover(fetch_products=False, use_fixture_sitemap=True)
    console.print(f"Sitemap phone product URLs: {stats.phone_product_urls}")
    console.print(f"New URLs vs baseline: {stats.new_urls}")

    # show a few novel URLs
    novel = [d for d in stats.discoveries if d.get("novelty") == "new_url_unfetched"][:5]
    for d in novel:
        console.print(f"  NEW URL  {d['url']}")

    # 4–8 fetch + validate (fixture-assisted)
    stats2 = disc.discover(fetch_products=True, use_fixture_sitemap=True, max_fetches=4)
    console.print(f"Fetched product pages; valid mobile models: {stats2.valid_mobile}")
    for d in stats2.discoveries[:8]:
        console.print(
            f"  model={d.get('model')}  novelty={d.get('novelty')}  "
            f"origin={d.get('origin_type')}  slug={d.get('product_slug')}"
        )

    # 9 confidence ledger via service
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from database.models import Base, Device

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    svc = ConfidenceService(session)

    if stats2.discoveries:
        m = next((d for d in stats2.discoveries if d.get("model")), None)
        if m:
            dev = Device(manufacturer="samsung", model_number=m["model"], confidence=0)
            session.add(dev)
            session.flush()
            svc.apply(dev, rule_id="sitemap_new_page", points=10, evidence_id="demo1",
                      explanation="New URL from support sitemap")
            svc.apply(dev, rule_id="model_extracted", points=8, evidence_id="demo2",
                      explanation="Validated SM- model on first-party support page")
            console.print(f"Ledger confidence for {dev.model_number}: {dev.confidence}")
            audit = svc.recalculate(dev)
            console.print(f"Recalc drift: {audit['drift']}")

            # 14 invalidate
            svc.invalidate(dev, rule_id="model_extracted", original_evidence_id="demo2",
                           points_to_reverse=8, explanation="false positive reversed")
            console.print(f"After invalidation: {dev.confidence}")

    # 11 polling state
    pol = transition("newly_discovered", event="discovered")
    console.print(f"Polling: state={pol.state} interval={pol.interval_minutes}m reason={pol.reason}")
    pol2 = transition(pol.state, event="meaningful_change")
    console.print(f"After change: state={pol2.state} interval={pol2.interval_minutes}m")

    # 15–16 maintenance alerts
    maint = MaintenanceAlerter(webhook_url="", enabled=False)
    maint.alert(source_id="samsung_us_support_sitemap", problem="candidate_count_collapse",
                detail="median 42 → 0 across 3 successful HTTP runs")
    maint.recover(source_id="samsung_us_support_sitemap", problem="candidate_count_collapse",
                  detail="parser recovered, 38 candidates")

    console.print("[bold green]Discovery demo complete.[/bold green]")
    console.print("Origin: LIVE_VALIDATED sitemap fixture captured 2026-08-02 from samsung.com")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_demo())
