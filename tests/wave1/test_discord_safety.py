"""
Staging Discord labeling + a PERMANENT regression proving a staging
environment can never reach the production webhook (spec sections 25-26).
"""

from __future__ import annotations

import os

import pytest

from alerts.discord import DiscordAlerter
from config.settings import load_settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("MAINTENANCE_DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("STAGING_DISCORD_WEBHOOK_URL", raising=False)


def test_staging_settings_never_pick_up_production_webhook_env_var(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/PRODUCTION_WEBHOOK")
    monkeypatch.setenv("STAGING_DISCORD_WEBHOOK_URL", "https://discord.example/STAGING_WEBHOOK")

    settings = load_settings("config/config.staging.yaml")
    assert settings.environment == "staging"
    assert settings.discord_webhook == "https://discord.example/STAGING_WEBHOOK"
    assert "PRODUCTION_WEBHOOK" not in settings.discord_webhook


def test_staging_settings_disabled_when_only_production_webhook_present(monkeypatch):
    """If an operator's shell happens to have DISCORD_WEBHOOK_URL set (e.g. for
    a production shell) and STAGING_DISCORD_WEBHOOK_URL is NOT set, staging
    must fail closed to 'no webhook' rather than silently borrowing the
    production URL."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/PRODUCTION_WEBHOOK")

    settings = load_settings("config/config.staging.yaml")
    assert settings.discord_webhook == ""


def test_production_settings_never_pick_up_staging_webhook_env_var(monkeypatch):
    monkeypatch.setenv("STAGING_DISCORD_WEBHOOK_URL", "https://discord.example/STAGING_WEBHOOK")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/PRODUCTION_WEBHOOK")

    settings = load_settings("config/config.yaml")
    assert settings.environment == "production"
    assert settings.discord_webhook == "https://discord.example/PRODUCTION_WEBHOOK"


def test_staging_alert_message_visibly_labelled(monkeypatch):
    sent_payloads = []

    class RecordingTransport:
        def __init__(self, url):
            self.url = url

        def send(self, payload, *, eligible, suppressed):
            sent_payloads.append((payload, eligible, suppressed))
            from alerts.delivery import DeliveryResult
            return DeliveryResult(eligible=eligible, suppressed=suppressed, attempted=eligible, delivered=eligible)

    monkeypatch.setattr("alerts.discord.WebhookTransport", RecordingTransport)

    alerter = DiscordAlerter(
        webhook_url="https://discord.example/STAGING_WEBHOOK",
        staging_label=True,
        backfill=False,
    )
    alerter._send("New candidate: Pixel 11", reason="new_model")

    assert len(sent_payloads) == 1
    content = sent_payloads[0][0]["content"]
    assert "STAGING" in content
    assert "NOT A PRODUCTION ALERT" in content


def test_production_webhook_delivery_attempts_zero_when_staging_and_no_staging_webhook(monkeypatch):
    """The concrete spec-26 assertion: environment=staging, no
    STAGING_DISCORD_WEBHOOK_URL configured -> zero delivery attempts to ANY
    webhook, including a production URL that happens to be present in the
    process environment."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/PRODUCTION_WEBHOOK")

    delivery_attempts = []

    class RecordingTransport:
        def __init__(self, url):
            self.url = url
            if url:
                delivery_attempts.append(url)

        def send(self, payload, *, eligible, suppressed):
            if eligible and not suppressed:
                delivery_attempts.append("SEND_CALLED")
            from alerts.delivery import DeliveryResult
            return DeliveryResult(eligible=eligible, suppressed=True, attempted=False, delivered=False)

    monkeypatch.setattr("alerts.discord.WebhookTransport", RecordingTransport)

    settings = load_settings("config/config.staging.yaml")
    alerter = DiscordAlerter(
        webhook_url=settings.discord_webhook,  # "" — no STAGING_DISCORD_WEBHOOK_URL set
        staging_label=True,
    )
    assert alerter.enabled is False
    alerter._send("test", reason="new_model")

    assert delivery_attempts == [], f"production webhook must never receive delivery attempts from staging: {delivery_attempts}"
