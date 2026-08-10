"""
Alert persistence semantics (post-cleanup): an `Alert` row means exactly one
thing — this newsroom message was actually delivered to Discord.
`WebhookDelivery` is the source of truth for every transport decision
(eligible/suppressed/attempted/delivered/failed), written regardless of
outcome. See alerts/discord.py::record_alert()/_send() docstrings and
HANDOFF.md's Discord architecture section.

No real Discord traffic anywhere in this file — delivery-success/failure are
simulated via a fake WebhookTransport (same pattern as
tests/wave1/test_discord_safety.py), never a live send.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from alerts.delivery import DeliveryResult
from alerts.discord import DiscordAlerter
from database.models import Base, Device


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _device(session, **kwargs) -> Device:
    d = Device(
        manufacturer=kwargs.pop("manufacturer", "google"),
        model_number=kwargs.pop("model_number", "PIXEL 99"),
        marketing_name=kwargs.pop("marketing_name", "Pixel 99"),
        confidence=kwargs.pop("confidence", 50),
        **kwargs,
    )
    session.add(d)
    session.flush()
    return d


class _FakeTransport:
    """Drop-in for WebhookTransport — no HTTP, caller controls the outcome."""

    def __init__(self, outcome: str):
        self.outcome = outcome  # "delivered" | "failed" | "missing_webhook"

    def send(self, payload, *, eligible: bool, suppressed: bool) -> DeliveryResult:
        if suppressed:
            return DeliveryResult(eligible=eligible, suppressed=True, attempted=False, delivered=False)
        if not eligible:
            return DeliveryResult(eligible=False, suppressed=False, attempted=False, delivered=False)
        if self.outcome == "missing_webhook":
            return DeliveryResult(eligible=eligible, suppressed=False, attempted=False, delivered=False, error_type="webhook_not_configured")
        if self.outcome == "failed":
            return DeliveryResult(eligible=eligible, suppressed=False, attempted=True, delivered=False, status_code=500, error_type="server_error")
        return DeliveryResult(eligible=eligible, suppressed=False, attempted=True, delivered=True, status_code=204)


def _alerter(session, *, backfill=False, enabled=True, outcome="delivered") -> DiscordAlerter:
    a = DiscordAlerter(
        webhook_url="https://discord.example/webhook",
        enabled=enabled,
        session_factory=lambda: session,
        backfill=backfill,
    )
    a.transport = _FakeTransport(outcome)
    return a


def _counts(session):
    alerts = session.execute(text("SELECT COUNT(*) FROM alerts")).scalar()
    deliveries = session.execute(text("SELECT COUNT(*) FROM webhook_deliveries")).scalar()
    return alerts, deliveries


# ---------------------------------------------------------------------------
# The six required scenarios
# ---------------------------------------------------------------------------

def test_ineligible_event_writes_delivery_only():
    session = _session()
    device = _device(session)
    alerter = _alerter(session, outcome="delivered")

    # An unrecognized reason fails closed (alerts/eligibility.py) — genuinely
    # ineligible, not a backfill/suppression case.
    msg_id = alerter._send("irrelevant content", reason="not_a_real_reason", session=session)
    if msg_id:
        alerter.record_alert(session, device, "new_device", "msg", msg_id)
    session.commit()

    alerts, deliveries = _counts(session)
    assert msg_id is None
    assert deliveries == 1
    assert alerts == 0


def test_baseline_suppressed_writes_delivery_only():
    session = _session()
    device = _device(session, confidence=80)  # comfortably above min_confidence
    alerter = _alerter(session, backfill=True, outcome="delivered")

    msg_id = alerter.alert_new_device(device, session=session)
    if msg_id:
        alerter.record_alert(session, device, "new_device", "msg", msg_id)
    session.commit()

    alerts, deliveries = _counts(session)
    assert msg_id is None
    assert deliveries == 1
    assert alerts == 0
    row = session.execute(text("SELECT suppressed, eligible FROM webhook_deliveries")).fetchone()
    assert row.eligible == 0  # backfill makes newsroom_eligible() return False


def test_missing_webhook_writes_delivery_only():
    session = _session()
    device = _device(session, confidence=80)
    # enabled=False (no webhook configured) — DiscordAlerter.enabled becomes
    # False regardless of the `enabled` flag once webhook_url is empty.
    alerter = DiscordAlerter(webhook_url="", enabled=True, session_factory=lambda: session)
    alerter.transport = _FakeTransport("missing_webhook")

    msg_id = alerter.alert_new_device(device, session=session)
    if msg_id:
        alerter.record_alert(session, device, "new_device", "msg", msg_id)
    session.commit()

    alerts, deliveries = _counts(session)
    assert msg_id is None
    assert deliveries == 1
    assert alerts == 0
    row = session.execute(text("SELECT suppressed FROM webhook_deliveries")).fetchone()
    assert row.suppressed == 1  # not-enabled path is recorded as suppressed


def test_discord_failure_writes_delivery_only():
    session = _session()
    device = _device(session, confidence=80)
    alerter = _alerter(session, outcome="failed")

    msg_id = alerter.alert_new_device(device, session=session)
    if msg_id:
        alerter.record_alert(session, device, "new_device", "msg", msg_id)
    session.commit()

    alerts, deliveries = _counts(session)
    assert msg_id is None
    assert deliveries == 1
    assert alerts == 0
    row = session.execute(text("SELECT attempted, delivered, status_code FROM webhook_deliveries")).fetchone()
    assert row.attempted == 1
    assert row.delivered == 0
    assert row.status_code == 500


def test_discord_success_writes_delivery_and_exactly_one_alert():
    session = _session()
    device = _device(session, confidence=80)
    alerter = _alerter(session, outcome="delivered")

    msg_id = alerter.alert_new_device(device, session=session)
    assert msg_id is not None
    alerter.record_alert(session, device, "new_device", "msg", msg_id)
    session.commit()

    alerts, deliveries = _counts(session)
    assert deliveries == 1
    assert alerts == 1
    row = session.execute(text("SELECT discord_message_id FROM alerts")).fetchone()
    assert row.discord_message_id is not None


def test_record_alert_refuses_without_a_delivered_id():
    """Defense in depth: record_alert() itself refuses to write a phantom
    row even if a caller forgets to gate on msg_id."""
    session = _session()
    device = _device(session)
    alerter = _alerter(session)

    alerter.record_alert(session, device, "new_device", "msg", discord_id=None)
    session.commit()

    alerts, _ = _counts(session)
    assert alerts == 0


def test_reprocessing_a_delivered_event_does_not_duplicate_the_alert(monkeypatch, tmp_path):
    """spec: same delivered event retried -> still exactly 1 Alert row.
    Simulated via the real pipeline/resolver dedup identity (is_new becomes
    False once the device exists), not a synthetic guard — see the comment
    in pipeline.py::process_discoveries()."""
    from collectors.wave1.adapter import DiscoveryAdapter, AdapterMetrics, DiscoveryResult
    from collectors.wave1.staging_pipeline import run_oem_staging_cycle
    from config.settings import load_settings
    from database.session import get_session_factory, session_scope
    import database.models_v03  # noqa: F401
    from pipeline import IntelligencePipeline

    class FixtureAdapter(DiscoveryAdapter):
        def __init__(self, manufacturer, source_name, candidates, **kwargs):
            kwargs.setdefault("user_agent", "test")
            super().__init__(**kwargs)
            self.manufacturer = manufacturer
            self.source_name = source_name
            self._candidates = candidates

        def discover(self):
            metrics = AdapterMetrics(pages_requested=1, pages_fetched=1, candidates_found=len(self._candidates))
            return list(self._candidates), metrics

    def cand(m, s, i):
        return DiscoveryResult(
            manufacturer=m, source=s, source_url=f"https://example.test/{s}",
            canonical_url=f"https://example.test/{s}/{i}", region="us",
            candidate_identifier=i, raw_reference=i,
        )

    class DeliveringTransport:
        def __init__(self, url):
            self.url = url

        def send(self, payload, *, eligible, suppressed):
            if suppressed or not eligible:
                return DeliveryResult(eligible=eligible, suppressed=suppressed, attempted=False, delivered=False)
            return DeliveryResult(eligible=True, suppressed=False, attempted=True, delivered=True, status_code=204)

    monkeypatch.setattr("alerts.discord.WebhookTransport", DeliveringTransport)

    db_path = tmp_path / "clank-staging-alert-test.db"
    settings = load_settings("config/config.staging.yaml")
    settings.raw["database"]["url"] = f"sqlite:///{db_path.as_posix()}"
    settings.raw.setdefault("discord", {})["webhook_url"] = "https://discord.example/webhook"
    # Single-evidence fixture devices land at confidence 10 (default weight);
    # lower the alert threshold so this test can actually reach the
    # delivered branch and prove idempotency, rather than being blocked
    # earlier by the ordinary min-confidence gate (a separate, correctly
    # working piece of business logic, not what this test is about).
    settings.raw["discord"]["min_confidence_for_alert"] = 0

    session_factory = get_session_factory(settings.database_url)
    Base.metadata.create_all(bind=session_factory().get_bind())
    import database.models_v03  # noqa: F401
    Base.metadata.create_all(bind=session_factory().get_bind())
    pipeline = IntelligencePipeline(settings, session_factory)

    # Cycle 1: baseline (backfill=True) — Pixel 9 only. Suppressed, 0 alerts.
    r1 = run_oem_staging_cycle(
        FixtureAdapter("google", "google_store_category_phones", [cand("google", "google_store_category_phones", "Pixel 9")]),
        pipeline, session_factory,
    )
    assert r1.baseline_just_completed is True

    # Cycle 2: baseline already complete — Pixel 9 (resighting) + Pixel 11 (genuinely new, eligible).
    r2 = run_oem_staging_cycle(
        FixtureAdapter("google", "google_store_category_phones", [
            cand("google", "google_store_category_phones", "Pixel 9"),
            cand("google", "google_store_category_phones", "Pixel 11"),
        ]),
        pipeline, session_factory,
    )
    assert r2.new_devices == 1

    with session_scope(session_factory) as session:
        alerts_after_2 = session.execute(text("SELECT COUNT(*) FROM alerts")).scalar()
    assert alerts_after_2 == 1

    # Cycle 3: "retry" — reprocess the exact same discoveries again (as a
    # restarted/duplicated run might). Pixel 11 now already exists, so
    # is_new is False this time — no re-alert attempt is even made.
    r3 = run_oem_staging_cycle(
        FixtureAdapter("google", "google_store_category_phones", [
            cand("google", "google_store_category_phones", "Pixel 9"),
            cand("google", "google_store_category_phones", "Pixel 11"),
        ]),
        pipeline, session_factory,
    )
    assert r3.new_devices == 0
    assert r3.resighted == 2

    with session_scope(session_factory) as session:
        alerts_after_3 = session.execute(text("SELECT COUNT(*) FROM alerts")).scalar()
    assert alerts_after_3 == 1, "retried/reprocessed delivered event must not duplicate the Alert row"


# ---------------------------------------------------------------------------
# Per-OEM baseline suppression, still passing after the semantics change
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("manufacturer,source", [
    ("google", "google_store_category_phones"),
    ("nothing", "nothing_products_sitemap"),
    ("oneplus", "oneplus_regional_sitemap"),
    ("motorola", "motorola_regional_sitemap"),
    ("honor", "honor_global_sitemap"),
    ("oppo", "oppo_global_sitemap"),
    ("realme", "realme_regional_sitemap"),
])
def test_oem_baseline_suppression_writes_zero_alerts(tmp_path, manufacturer, source):
    from collectors.wave1.adapter import DiscoveryAdapter, AdapterMetrics, DiscoveryResult
    from collectors.wave1.staging_pipeline import run_oem_staging_cycle
    from config.settings import load_settings
    from database.session import get_session_factory, session_scope
    import database.models_v03  # noqa: F401
    from pipeline import IntelligencePipeline

    class FixtureAdapter(DiscoveryAdapter):
        def __init__(self, manufacturer, source_name, candidates, **kwargs):
            kwargs.setdefault("user_agent", "test")
            super().__init__(**kwargs)
            self.manufacturer = manufacturer
            self.source_name = source_name
            self._candidates = candidates

        def discover(self):
            metrics = AdapterMetrics(pages_requested=1, pages_fetched=1, candidates_found=len(self._candidates))
            return list(self._candidates), metrics

    def cand(m, s, i):
        return DiscoveryResult(
            manufacturer=m, source=s, source_url=f"https://example.test/{s}",
            canonical_url=f"https://example.test/{s}/{i}", region="us",
            candidate_identifier=i, raw_reference=i,
        )

    identifier = {
        "google": "Pixel 9", "nothing": "Phone (3)", "oneplus": "OnePlus 13",
        "motorola": "Razr 2026", "honor": "Honor Magic8 Pro", "oppo": "Find X9 Pro", "realme": "realme 16 Pro 5G",
    }[manufacturer]

    db_path = tmp_path / f"clank-staging-{manufacturer}-alert-test.db"
    settings = load_settings("config/config.staging.yaml")
    settings.raw["database"]["url"] = f"sqlite:///{db_path.as_posix()}"

    session_factory = get_session_factory(settings.database_url)
    Base.metadata.create_all(bind=session_factory().get_bind())
    Base.metadata.create_all(bind=session_factory().get_bind())
    pipeline = IntelligencePipeline(settings, session_factory)

    result = run_oem_staging_cycle(
        FixtureAdapter(manufacturer, source, [cand(manufacturer, source, identifier)]),
        pipeline, session_factory,
    )
    assert result.baseline_just_completed is True
    assert result.new_devices == 1

    with session_scope(session_factory) as session:
        alerts = session.execute(text("SELECT COUNT(*) FROM alerts")).scalar()
    assert alerts == 0, f"{manufacturer} baseline import must not create Alert rows"
