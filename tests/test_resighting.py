"""
Proves: re-fetching an unchanged page updates device freshness (last_seen)
without creating a duplicate Evidence row or double-counting confidence.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import Base, Evidence
from entity_resolution.resolver import EntityResolver
from models.schemas import Discovery, Manufacturer, SourceType


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _disc(model="SM-S957B", url="https://www.samsung.com/us/support/mobile/phones/galaxy-s/sm-s957b/"):
    return Discovery(
        manufacturer=Manufacturer.SAMSUNG,
        model_number=model,
        source="samsung_us_support_sitemap",
        source_type=SourceType.SUPPORT_PAGE,
        url=url,
    )


def test_first_sighting_creates_device_and_evidence():
    session = _session()
    resolver = EntityResolver(session, weights={"support_page": 10})
    device, is_new, evidence_added = resolver.resolve(_disc())
    session.commit()
    assert is_new is True
    assert evidence_added is True
    assert session.query(Evidence).filter(Evidence.device_id == device.id).count() == 1
    print("first sighting creates device+evidence: ok")


def test_resighting_no_duplicate_evidence_but_freshens():
    session = _session()
    resolver = EntityResolver(session, weights={"support_page": 10})
    device, _, _ = resolver.resolve(_disc())
    session.commit()

    stale_seen = device.last_seen
    time.sleep(0.01)  # ensure a measurable freshness delta

    device2, is_new2, evidence_added2 = resolver.resolve(_disc())  # identical re-fetch
    session.commit()

    assert device2.id == device.id
    assert is_new2 is False
    assert evidence_added2 is False, "identical re-fetch must not be treated as new evidence"
    assert session.query(Evidence).filter(Evidence.device_id == device.id).count() == 1, \
        "resighting must not create a duplicate Evidence row"
    assert device2.last_seen > stale_seen, "resighting must still refresh last_seen (freshness)"
    print("resighting: no dup evidence, last_seen refreshed: ok")


def test_resighting_does_not_change_confidence_contribution():
    """Confidence is only ever applied via ConfidenceService when evidence_added — a
    resighting produces evidence_added=False, so pipeline.py never calls conf_svc.apply()
    for it. This checks the signal ConfidenceService keys off stays untouched."""
    session = _session()
    resolver = EntityResolver(session, weights={"support_page": 10})
    device, _, _ = resolver.resolve(_disc())
    session.commit()
    ev = session.query(Evidence).filter(Evidence.device_id == device.id).first()
    contribution_before = ev.confidence_contribution

    _, _, evidence_added = resolver.resolve(_disc())
    session.commit()
    ev_after = session.query(Evidence).filter(Evidence.device_id == device.id).first()

    assert evidence_added is False
    assert ev_after.confidence_contribution == contribution_before
    assert ev_after.id == ev.id  # same row, not replaced
    print("resighting leaves confidence contribution untouched: ok")


def test_page_content_change_is_not_a_resighting():
    """A genuinely different URL/content for the same device IS new evidence —
    resighting suppression must not swallow real changes."""
    session = _session()
    resolver = EntityResolver(session, weights={"support_page": 10})
    device, _, _ = resolver.resolve(_disc(url="https://www.samsung.com/us/support/mobile/phones/galaxy-s/sm-s957b/"))
    session.commit()

    _, is_new2, evidence_added2 = resolver.resolve(
        _disc(url="https://www.samsung.com/us/support/mobile/phones/galaxy-s/sm-s957b-v2/")
    )
    session.commit()

    assert is_new2 is False  # same device
    assert evidence_added2 is True  # but a genuinely new page for it
    assert session.query(Evidence).filter(Evidence.device_id == device.id).count() == 2
    print("real change still counted as new evidence: ok")


def run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
