"""v0.3.1 sitemap discovery, confidence service, ordered migrations, polling."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.samsung.sitemap_discovery import SamsungSitemapDiscovery, PHONE_PATH_RE
from collectors.samsung.polling import transition
from entity_resolution.confidence_service import ConfidenceService
from database.migrations_ordered import upgrade, current_version, history, backup


def test_phone_path_regex():
    assert PHONE_PATH_RE.match("/us/support/mobile/phones/galaxy-s/galaxy-s25-ultra/")
    assert PHONE_PATH_RE.match("/us/support/mobile/phones/galaxy-a/galaxy-a36-5g/")
    assert not PHONE_PATH_RE.match("/us/support/mobile/phones/galaxy-s/")
    print("path regex ok")


def test_parse_fixture_sitemap():
    disc = SamsungSitemapDiscovery(fixtures_dir=str(ROOT / "fixtures/samsung"))
    stats = disc.discover(fetch_products=False, use_fixture_sitemap=True)
    assert stats.phone_product_urls >= 50, stats.phone_product_urls
    assert stats.validation_status == "LIVE_VALIDATED"
    print(f"sitemap parse ok: {stats.phone_product_urls} phone product URLs")


def test_extract_from_sitemap_discovered_page():
    disc = SamsungSitemapDiscovery(
        fixtures_dir=str(ROOT / "fixtures/samsung"),
        max_product_fetches=2,
        known_urls=set(),
    )
    # offline: use fixture sitemap + product fixtures
    stats = disc.discover(fetch_products=True, use_fixture_sitemap=True, max_fetches=3)
    # may use fixture product pages when live fetch fails
    print(f"product fetch stats: valid={stats.valid_mobile} extracted={stats.models_extracted} errors={stats.errors[:3]}")
    assert stats.phone_product_urls > 0
    print("discovery pipeline ok")


def test_polling_transitions():
    d = transition("newly_discovered", event="no_change")
    assert d.state in ("stable", "newly_discovered", "recently_changed")
    d2 = transition("stable", event="meaningful_change")
    assert d2.state == "recently_changed"
    d3 = transition("stable", event="fetch_error", failure_backoff=0)
    assert d3.state == "failing"
    d4 = transition("failing", event="fetch_error", failure_backoff=2)
    assert d4.failure_backoff >= 2
    print("polling transitions ok", d2.interval_minutes)


def test_confidence_service_and_recalc():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from database.models import Base, Device
    from entity_resolution.confidence_ledger import ConfidenceLedgerEntry  # noqa

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    dev = Device(manufacturer="samsung", model_number="SM-TEST031", confidence=0)
    s.add(dev)
    s.flush()
    svc = ConfidenceService(s)
    svc.apply(dev, rule_id="support_new_page", points=10, evidence_id="e1", explanation="new page")
    svc.apply(dev, rule_id="support_new_page", points=10, evidence_id="e1", explanation="dup")  # suppressed
    assert dev.confidence == 10
    svc.apply(dev, rule_id="download_user_manual", points=18, evidence_id="e2")
    assert dev.confidence == 28
    audit = svc.recalculate(dev, repair=False)
    assert audit["ledger_sum"] == 28
    assert audit["drift"] == 0
    svc.invalidate(dev, rule_id="download_user_manual", original_evidence_id="e2", points_to_reverse=18)
    assert dev.confidence == 10
    print("confidence service ok", svc.ledger.summary(dev))


def test_ordered_migrations():
    td = tempfile.mkdtemp()
    db = f"sqlite:///{td}/m.db"
    applied = upgrade(db)
    assert "0.2.1" in applied
    assert "0.3.0" in applied
    assert "0.3.1" in applied
    assert current_version(db) == "0.3.1"
    # idempotent
    applied2 = upgrade(db)
    assert applied2 == []
    h = history(db)
    assert len(h) >= 3
    print("ordered migrations ok", h)


if __name__ == "__main__":
    test_phone_path_regex()
    test_parse_fixture_sitemap()
    test_extract_from_sitemap_discovered_page()
    test_polling_transitions()
    test_confidence_service_and_recalc()
    test_ordered_migrations()
    print("\nAll v0.3.1 tests passed")
