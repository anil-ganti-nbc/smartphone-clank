"""
Evidence Confidence Decay.

Old evidence gradually loses influence.
Official announcements never decay.
Rates are configurable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Device, Evidence

logger = logging.getLogger("clank.decay")


# Default decay schedule: (days_after_first_seen, remaining_fraction_of_original)
DEFAULT_DECAY_SCHEDULE = [
    (30, 0.90),
    (90, 0.75),
    (180, 0.50),
    (365, 0.30),
]


class ConfidenceDecay:
    def __init__(
        self,
        schedule: list[tuple[int, float]] | None = None,
        never_decay_types: set[str] | None = None,
    ):
        self.schedule = sorted(schedule or DEFAULT_DECAY_SCHEDULE, key=lambda x: x[0])
        self.never_decay_types = never_decay_types or {"official"}

    def _fraction_for_age(self, age_days: float) -> float:
        fraction = 1.0
        for days, frac in self.schedule:
            if age_days >= days:
                fraction = frac
            else:
                break
        return fraction

    def apply_to_evidence(self, evidence: Evidence, now: Optional[datetime] = None) -> int:
        """
        Recompute confidence_contribution from original_weight + age.
        Returns the new contribution.
        """
        now = now or datetime.utcnow()
        if not evidence.decays or evidence.source_type in self.never_decay_types:
            evidence.confidence_contribution = evidence.original_weight or evidence.confidence_contribution
            return evidence.confidence_contribution

        original = evidence.original_weight or evidence.confidence_contribution
        if original <= 0:
            return 0

        age = (now - evidence.first_seen).total_seconds() / 86400.0
        fraction = self._fraction_for_age(age)
        new_val = max(0, int(round(original * fraction)))
        evidence.confidence_contribution = new_val
        return new_val

    def recompute_device(self, session: Session, device: Device, now: Optional[datetime] = None) -> int:
        """
        Re-apply decay to all evidence of a device and update device.confidence.
        Returns new confidence.
        """
        now = now or datetime.utcnow()
        # Prefer DB query so newly-added evidence in this session is included
        evidence_list = (
            session.query(Evidence)
            .filter(Evidence.device_id == device.id)
            .all()
        )
        if not evidence_list:
            evidence_list = list(device.evidence or [])
        total = 0
        for ev in evidence_list:
            total += self.apply_to_evidence(ev, now=now)
        # Do NOT set device.confidence here — ConfidenceService owns that projection.
        if hasattr(device, "base_confidence"):
            base = sum(ev.original_weight or ev.confidence_contribution for ev in evidence_list)
            device.base_confidence = base
        return total

    def recompute_all(self, session: Session) -> int:
        """Batch recompute for all active devices. Returns number of devices touched."""
        devices = session.query(Device).filter(Device.active == True).all()  # noqa: E712
        count = 0
        for dev in devices:
            self.recompute_device(session, dev)
            count += 1
        logger.info(f"Decay recomputed for {count} devices")
        return count
