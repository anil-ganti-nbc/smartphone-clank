"""Source-maturity / soak notification suppression tests.

Campaign rule under test: a NEW source begins in soak maturity; during
soak its discoveries may persist but can NEVER reach the newsroom
channel — suppression is explicit policy with persisted evidence rows
(WebhookDelivery.suppressed=1), never an absent webhook credential.
Fail-closed: unknown/absent source ids are soak by definition.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from alerts.delivery import DeliveryResult
from alerts.discord import DiscordAlerter
from alerts.source_maturity import (
    MATURITY_PRODUCTION,
    MATURITY_SOAK,
    PRODUCTION_SOURCES,
    notifications_allowed,
    source_maturity,
)
from database.models import Base, Device


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class _RecordingTransport:
    """Records whether a send was even attempted; never touches network."""

    def __init__(self):
        self.attempts: list[dict] = []

    def send(self, payload, *, eligible: bool, suppressed: bool) -> DeliveryResult:
        if suppressed or not eligible:
            result = DeliveryResult(eligible=eligible, suppressed=suppressed, attempted=False, delivered=False)
        else:
            result = DeliveryResult(eligible=True, suppressed=False, attempted=True, delivered=True, status_code=204)
        self.attempts.append({"eligible": eligible, "suppressed": suppressed, "attempted": result.attempted})
        return result


def _alerter(session) -> DiscordAlerter:
    a = DiscordAlerter(
        webhook_url="https://discord.example/webhook",
        enabled=True,
        session_factory=lambda: session,
    )
    a.transport = _RecordingTransport()
    return a


# -- classification -------------------------------------------------------------

def test_currently_promoted_sources_hold_production_authority():
    for sid in (
        "samsung_us_support_sitemap",
        "google_store_category_phones",
        "nothing_products_sitemap",
        "oneplus_regional_sitemap",
        "motorola_regional_sitemap",
        "honor_global_sitemap",
        "oppo_global_sitemap",
        "realme_regional_sitemap",
    ):
        assert source_maturity(sid) == MATURITY_PRODUCTION, sid
        assert notifications_allowed(sid) is True


def test_unknown_and_absent_sources_fail_closed_to_soak():
    assert source_maturity("brand_new_unannounced_source") == MATURITY_SOAK
    # samsung_us_owners_product was promoted to production maturity on
    # 2026-09-05 (explicit operator decision), so it is no longer an example
    # of the fail-closed default. The default itself is unchanged and is
    # still proven by the unknown/None cases above and below.
    assert source_maturity("another_unregistered_source") == MATURITY_SOAK
    assert source_maturity(None) == MATURITY_SOAK
    assert notifications_allowed(None) is False


def test_canary_membership_alone_still_confers_no_authority():
    """CANARY means production execution while authority is decided
    separately in PRODUCTION_SOURCES. That separation is the invariant, and
    it survives the 2026-09-05 promotion: authority still comes only from a
    reviewed edit to this registry, never from the canary transition itself
    (Fleet Law 8).

    samsung_us_owners_product has now received exactly that reviewed edit,
    so it is production. A canary source that has NOT been granted authority
    is still suppressed — proven here with a hypothetical member so the
    guarantee keeps a test even though the real canary set is now fully
    promoted."""
    from collectors import CANARY_SAMSUNG_SOURCE_IDS

    assert "samsung_us_owners_product" in CANARY_SAMSUNG_SOURCE_IDS
    # Promoted: canary AND production is now a legitimate combination.
    assert source_maturity("samsung_us_owners_product") == "production"
    assert notifications_allowed("samsung_us_owners_product") is True
    # The mechanism is unchanged: membership in the canary set is not what
    # grants authority — absence from PRODUCTION_SOURCES still suppresses.
    assert source_maturity("hypothetical_future_canary") == MATURITY_SOAK
    assert notifications_allowed("hypothetical_future_canary") is False


# -- suppression evidence ---------------------------------------------------------

def _device(session, **kwargs) -> Device:
    d = Device(
        manufacturer="samsung",
        model_number="SM-SOAK1",
        marketing_name="Soak Test Device",
        confidence=80,
        **kwargs,
    )
    session.add(d)
    session.flush()
    return d


def test_soak_source_suppression_is_explicit_and_evidence_bearing():
    session = _session()
    device = _device(session)
    alerter = _alerter(session)

    msg_id = alerter._send(
        "content irrelevant",
        reason="new_model",
        extra_eligible=True,
        # A source with soak maturity. samsung_us_owners_product used to
        # serve here; it was promoted to production on 2026-09-05, so the
        # suppression mechanism is now proven with a source that is actually
        # still soak — the behaviour under test is unchanged.
        source_id="unpromoted_soak_source",
        session=session,
    )
    session.commit()

    # No network attempt at all — suppression happens before the transport
    # would ever go out (the recorder saw a gate call, none attempted).
    assert all(not a["attempted"] for a in alerter.transport.attempts)
    assert msg_id is None

    # But the decision leaves durable evidence: one suppressed delivery row.
    row = session.execute(
        text("SELECT suppressed, eligible FROM webhook_deliveries")
    ).fetchone()
    assert row.suppressed == 1 and row.eligible == 0
    assert session.execute(text("SELECT COUNT(*) FROM alerts")).scalar() == 0


def test_absent_source_id_is_fail_closed_even_with_webhook_configured():
    session = _session()
    alerter = _alerter(session)

    msg_id = alerter._send("content", reason="new_model", extra_eligible=True, session=session)
    session.commit()

    assert msg_id is None
    assert all(not a["attempted"] for a in alerter.transport.attempts)
    row = session.execute(text("SELECT suppressed FROM webhook_deliveries")).fetchone()
    assert row.suppressed == 1


def test_production_source_still_delivers_through_the_same_gate():
    session = _session()
    device = _device(session)
    alerter = _alerter(session)

    msg_id = alerter.alert_new_device(
        device, session=session, source_id="samsung_us_support_sitemap"
    )
    if msg_id:
        alerter.record_alert(session, device, "new_device", "New device SM-SOAK1", msg_id)
    session.commit()

    assert msg_id == "sent"
    assert len(alerter.transport.attempts) == 1
    assert alerter.transport.attempts[0]["attempted"] is True
    assert session.execute(text("SELECT COUNT(*) FROM alerts")).scalar() == 1


def test_maturity_gate_is_independent_of_enabled_flag():
    """A disabled alerter suppresses anyway, but the SOAK path must not
    depend on it: enabled=True + soak source => suppressed; enabled=False +
    production source => suppressed for a different reason. The delivery
    rows make both visible."""
    session = _session()
    device = _device(session)

    soak_alerter = _alerter(session)
    assert soak_alerter.alert_new_device(
        device, session=session, source_id="new_soak_source"
    ) is None

    disabled = DiscordAlerter(
        webhook_url="https://discord.example/webhook",
        enabled=False,
        session_factory=lambda: session,
    )
    disabled.transport = _RecordingTransport()
    assert disabled.alert_new_device(
        device, session=session, source_id="samsung_us_support_sitemap"
    ) is None

    rows = session.execute(text("SELECT suppressed FROM webhook_deliveries")).fetchall()
    assert all(r.suppressed == 1 for r in rows)


# ---------------------------------------------------------------- promotion guard


def test_no_active_collector_holds_non_production_maturity():
    """Fleet guard (operator decision 2026-09-05): every ACTIVE collector
    holds production maturity. Sources disabled for their own reason are a
    separate axis and are deliberately excluded — promotion moves maturity,
    it does not enable a disabled source."""
    from alerts.source_maturity import MATURITY_PRODUCTION, source_maturity
    from collectors import CANARY_SAMSUNG_SOURCE_IDS, RUNNABLE_SAMSUNG_SOURCE_IDS

    # samsung_support is enabled: false in config/config.yaml ("secondary
    # monitoring only"), so it is not an active collector.
    disabled_by_config = {"samsung_support"}
    active = (RUNNABLE_SAMSUNG_SOURCE_IDS | CANARY_SAMSUNG_SOURCE_IDS) - disabled_by_config

    stragglers = [s for s in sorted(active) if source_maturity(s) != MATURITY_PRODUCTION]
    assert stragglers == [], f"active collectors still below production maturity: {stragglers}"


def test_promotion_did_not_enable_a_config_disabled_source():
    """samsung_support stays disabled and stays soak. Promoting maturity must
    never silently switch on a source that is off for another reason."""
    import yaml

    from alerts.source_maturity import MATURITY_SOAK, source_maturity

    repo_root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load((repo_root / "config" / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["collectors"]["samsung_support"]["enabled"] is False
    assert source_maturity("samsung_support") == MATURITY_SOAK


def test_fail_closed_default_survives_the_promotion():
    """The maturity gate is still fail-closed for anything unregistered."""
    from alerts.source_maturity import MATURITY_SOAK, notifications_allowed, source_maturity

    assert source_maturity("never_seen_before") == MATURITY_SOAK
    assert source_maturity(None) == MATURITY_SOAK
    assert notifications_allowed("never_seen_before") is False
