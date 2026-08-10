"""
Wave 2 Phase 1: full offline alert-path integration proof.

Single deterministic lifecycle, run through the real staging pipeline
(resolver -> evidence -> confidence -> alerts), against temporary SQLite
only. No real Discord traffic anywhere in this file — a fake transport
swapped in via monkeypatch stands in for `alerts.delivery.WebhookTransport`.

    baseline catalogue -> known device persisted -> later collection
    introduces a genuinely new device -> resolver marks is_new ->
    eligibility passes -> mocked Discord transport returns success ->
    WebhookDelivery row -> Alert row -> same device observed again ->
    no duplicate alert

...and, separately, the failure branch: mocked Discord failure ->
WebhookDelivery records failure -> zero Alert rows -> intelligence data
remains valid -> retry does not produce duplicate intelligence.

This complements (does not replace) the scenario-level unit tests in
test_alert_semantics.py — those isolate DiscordAlerter behavior directly;
this file proves the same guarantees hold end-to-end through the pipeline
with exact database-state assertions after every step, per the Wave 2
qualification mission's Phase 1 requirement.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from alerts.delivery import DeliveryResult
from collectors.wave1.adapter import AdapterMetrics, DiscoveryAdapter, DiscoveryResult
from collectors.wave1.staging_pipeline import run_oem_staging_cycle
from config.settings import load_settings
from database.models import Base
from database.session import get_session_factory, session_scope
from pipeline import IntelligencePipeline

import database.models_v03  # noqa: F401


class _FixtureAdapter(DiscoveryAdapter):
    def __init__(self, manufacturer, source_name, candidates, **kwargs):
        kwargs.setdefault("user_agent", "test")
        super().__init__(**kwargs)
        self.manufacturer = manufacturer
        self.source_name = source_name
        self._candidates = candidates

    def discover(self):
        metrics = AdapterMetrics(pages_requested=1, pages_fetched=1, candidates_found=len(self._candidates))
        return list(self._candidates), metrics


def _cand(m, s, i):
    return DiscoveryResult(
        manufacturer=m, source=s, source_url=f"https://example.test/{s}",
        canonical_url=f"https://example.test/{s}/{i}", region="us",
        candidate_identifier=i, raw_reference=i,
    )


def _build_pipeline(db_name, *, min_confidence_for_alert=0):
    settings = load_settings("config/config.staging.yaml")
    # A fresh tempfile.mkdtemp() (not the pytest `tmp_path` fixture) — pytest's
    # tmp_path retention/reuse policy was observed to occasionally hand back a
    # directory containing a stale sqlite file from a prior test run on this
    # Windows filesystem, silently reusing pre-existing WebhookDelivery/Alert
    # rows and making these assertions flaky. mkdtemp() is unique every call.
    db_path = Path(tempfile.mkdtemp()) / db_name
    settings.raw["database"]["url"] = f"sqlite:///{db_path.as_posix()}"
    settings.raw.setdefault("discord", {})["webhook_url"] = "https://discord.example/webhook"
    settings.raw["discord"]["min_confidence_for_alert"] = min_confidence_for_alert

    session_factory = get_session_factory(settings.database_url)
    Base.metadata.create_all(bind=session_factory().get_bind())
    return IntelligencePipeline(settings, session_factory), session_factory


class _DeliveringTransport:
    """Every eligible, non-suppressed send succeeds."""

    def __init__(self, url):
        self.url = url

    def send(self, payload, *, eligible, suppressed):
        if suppressed or not eligible:
            return DeliveryResult(eligible=eligible, suppressed=suppressed, attempted=False, delivered=False)
        return DeliveryResult(eligible=True, suppressed=False, attempted=True, delivered=True, status_code=204)


class _FailingTransport:
    """Every eligible, non-suppressed send is attempted but fails (HTTP 500)."""

    def __init__(self, url):
        self.url = url

    def send(self, payload, *, eligible, suppressed):
        if suppressed or not eligible:
            return DeliveryResult(eligible=eligible, suppressed=suppressed, attempted=False, delivered=False)
        return DeliveryResult(
            eligible=True, suppressed=False, attempted=True, delivered=False,
            status_code=500, error_type="server_error", error_message="simulated failure",
        )


def _delivery_rows(session):
    # `id` is a UUID (database/models.py::WebhookDelivery), not sequential —
    # ordering by it sorts lexically, not chronologically. `created_at` is
    # the actual insertion-order column.
    return session.execute(
        text("SELECT eligible, suppressed, attempted, delivered, status_code FROM webhook_deliveries ORDER BY created_at")
    ).fetchall()


def test_full_success_lifecycle(monkeypatch):
    monkeypatch.setattr("alerts.discord.WebhookTransport", _DeliveringTransport)
    pipeline, session_factory = _build_pipeline("wave2-p1-success.db")

    # --- Step 1: baseline catalogue -> known device persisted ---------------
    r1 = run_oem_staging_cycle(
        _FixtureAdapter("google", "google_store_category_phones", [_cand("google", "google_store_category_phones", "Pixel 9")]),
        pipeline, session_factory,
    )
    assert r1.baseline_just_completed is True
    assert r1.new_devices == 1

    with session_scope(session_factory) as session:
        devices = session.execute(text("SELECT manufacturer, model_number FROM devices")).fetchall()
        evidence_count = session.execute(text("SELECT COUNT(*) FROM evidence")).scalar()
        alerts, deliveries = _counts(session)
        rows = _delivery_rows(session)

    assert len(devices) == 1 and devices[0].model_number == "PIXEL 9"
    assert evidence_count == 1
    assert deliveries == 1  # baseline suppression represented in WebhookDelivery
    assert alerts == 0
    assert rows[0].suppressed == 0 and rows[0].eligible == 0  # backfill -> newsroom_eligible() False, not "suppressed"

    # --- Step 2: later collection introduces a genuinely new device ---------
    r2 = run_oem_staging_cycle(
        _FixtureAdapter("google", "google_store_category_phones", [
            _cand("google", "google_store_category_phones", "Pixel 9"),   # resighting
            _cand("google", "google_store_category_phones", "Pixel 11"),  # genuinely new
        ]),
        pipeline, session_factory,
    )
    assert r2.new_devices == 1  # resolver marks is_new for exactly one device
    assert r2.resighted == 1

    with session_scope(session_factory) as session:
        devices = session.execute(text("SELECT model_number FROM devices ORDER BY model_number")).fetchall()
        pixel11_evidence = session.execute(
            text("SELECT COUNT(*) FROM evidence e JOIN devices d ON e.device_id = d.id WHERE d.model_number = 'PIXEL 11'")
        ).scalar()
        alerts, deliveries = _counts(session)
        rows = _delivery_rows(session)
        alert_row = session.execute(text("SELECT discord_message_id FROM alerts")).fetchone()

    assert sorted(d.model_number for d in devices) == ["PIXEL 11", "PIXEL 9"]  # exactly one new Device
    assert pixel11_evidence == 1  # correct Evidence
    assert deliveries == 2  # +1 WebhookDelivery for this event (total: baseline + this)
    new_delivery = rows[-1]
    assert new_delivery.eligible == 1
    assert new_delivery.attempted == 1
    assert new_delivery.delivered == 1
    assert alerts == 1  # exactly one Alert
    assert alert_row.discord_message_id is not None  # Alert has a delivered message ID

    # --- Step 3: same device observed again -> no duplicate alert -----------
    r3 = run_oem_staging_cycle(
        _FixtureAdapter("google", "google_store_category_phones", [
            _cand("google", "google_store_category_phones", "Pixel 9"),
            _cand("google", "google_store_category_phones", "Pixel 11"),
        ]),
        pipeline, session_factory,
    )
    assert r3.new_devices == 0  # zero new Device
    assert r3.resighted == 2

    with session_scope(session_factory) as session:
        device_count = session.execute(text("SELECT COUNT(*) FROM devices")).scalar()
        alerts, deliveries = _counts(session)

    assert device_count == 2  # no duplicate intelligence
    assert alerts == 1  # no duplicate Alert
    assert deliveries == 2  # no duplicate WebhookDelivery for the resighted event


def test_full_failure_lifecycle(monkeypatch):
    monkeypatch.setattr("alerts.discord.WebhookTransport", _FailingTransport)
    pipeline, session_factory = _build_pipeline("wave2-p1-failure.db")

    # Baseline (suppressed regardless of transport outcome — backfill path).
    r1 = run_oem_staging_cycle(
        _FixtureAdapter("nothing", "nothing_products_sitemap", [_cand("nothing", "nothing_products_sitemap", "Phone (2a)")]),
        pipeline, session_factory,
    )
    assert r1.baseline_just_completed is True

    # New post-baseline device -> transport attempts and fails.
    r2 = run_oem_staging_cycle(
        _FixtureAdapter("nothing", "nothing_products_sitemap", [
            _cand("nothing", "nothing_products_sitemap", "Phone (2a)"),
            _cand("nothing", "nothing_products_sitemap", "Phone (3)"),
        ]),
        pipeline, session_factory,
    )
    assert r2.new_devices == 1

    with session_scope(session_factory) as session:
        alerts, deliveries = _counts(session)
        rows = _delivery_rows(session)
        device = session.execute(
            text("SELECT manufacturer, model_number, confidence FROM devices WHERE model_number = 'PHONE (3)'")
        ).fetchone()

    assert deliveries == 2  # baseline + this attempt, both recorded
    failed_row = rows[-1]
    assert failed_row.attempted == 1
    assert failed_row.delivered == 0
    assert failed_row.status_code == 500
    assert alerts == 0  # zero Alert rows
    assert device is not None and device.manufacturer == "nothing"  # intelligence data remains valid

    # Retry (reprocess the same discoveries) — must not duplicate intelligence.
    r3 = run_oem_staging_cycle(
        _FixtureAdapter("nothing", "nothing_products_sitemap", [
            _cand("nothing", "nothing_products_sitemap", "Phone (2a)"),
            _cand("nothing", "nothing_products_sitemap", "Phone (3)"),
        ]),
        pipeline, session_factory,
    )
    assert r3.new_devices == 0
    assert r3.resighted == 2

    with session_scope(session_factory) as session:
        device_count = session.execute(text("SELECT COUNT(*) FROM devices")).scalar()
        alerts, deliveries = _counts(session)

    assert device_count == 2  # no duplicate intelligence from the retry
    assert alerts == 0
    assert deliveries == 2  # resighting makes no new send attempt


def _counts(session):
    alerts = session.execute(text("SELECT COUNT(*) FROM alerts")).scalar()
    deliveries = session.execute(text("SELECT COUNT(*) FROM webhook_deliveries")).scalar()
    return alerts, deliveries
