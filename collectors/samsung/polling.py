"""
Adaptive polling state machine for discovered URLs.
Persists next_run, interval, reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


# defaults in minutes
INTERVALS = {
    "discovery_seed": 360,
    "newly_discovered": 30,
    "recently_changed": 45,
    "stable": 360,
    "officially_launched": 720,
    "removed": 1440,
    "failing": 120,  # base; multiplied by backoff
    "blocked": 10080,
    "disabled": 0,
}


@dataclass
class PollDecision:
    state: str
    interval_minutes: int
    next_run: datetime
    reason: str
    failure_backoff: int = 0


def transition(
    current_state: str,
    *,
    event: str,
    failure_backoff: int = 0,
    meaningful_changes_recent: int = 0,
    now: Optional[datetime] = None,
) -> PollDecision:
    """
    event: discovered | meaningful_change | no_change | fetch_error | removed | restored | launched | blocked
    """
    now = now or datetime.utcnow()
    state = current_state or "newly_discovered"
    backoff = failure_backoff

    if event == "blocked":
        state, reason = "blocked", "source blocked"
        backoff = 0
    elif event == "removed":
        state, reason = "removed", "confirmed removal"
    elif event == "restored":
        state, reason = "recently_changed", "page restored"
        backoff = 0
    elif event == "launched":
        state, reason = "officially_launched", "official product"
    elif event == "fetch_error":
        backoff = min(8, (failure_backoff or 0) + 1)
        state, reason = "failing", f"fetch error backoff x{backoff}"
    elif event == "meaningful_change":
        state, reason = "recently_changed", "meaningful change detected"
        backoff = 0
    elif event == "discovered":
        state, reason = "newly_discovered", "new URL discovered"
        backoff = 0
    elif event == "no_change":
        if state in ("newly_discovered", "recently_changed"):
            if meaningful_changes_recent == 0:
                state, reason = "stable", "no recent meaningful changes"
            else:
                reason = "still watching recent changes"
        elif state == "failing":
            state, reason = "stable", "recovered"
            backoff = 0
        else:
            reason = "stable poll"
    else:
        reason = f"unchanged after {event}"

    base = INTERVALS.get(state, 180)
    if state == "failing":
        base = INTERVALS["failing"] * (2 ** max(0, backoff - 1))
    interval = int(base)
    return PollDecision(
        state=state,
        interval_minutes=interval,
        next_run=now + timedelta(minutes=interval) if interval > 0 else now + timedelta(days=365),
        reason=reason,
        failure_backoff=backoff,
    )
