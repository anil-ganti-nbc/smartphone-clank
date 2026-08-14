"""
Wave 1 OEM discovery adapter contract.

Collectors report. Validators validate. Resolvers resolve. Evidence services
persist. This module only defines the reporting shape — it must not contain
entity-resolution, confidence, or persistence logic (see docs/wave1/*.md and
spec section 10/32).

A DiscoveryAdapter differs from collectors.base.BaseCollector deliberately:
BaseCollector.collect() returns models.schemas.Discovery, which the existing
production pipeline resolves straight into entities. Wave 1 candidates must
never enter that path directly — DiscoveryResult is a lower-trust shape that
staging-only code turns into candidates, runs through an OEM-specific
model_validator, and only then (if VALID) into the same Discovery/pipeline
machinery Samsung uses. Keeping the type distinct makes it structurally
impossible to accidentally wire an unvalidated wave1 result into the
production confidence/evidence services.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

DISCOVERY = "discovery"
MONITORING = "monitoring"
CONFIRMATION = "confirmation"
SOURCE_ROLES = {DISCOVERY, MONITORING, CONFIRMATION}

EXPERIMENTAL = "EXPERIMENTAL"
LIVE_PARTIAL = "LIVE_PARTIAL"
LIVE_VALIDATED = "LIVE_VALIDATED"
BLOCKED = "BLOCKED"
UNSUPPORTED = "UNSUPPORTED"
VALIDATION_STATES = {EXPERIMENTAL, LIVE_PARTIAL, LIVE_VALIDATED, BLOCKED, UNSUPPORTED}


@dataclass
class DiscoveryResult:
    """
    What a Wave 1 adapter reports for one candidate. Deliberately dumb: no
    "is this new", "is this newsworthy", or "is this valid" judgment lives
    here (spec section 32) — that's the validator's and the intelligence
    layer's job, not the collector's.
    """
    manufacturer: str
    source: str                    # adapter.source_name
    source_url: str                # the specific page/endpoint fetched
    canonical_url: Optional[str] = None
    region: str = "unknown"
    candidate_identifier: Optional[str] = None       # raw candidate model/id string, unvalidated
    candidate_marketing_name: Optional[str] = None
    candidate_family: Optional[str] = None
    raw_reference: Optional[str] = None               # verbatim source text the identifier came from
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterMetrics:
    """Populated for real — unknown historical metrics stay unknown, never fabricated zero (spec 29)."""
    pages_requested: int = 0
    pages_fetched: int = 0
    bytes_downloaded: int = 0
    http_failures: int = 0
    timeouts: int = 0
    redirects: int = 0
    status_distribution: dict[str, int] = field(default_factory=dict)
    candidates_found: int = 0
    duration_ms: int = 0
    errors: list[str] = field(default_factory=list)


class DiscoveryAdapter:
    """
    Base contract for a Wave 1 OEM source adapter. Subclasses implement
    discover(); everything else (validation, entity resolution, evidence,
    confidence, alerting) happens downstream and is shared with Samsung.
    """

    manufacturer: str = "unknown"
    source_name: str = "unknown"
    source_role: str = DISCOVERY
    validation_state: str = EXPERIMENTAL
    # Catalogue/discovery adapters are expected to return at least one
    # candidate after a usable fetch. A genuinely-empty source must opt in
    # explicitly so an HTML consent/challenge shell cannot look healthy.
    allows_empty_result: bool = False

    def __init__(self, *, user_agent: str, min_delay: float = 1.5, timeout: int = 30, max_fetches_per_run: int = 20):
        self.user_agent = user_agent
        self.min_delay = min_delay
        self.timeout = timeout
        self.max_fetches_per_run = max_fetches_per_run
        self._last_request = 0.0
        assert self.source_role in SOURCE_ROLES, f"invalid source_role: {self.source_role}"
        assert self.validation_state in VALIDATION_STATES, f"invalid validation_state: {self.validation_state}"

    def discover(self) -> tuple[list[DiscoveryResult], AdapterMetrics]:
        raise NotImplementedError

    def _get(self, url: str, metrics: AdapterMetrics) -> Optional[httpx.Response]:
        """Polite, bounded GET shared by every OEM adapter. Never raises — records
        the failure on `metrics` and returns None so discover() can keep going."""
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self._last_request = time.monotonic()

        metrics.pages_requested += 1
        try:
            resp = httpx.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
                follow_redirects=True,
            )
        except httpx.TimeoutException:
            metrics.timeouts += 1
            metrics.errors.append(f"timeout: {url}")
            return None
        except httpx.HTTPError as e:
            metrics.http_failures += 1
            metrics.errors.append(f"{type(e).__name__}: {url}")
            return None

        status_key = str(resp.status_code)
        metrics.status_distribution[status_key] = metrics.status_distribution.get(status_key, 0) + 1
        if resp.history:
            metrics.redirects += len(resp.history)
        if resp.status_code >= 400:
            metrics.http_failures += 1
            return None

        metrics.pages_fetched += 1
        metrics.bytes_downloaded += len(resp.content)
        return resp
