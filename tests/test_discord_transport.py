"""Discord webhook transport tests — offline, mocked HTTP only."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from alerts.delivery import WebhookTransport, redact_webhook_url
from alerts.discord import DiscordAlerter
from alerts.eligibility import newsroom_eligible, maintenance_eligible
from alerts.maintenance import MaintenanceAlerter
from config.settings import Settings
from database.models import Base, Device, WebhookDelivery


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    # maintenance_alerts is a raw-SQL table, not part of Base.metadata — create it here too.
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS maintenance_alerts (
                id VARCHAR(36) PRIMARY KEY,
                alert_key VARCHAR(128) NOT NULL,
                source_id VARCHAR(64),
                severity VARCHAR(16) DEFAULT 'warning',
                message TEXT NOT NULL,
                first_sent_at DATETIME,
                last_sent_at DATETIME,
                resolved_at DATETIME,
                send_count INTEGER DEFAULT 1,
                payload JSON
            )
            """
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_maint_alert_key ON maintenance_alerts(alert_key)"
        ))
    return sessionmaker(bind=engine)()


class _FakeResponse:
    def __init__(self, status_code: int, headers: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}


def test_missing_webhook():
    transport = WebhookTransport(None)
    result = transport.send({"content": "hi"})
    assert result.attempted is False
    assert result.delivered is False
    assert result.error_type == "webhook_not_configured"
    print("missing webhook ok")


def test_successful_204():
    transport = WebhookTransport("https://discord.com/api/webhooks/x/y")
    with patch("httpx.Client.post", return_value=_FakeResponse(204)):
        result = transport.send({"content": "hi"})
    assert result.delivered is True
    assert result.status_code == 204
    print("successful 204 ok")


def test_timeout_retried_then_fails():
    transport = WebhookTransport("https://discord.com/api/webhooks/x/y", max_attempts=3)
    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("timed out")) as mock_post, \
         patch("alerts.delivery.time.sleep"):
        result = transport.send({"content": "hi"})
    assert mock_post.call_count == 3
    assert result.delivered is False
    assert result.error_type == "timeout"
    assert result.attempted is True
    print("timeout retry ok")


def test_429_retry_after_then_success():
    responses = [_FakeResponse(429, {"retry-after": "0"}), _FakeResponse(204)]
    transport = WebhookTransport("https://discord.com/api/webhooks/x/y", max_attempts=3)
    with patch("httpx.Client.post", side_effect=responses), \
         patch("alerts.delivery.time.sleep") as mock_sleep:
        result = transport.send({"content": "hi"})
    assert result.delivered is True
    mock_sleep.assert_called_with(0.0)
    print("429 retry-after ok")


def test_permanent_400_not_retried():
    transport = WebhookTransport("https://discord.com/api/webhooks/x/y", max_attempts=4)
    with patch("httpx.Client.post", return_value=_FakeResponse(400)) as mock_post:
        result = transport.send({"content": "hi"})
    assert mock_post.call_count == 1
    assert result.delivered is False
    assert result.error_type == "client_error"
    print("permanent 400 no-retry ok")


def test_invalid_webhook_url_no_crash():
    transport = WebhookTransport("not-a-valid-url", max_attempts=2)
    result = transport.send({"content": "hi"})  # real httpx call, no mock — must not raise
    assert result.delivered is False
    assert result.attempted is True
    print("invalid webhook url ok")


def test_redaction():
    assert redact_webhook_url("https://discord.com/api/webhooks/123/secrettoken") == "configured"
    assert redact_webhook_url(None) == "not_configured"
    assert redact_webhook_url("") == "not_configured"

    s = Settings(config_path="config/config.yaml")
    s.raw = {"discord": {"webhook_url": "https://discord.com/api/webhooks/123/secrettoken"}}
    assert "secrettoken" not in repr(s)
    assert "secrettoken" not in str(s)
    print("redaction ok")


def test_maintenance_dedup_suppresses_repeat_send():
    session = _session()
    alerter = MaintenanceAlerter("https://discord.com/api/webhooks/x/y", session=session, enabled=True)
    with patch("httpx.Client.post", return_value=_FakeResponse(204)) as mock_post:
        first = alerter.alert(source_id="samsung_us", problem="scheduler_stall", detail="d1", reason="scheduler_stall")
        second = alerter.alert(source_id="samsung_us", problem="scheduler_stall", detail="d2", reason="scheduler_stall")
    assert first is True
    assert second is False
    assert mock_post.call_count == 1
    rows = session.query(WebhookDelivery).filter(WebhookDelivery.channel == "maintenance").all()
    assert any(r.suppressed for r in rows)
    print("maintenance dedup ok")


def test_baseline_import_suppression():
    assert newsroom_eligible("new_model", backfill=True) is False
    assert newsroom_eligible("new_model", backfill=False) is True
    print("baseline import suppression ok")


def test_resighting_suppression():
    assert newsroom_eligible("unchanged_resighting") is False
    print("re-sighting suppression ok")


def test_maintenance_unknown_reason_fails_closed():
    assert maintenance_eligible("something_made_up") is False
    print("maintenance fail-closed ok")


def test_synthetic_test_excluded_from_intelligence_counts():
    session = _session()
    session.add(WebhookDelivery(
        channel="newsroom", reason="synthetic_test", test_mode=True,
        eligible=True, suppressed=False, attempted=True, delivered=True,
    ))
    session.add(WebhookDelivery(
        channel="newsroom", reason="new_model", test_mode=False,
        eligible=True, suppressed=False, attempted=True, delivered=True,
    ))
    session.commit()

    intelligence_count = session.query(WebhookDelivery).filter(
        WebhookDelivery.channel == "newsroom", WebhookDelivery.test_mode.is_(False)
    ).count()
    diagnostics_count = session.query(WebhookDelivery).filter(
        WebhookDelivery.channel == "newsroom"
    ).count()
    assert intelligence_count == 1
    assert diagnostics_count == 2
    print("synthetic test exclusion ok")


def test_newsroom_and_maintenance_routing_separation():
    session = _session()
    newsroom = DiscordAlerter(
        webhook_url="https://discord.com/api/webhooks/newsroom/token",
        enabled=True, session_factory=lambda: session,
    )
    maintenance = MaintenanceAlerter(
        webhook_url="https://discord.com/api/webhooks/maintenance/token",
        session=session, enabled=True,
    )
    calls = []

    def fake_post(self, url, **kwargs):
        calls.append(url)
        return _FakeResponse(204)

    with patch("httpx.Client.post", new=fake_post):
        newsroom._send("hello", reason="new_model", source_id="samsung_us_support_sitemap")
        maintenance.alert(source_id="s1", problem="db_integrity_failure", detail="d", reason="db_integrity_failure")
        session.commit()

    assert calls[0] == "https://discord.com/api/webhooks/newsroom/token"
    assert calls[1] == "https://discord.com/api/webhooks/maintenance/token"

    rows = session.query(WebhookDelivery).all()
    channels_seen = {r.channel for r in rows}
    assert channels_seen == {"newsroom", "maintenance"}
    print("routing separation ok")


def test_device_persistence_survives_alert_failure():
    session = _session()
    alerter = DiscordAlerter(
        webhook_url="https://discord.com/api/webhooks/x/y",
        enabled=True, session_factory=lambda: session,
    )
    device = Device(manufacturer="samsung", model_number="SM-TEST1", confidence=50)
    session.add(device)
    session.flush()

    with patch("httpx.Client.post", side_effect=httpx.ConnectError("boom")), \
         patch("alerts.delivery.time.sleep"):
        result = alerter.alert_new_device(device)

    assert result is None  # delivery failed
    session.commit()  # must not raise / roll back the device
    assert session.query(Device).filter(Device.model_number == "SM-TEST1").count() == 1
    print("device persistence survives alert failure ok")


def run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
