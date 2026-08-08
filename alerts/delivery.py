"""
Discord webhook transport: structured delivery results, retry/backoff,
429 handling, payload-length safeguards, and URL redaction.

Never raises — every failure mode resolves to a DeliveryResult so callers
(pipeline, CLI, alerters) can persist device/evidence work regardless of
webhook outcome.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger("clank.webhook")

DISCORD_CONTENT_LIMIT = 2000
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_BACKOFF_SECONDS = 1.0
_ERROR_MESSAGE_MAX_LEN = 300


def redact_webhook_url(url: Optional[str]) -> str:
    """Never return the URL itself — only whether one is configured."""
    return "configured" if url else "not_configured"


@dataclass
class DeliveryResult:
    eligible: bool
    suppressed: bool = False
    attempted: bool = False
    delivered: bool = False
    status_code: Optional[int] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    attempted_at: Optional[str] = None
    delivered_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _sanitize(text: str) -> str:
    return text[:_ERROR_MESSAGE_MAX_LEN]


def _not_configured_result(eligible: bool) -> DeliveryResult:
    return DeliveryResult(
        eligible=eligible,
        suppressed=False,
        attempted=False,
        delivered=False,
        error_type="webhook_not_configured",
    )


def _suppressed_result(eligible: bool) -> DeliveryResult:
    return DeliveryResult(eligible=eligible, suppressed=True, attempted=False, delivered=False)


class WebhookTransport:
    """Wraps a single webhook URL (newsroom or maintenance are separate instances)."""

    def __init__(
        self,
        webhook_url: Optional[str],
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ):
        self.webhook_url = webhook_url or ""
        self.timeout = timeout
        self.max_attempts = max_attempts

    @property
    def configured(self) -> bool:
        return bool(self.webhook_url)

    def send(self, payload: dict, *, eligible: bool = True, suppressed: bool = False) -> DeliveryResult:
        if suppressed:
            return _suppressed_result(eligible)
        if not eligible:
            return DeliveryResult(eligible=False, suppressed=False, attempted=False, delivered=False)
        if not self.configured:
            return _not_configured_result(eligible)

        payload = self._truncate_content(payload)
        attempted_at = datetime.utcnow().isoformat()

        status_code: Optional[int] = None
        error_type: Optional[str] = None
        error_message: Optional[str] = None
        backoff = DEFAULT_BACKOFF_SECONDS

        for attempt in range(1, self.max_attempts + 1):
            last_attempt = attempt == self.max_attempts
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(self.webhook_url, json=payload)
            except httpx.TimeoutException as e:
                error_type, error_message = "timeout", _sanitize(str(e))
                logger.error("webhook timeout (attempt %d/%d): %s", attempt, self.max_attempts, error_type)
            except httpx.HTTPError as e:
                error_type, error_message = "connection_error", _sanitize(str(e))
                logger.error("webhook connection error (attempt %d/%d): %s", attempt, self.max_attempts, error_type)
            except Exception as e:  # malformed URL, etc — never propagate
                error_type, error_message = "invalid_request", _sanitize(f"{type(e).__name__}: {e}")
                logger.error("webhook invalid request: %s", error_type)
                break
            else:
                status_code = resp.status_code
                if 200 <= resp.status_code < 300:
                    return DeliveryResult(
                        eligible=eligible,
                        suppressed=False,
                        attempted=True,
                        delivered=True,
                        status_code=status_code,
                        attempted_at=attempted_at,
                        delivered_at=datetime.utcnow().isoformat(),
                    )
                if resp.status_code == 429:
                    retry_after = resp.headers.get("retry-after")
                    wait = float(retry_after) if retry_after else backoff
                    error_type = "rate_limited"
                    error_message = _sanitize(f"429 retry-after={retry_after}")
                    logger.warning(
                        "webhook rate limited (attempt %d/%d), retry-after=%s",
                        attempt, self.max_attempts, retry_after,
                    )
                    if not last_attempt:
                        time.sleep(wait)
                        backoff *= 2
                    continue
                if 400 <= resp.status_code < 500:
                    # Permanent client error — do not retry.
                    error_type = "client_error"
                    error_message = _sanitize(f"HTTP {resp.status_code}")
                    logger.error("webhook permanent failure %d, not retrying", resp.status_code)
                    break
                # 5xx — retryable
                error_type = "server_error"
                error_message = _sanitize(f"HTTP {resp.status_code}")
                logger.error(
                    "webhook server error (attempt %d/%d): %d",
                    attempt, self.max_attempts, resp.status_code,
                )

            if not last_attempt:
                time.sleep(backoff)
                backoff *= 2

        return DeliveryResult(
            eligible=eligible,
            suppressed=False,
            attempted=True,
            delivered=False,
            status_code=status_code,
            error_type=error_type,
            error_message=error_message,
            attempted_at=attempted_at,
        )

    @staticmethod
    def _truncate_content(payload: dict) -> dict:
        content = payload.get("content")
        if isinstance(content, str) and len(content) > DISCORD_CONTENT_LIMIT:
            logger.warning("webhook payload truncated from %d to %d chars", len(content), DISCORD_CONTENT_LIMIT)
            payload = dict(payload)
            payload["content"] = content[: DISCORD_CONTENT_LIMIT - 1] + "…"
        return payload


def channel_summary(session, channel: str, *, start=None, end=None, test_mode: bool = False) -> dict:
    """
    eligible/suppressed/attempted/delivered/failed counts for a webhook channel,
    optionally windowed by created_at in [start, end). Single source of truth for
    the discord CLI, dashboard, and daily report — avoids re-deriving this query shape.
    """
    from database.models import WebhookDelivery

    q = session.query(WebhookDelivery).filter(
        WebhookDelivery.channel == channel, WebhookDelivery.test_mode.is_(test_mode)
    )
    if start is not None:
        q = q.filter(WebhookDelivery.created_at >= start)
    if end is not None:
        q = q.filter(WebhookDelivery.created_at < end)
    return {
        "eligible": q.filter(WebhookDelivery.eligible.is_(True)).count(),
        "suppressed": q.filter(WebhookDelivery.suppressed.is_(True)).count(),
        "attempted": q.filter(WebhookDelivery.attempted.is_(True)).count(),
        "delivered": q.filter(WebhookDelivery.delivered.is_(True)).count(),
        "failed": q.filter(WebhookDelivery.attempted.is_(True), WebhookDelivery.delivered.is_(False)).count(),
    }
