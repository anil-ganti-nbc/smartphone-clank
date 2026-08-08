"""
Separate maintenance Discord webhook — never mixed with newsroom alerts.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from alerts.delivery import DeliveryResult, WebhookTransport
from alerts.eligibility import maintenance_eligible
from database.models import WebhookDelivery

logger = logging.getLogger("clank.maintenance")


class MaintenanceAlerter:
    def __init__(
        self,
        webhook_url: str = "",
        session: Session | None = None,
        enabled: bool = True,
    ):
        self.webhook_url = webhook_url
        self.session = session
        self.enabled = enabled and bool(webhook_url)
        self.transport = WebhookTransport(webhook_url if enabled else None)

    def _key(self, source_id: str, problem: str) -> str:
        return hashlib.sha256(f"{source_id}:{problem}".encode()).hexdigest()[:32]

    def _record_delivery(self, reason: str, result: DeliveryResult, *, dedupe_key: Optional[str], test_mode: bool = False) -> None:
        if self.session is None:
            return
        try:
            self.session.add(WebhookDelivery(
                channel="maintenance",
                reason=reason,
                dedupe_key=dedupe_key,
                test_mode=test_mode,
                **_result_kwargs(result),
            ))
        except Exception as e:
            logger.error("failed to persist maintenance delivery record: %s", type(e).__name__)

    def alert(
        self,
        *,
        source_id: str,
        problem: str,
        detail: str,
        severity: str = "warning",
        reason: str = "collector_failure_streak",
    ) -> bool:
        """Send or dedupe a maintenance alert. Returns True if newly sent."""
        key = self._key(source_id, problem)
        eligible = maintenance_eligible(reason)

        # Dedupe: an unresolved incident with this key suppresses re-sending content.
        if self.session is not None:
            try:
                row = self.session.execute(
                    text("SELECT id, resolved_at FROM maintenance_alerts WHERE alert_key=:k"),
                    {"k": key},
                ).fetchone()
                if row and not row[1]:
                    self.session.execute(
                        text(
                            "UPDATE maintenance_alerts SET last_sent_at=:t, send_count=send_count+1 WHERE alert_key=:k"
                        ),
                        {"t": datetime.utcnow().isoformat(), "k": key},
                    )
                    logger.info("maintenance deduped: %s %s", source_id, problem)
                    result = DeliveryResult(eligible=eligible, suppressed=True)
                    self._record_delivery(reason, result, dedupe_key=key)
                    return False
            except Exception as e:
                logger.debug("maint dedupe lookup skipped: %s", type(e).__name__)

        msg = (
            f"**⚠️ Samsung Collector Degraded**\n"
            f"**Source:** {source_id}\n"
            f"**Problem:** {problem}\n"
            f"**Detail:** {detail}\n"
            f"**Severity:** {severity}\n"
            f"**At:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )
        result = self.transport.send({"content": msg}, eligible=eligible, suppressed=not self.enabled)
        self._record_delivery(reason, result, dedupe_key=key)

        if self.session is not None and eligible and self.enabled:
            try:
                self.session.execute(
                    text(
                        """
                        INSERT INTO maintenance_alerts
                            (id, alert_key, source_id, severity, message, first_sent_at, last_sent_at, send_count, payload)
                        VALUES (lower(hex(randomblob(16))), :k, :s, :sev, :m, :t, :t, 1, NULL)
                        ON CONFLICT(alert_key) DO UPDATE SET
                            last_sent_at=excluded.last_sent_at, send_count=send_count+1
                        """
                    ),
                    {"k": key, "s": source_id, "sev": severity, "m": msg, "t": datetime.utcnow().isoformat()},
                )
            except Exception as e:
                logger.debug("maint persist skipped: %s", type(e).__name__)

        return result.delivered or not self.enabled

    def recover(self, *, source_id: str, problem: str, detail: str = "recovered") -> bool:
        key = self._key(source_id, problem)
        msg = (
            f"**✅ Collector Recovered**\n"
            f"**Source:** {source_id}\n"
            f"**Was:** {problem}\n"
            f"**Detail:** {detail}"
        )
        eligible = True  # recovery notices always fire once an incident is open
        result = self.transport.send({"content": msg}, eligible=eligible, suppressed=not self.enabled)
        self._record_delivery("collector_failure_streak", result, dedupe_key=key)

        if self.session is not None:
            try:
                self.session.execute(
                    text("UPDATE maintenance_alerts SET resolved_at=:t WHERE alert_key=:k AND resolved_at IS NULL"),
                    {"t": datetime.utcnow().isoformat(), "k": key},
                )
            except Exception as e:
                logger.debug("maint recovery persist skipped: %s", type(e).__name__)

        return result.delivered or not self.enabled


def _result_kwargs(result: DeliveryResult) -> dict:
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
