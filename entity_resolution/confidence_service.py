"""
Central confidence service — the only approved way to change device.confidence.
All pipeline paths must call apply() / invalidate() / recalculate().
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Device, Evidence
from entity_resolution.confidence_ledger import ConfidenceLedger, ConfidenceLedgerEntry
from entity_resolution.decay import ConfidenceDecay

logger = logging.getLogger("clank.confidence_service")


class ConfidenceService:
    def __init__(self, session: Session, decay: ConfidenceDecay | None = None):
        self.session = session
        self.ledger = ConfidenceLedger(session)
        self.decay = decay or ConfidenceDecay()

    def apply(
        self,
        device: Device,
        *,
        rule_id: str,
        points: int,
        evidence_id: Optional[str] = None,
        explanation: str = "",
        meta: Optional[dict] = None,
        allow_zero: bool = False,
    ) -> Optional[ConfidenceLedgerEntry]:
        """Apply a positive or negative confidence contribution via ledger."""
        if points == 0 and not allow_zero:
            return None
        entry = self.ledger.record(
            device,
            rule=rule_id,
            points=points,
            evidence_id=evidence_id,
            raw_weight=points,
            explanation=explanation or rule_id,
            meta=meta,
        )
        if entry is None:
            logger.debug(f"suppressed duplicate {rule_id} on {device.model_number}")
        return entry

    def invalidate(
        self,
        device: Device,
        *,
        rule_id: str,
        original_evidence_id: Optional[str] = None,
        points_to_reverse: int,
        explanation: str = "evidence invalidated",
    ) -> ConfidenceLedgerEntry:
        """Compensating ledger entry — does not delete history."""
        return self.ledger.record(
            device,
            rule=f"invalidate:{rule_id}",
            points=-abs(points_to_reverse),
            evidence_id=f"inv:{original_evidence_id}" if original_evidence_id else None,
            raw_weight=-abs(points_to_reverse),
            explanation=explanation,
            meta={"invalidates": rule_id, "original_evidence_id": original_evidence_id},
        ) or ConfidenceLedgerEntry()  # type: ignore

    def recalculate(self, device: Device, *, repair: bool = False) -> dict:
        """
        Recompute confidence from non-invalidated ledger entries + decay on evidence.
        Returns audit dict.
        """
        stored = int(device.confidence or 0)
        entries = self.ledger.entries_for_device(device.id)
        calculated = 0
        for e in entries:
            if e.duplicate_suppressed:
                continue
            if e.rule.startswith("invalidate:"):
                calculated += e.points  # already negative
            else:
                calculated += e.points
        # optional decay pass on evidence weights (does not rewrite ledger)
        self.decay.recompute_device(self.session, device)
        decayed = int(device.confidence or 0)
        # For audit: ledger sum is ground truth if we route everything through ledger
        drift = stored - calculated
        if repair:
            device.confidence = calculated
        else:
            # restore stored unless repair
            device.confidence = stored
        return {
            "model": device.model_number,
            "stored": stored,
            "ledger_sum": calculated,
            "after_decay_pass": decayed,
            "drift": drift,
            "repaired": repair,
        }

    def audit_all(self, repair: bool = False) -> dict:
        devices = self.session.query(Device).filter(Device.active == True).all()  # noqa: E712
        exact = 0
        drifts = []
        for d in devices:
            r = self.recalculate(d, repair=repair)
            if r["drift"] == 0:
                exact += 1
            else:
                drifts.append(r)
        drifts.sort(key=lambda x: abs(x["drift"]), reverse=True)
        return {
            "devices_checked": len(devices),
            "exact_matches": exact,
            "drift_detected": len(drifts),
            "largest": drifts[0] if drifts else None,
            "drifts": drifts[:20],
        }
