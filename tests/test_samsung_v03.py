"""v0.3 Samsung model validation, discovery fixtures, ledger idempotency."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.samsung.model_validator import SamsungModelValidator
from entity_resolution.confidence_ledger import ConfidenceLedger, ConfidenceLedgerEntry
from knowledge.change_detection import extract_fingerprint


def test_parse_galaxy_s():
    v = SamsungModelValidator()
    r = v.validate("SM-S928U")
    assert r.valid
    assert r.canonical_model.startswith("SM-S928")
    assert r.category_hint == "smartphone"
    assert r.series_hint == "Galaxy S"
    print("galaxy s ok", r)


def test_parse_foldable():
    v = SamsungModelValidator()
    r = v.validate("SM-F956U")
    assert r.valid
    assert r.category_hint == "foldable"
    print("foldable ok", r)


def test_parse_carrier_suffix():
    v = SamsungModelValidator()
    r = v.validate("SM-S928ULBEXAA")
    assert r.valid
    assert r.canonical_model.startswith("SM-S")
    print("carrier suffix ok", r.canonical_model, r.suffixes)


def test_reject_excluded_category():
    v = SamsungModelValidator()
    # SM-L is laptop per rules
    r = v.validate("SM-L123")
    assert not r.valid or r.category_hint == "laptop"
    if r.valid:
        assert not v.is_alert_eligible(r)
    print("exclude laptop ok", r.reject_reason or r.category_hint)


def test_find_in_live_fixture():
    path = ROOT / "fixtures/samsung/live_samsung_us_galaxy_s24_ultra.html"
    if not path.exists():
        print("skip live fixture missing")
        return
    html = path.read_text(encoding="utf-8", errors="replace")
    v = SamsungModelValidator()
    found = v.find_candidates(html)
    assert any(x.startswith("SM-S928") for x in found), found
    validated = [v.validate(x) for x in found]
    ok = [x for x in validated if x.valid and v.is_alert_eligible(x)]
    assert ok, validated
    print("live fixture models", [x.canonical_model for x in ok])


def test_ledger_idempotent():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from database.models import Base, Device
    from database.models_v03 import SchemaVersion  # noqa
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    dev = Device(manufacturer="samsung", model_number="SM-TEST1", confidence=0)
    session.add(dev)
    session.flush()
    ledger = ConfidenceLedger(session)
    e1 = ledger.record(dev, rule="support_new_page", points=10, evidence_id="ev1", explanation="new page")
    e2 = ledger.record(dev, rule="support_new_page", points=10, evidence_id="ev1", explanation="dup")
    assert e1 is not None
    assert e2 is None
    assert dev.confidence == 10
    session.commit()
    print("ledger idempotent ok", ledger.summary(dev))


def test_migration_stamp():
    from database.migrate import upgrade, get_version
    url = "sqlite://"
    # file-less: use tmp
    import tempfile
    td = tempfile.mkdtemp()
    db = f"sqlite:///{td}/t.db"
    v = upgrade(db)
    assert v == "0.3.0"
    assert get_version(db) == "0.3.0"
    # idempotent
    v2 = upgrade(db)
    assert v2 == "0.3.0"
    print("migration ok")


if __name__ == "__main__":
    test_parse_galaxy_s()
    test_parse_foldable()
    test_parse_carrier_suffix()
    test_reject_excluded_category()
    test_find_in_live_fixture()
    test_ledger_idempotent()
    test_migration_stamp()
    print("\nAll v0.3 samsung tests passed")
