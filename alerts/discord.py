"""
Discord webhook alerts — newsroom channel.
Only fire on meaningful intelligence updates (see alerts/eligibility.py).
"""

from __future__ import annotations

import logging
from typing import Optional

from alerts.delivery import DeliveryResult, WebhookTransport
from alerts.eligibility import newsroom_eligible
from database.models import Alert, Device, WebhookDelivery

logger = logging.getLogger("clank.alerts")

_SOURCE_REASON_HINTS = (
    ("firmware", "firmware_added"),
    ("sitemap", "new_sitemap_url"),
    ("manual", "manual_added"),
    ("regional", "new_regional_variant"),
    ("official", "official_status_change"),
)


def _reason_for_source(source: Optional[str]) -> str:
    if source:
        low = source.lower()
        for hint, reason in _SOURCE_REASON_HINTS:
            if hint in low:
                return reason
    return "support_page_change"


class DiscordAlerter:
    def __init__(
        self,
        webhook_url: str,
        min_confidence: int = 20,
        significant_delta: int = 15,
        enabled: bool = True,
        session_factory=None,
        backfill: bool = False,
        staging_label: bool = False,
    ):
        self.webhook_url = webhook_url
        self.min_confidence = min_confidence
        self.significant_delta = significant_delta
        self.enabled = enabled and bool(webhook_url)
        self.session_factory = session_factory
        self.backfill = backfill
        # spec (Wave 1 integration, section 25): every staging-environment
        # message must be visibly labelled so an operator can never mistake
        # it for a real production newsroom alert. This only changes message
        # *content* — eligibility/delivery/dedupe logic is untouched.
        self.staging_label = staging_label
        self.transport = WebhookTransport(webhook_url if enabled else None)

    def _send(
        self,
        content: str,
        embeds: list | None = None,
        *,
        reason: str = "support_page_change",
        extra_eligible: bool = True,
        session=None,
    ) -> Optional[str]:
        """Always records a `WebhookDelivery` row (via `_record_delivery`
        below) — this is the one place every newsroom send decision funnels
        through, so it's the one place that must never be bypassed by an
        early return elsewhere. `extra_eligible` lets a caller fold in a
        business-rule condition (e.g. `alert_new_device`'s confidence
        threshold) that `newsroom_eligible(reason, ...)` doesn't know about;
        it is AND-ed with the normal reason/backfill/enabled checks, not a
        replacement for them.

        `session`, when given (the pipeline always passes its own), is
        reused for the WebhookDelivery write instead of opening a second
        SQLite connection — this call happens mid-transaction inside
        `pipeline.process_discoveries()`, and a second writer connection to
        the same file while that transaction is still open can raise
        "database is locked". Callers outside a pipeline transaction (CLI
        synthetic tests, standalone alerter use) can omit it; `_record_delivery`
        falls back to `self.session_factory()` as before.

        Returns the literal string "sent" if `result.delivered` is True, else
        None — a truthy/falsy delivery signal, not a real Discord message id
        (this transport doesn't request `?wait=true`, so no id is ever
        available). Callers use this to gate `record_alert()`: a
        `WebhookDelivery` row is written regardless of outcome, but an
        `Alert` row must only ever be written when this returns non-None."""
        if self.staging_label:
            content = "🧪 **STAGING — NOT A PRODUCTION ALERT**\n" + content
        eligible = extra_eligible and self.enabled and newsroom_eligible(reason, backfill=self.backfill)
        payload = {"content": content}
        if embeds:
            payload["embeds"] = embeds
        result = self.transport.send(payload, eligible=eligible, suppressed=not self.enabled)
        self._record_delivery(reason, result, dedupe_key=None, session=session)
        return "sent" if result.delivered else None

    def _record_delivery(
        self, reason: str, result: DeliveryResult, *, dedupe_key: Optional[str],
        test_mode: bool = False, session=None,
    ) -> None:
        """If `session` is given, adds+flushes into it — the caller (its
        transaction, e.g. pipeline.process_discoveries()'s `session_scope`)
        owns the commit, so this write becomes atomic with whatever device/
        evidence/Alert work is happening in the same call. Otherwise opens
        and commits its own session, as a standalone fire-and-forget write —
        the original behavior, still correct for callers with no transaction
        of their own to join."""
        if session is not None:
            try:
                session.add(WebhookDelivery(
                    channel="newsroom",
                    reason=reason,
                    dedupe_key=dedupe_key,
                    test_mode=test_mode,
                    **_result_kwargs(result),
                ))
                session.flush()
            except Exception as e:
                logger.error("failed to persist webhook delivery record: %s", type(e).__name__)
            return

        if self.session_factory is None:
            return
        try:
            own_session = self.session_factory()
            try:
                own_session.add(WebhookDelivery(
                    channel="newsroom",
                    reason=reason,
                    dedupe_key=dedupe_key,
                    test_mode=test_mode,
                    **_result_kwargs(result),
                ))
                own_session.commit()
            finally:
                own_session.close()
        except Exception as e:
            logger.error("failed to persist webhook delivery record: %s", type(e).__name__)

    def _fmt_timeline(self, events: list, limit: int = 6) -> str:
        if not events:
            return "—"
        lines = []
        for ev in events[-limit:]:
            date = ev.occurred_at.strftime("%b %d") if ev.occurred_at else "?"
            label = ev.source or ev.event_type
            lines.append(f"{date}  {label}")
        return "\n".join(lines)

    def alert_new_device(
        self,
        device: Device,
        timeline: list | None = None,
        knowledge_bits: dict | None = None,
        session=None,
    ) -> Optional[str]:
        reason = "new_model"
        confidence_met = device.confidence >= self.min_confidence

        evidence_list = ", ".join(sorted({e.source for e in device.evidence})) or "none"
        name = device.marketing_name or device.model_number
        kb = knowledge_bits or {}

        lines = [
            f"**🆕 New Device Detected**",
            f"**{name}**",
            f"Model: `{device.model_number}`",
            f"Manufacturer: {device.manufacturer.title()}",
            f"Confidence: **{device.confidence}**",
            f"Evidence: {evidence_list}",
        ]
        if kb.get("family"):
            lines.append(f"Family: {kb['family']}")
        if kb.get("tier"):
            lines.append(f"Tier: {kb['tier']}")
        if kb.get("variant"):
            lines.append(f"Variant: {kb['variant']}")
        if timeline:
            lines.append("Timeline:")
            lines.append(self._fmt_timeline(timeline))
        if device.first_seen:
            lines.append(f"First seen: {device.first_seen.strftime('%Y-%m-%d %H:%M UTC')}")

        return self._send("\n".join(lines), reason=reason, extra_eligible=confidence_met, session=session)

    def alert_device_updated(
        self,
        device: Device,
        old_confidence: int,
        new_source: str | None = None,
        timeline: list | None = None,
        session=None,
    ) -> Optional[str]:
        delta = device.confidence - old_confidence
        significant = delta >= self.significant_delta or bool(new_source)
        reason = _reason_for_source(new_source)

        evidence_sources = sorted({e.source for e in device.evidence})
        prev = [s for s in evidence_sources if s != new_source]
        name = device.marketing_name or device.model_number

        lines = [
            f"**🔄 Device Updated**",
            f"**{name}**",
            f"Model: `{device.model_number}`",
            f"Confidence: {old_confidence} → **{device.confidence}** (+{delta})",
        ]
        if new_source:
            lines.append(f"New Evidence: **{new_source}**")
        if prev:
            lines.append(f"Previous evidence: {', '.join(prev)}")
        if timeline:
            lines.append("Timeline:")
            lines.append(self._fmt_timeline(timeline))

        link = next((e.url for e in device.evidence if e.url), None)
        if link:
            lines.append(f"Link: {link}")

        return self._send("\n".join(lines), reason=reason, extra_eligible=significant, session=session)

    def alert_confidence_up(self, device: Device, old_confidence: int, new_source: str | None = None) -> Optional[str]:
        return self.alert_device_updated(device, old_confidence, new_source=new_source)

    def record_alert(
        self,
        session,
        device: Device,
        alert_type: str,
        message: str,
        discord_id: str | None = None,
        payload: dict | None = None,
    ) -> None:
        """An `Alert` row means exactly one thing: this newsroom message was
        actually delivered to Discord. `WebhookDelivery` (written for every
        attempt by `_record_delivery`, regardless of outcome) is the source
        of truth for eligible/suppressed/attempted/delivered/failed —
        `alerts/delivery.py::channel_summary()` reads from there, not here.

        Refuses (logs, does not raise — a bug here must never break device
        persistence) rather than writing a row for anything that wasn't
        delivered, so `SELECT COUNT(*) FROM alerts` is always exactly the
        delivered-alert count with no caveats. Callers pass `discord_id` as
        the truthy/falsy delivery signal returned by `_send()` (see its
        docstring — not currently a real Discord message id, a pre-existing
        simplification, unchanged by this fix) and must gate their own call
        on it being truthy; this check is the second, authoritative gate."""
        if not discord_id:
            logger.warning(
                "record_alert called without a delivered discord_id (device=%s, alert_type=%s) — "
                "refusing to write a phantom Alert row",
                device.id, alert_type,
            )
            return
        alert = Alert(
            device_id=device.id,
            alert_type=alert_type,
            message=message,
            confidence_at_alert=device.confidence,
            discord_message_id=discord_id,
            payload=payload,
        )
        session.add(alert)


def _result_kwargs(result: DeliveryResult) -> dict:
    from datetime import datetime
    return {
        "eligible": result.eligible,
        "suppressed": result.suppressed,
        "attempted": result.attempted,
        "delivered": result.delivered,
        "status_code": result.status_code,
        "error_type": result.error_type,
        "error_message": result.error_message,
        "attempted_at": datetime.fromisoformat(result.attempted_at) if result.attempted_at else None,
        "delivered_at": datetime.fromisoformat(result.delivered_at) if result.delivered_at else None,
    }
