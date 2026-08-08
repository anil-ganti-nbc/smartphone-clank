"""
Explainable confidence ledger.
Every confidence change is decomposable into individual contributions.
Idempotent: same evidence+rule does not double-count.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from database.models import Base, Device, Evidence

logger = logging.getLogger("clank.confidence_ledger")


def _uuid() -> str:
    return str(uuid4())


class ConfidenceLedgerEntry(Base):
    __tablename__ = "confidence_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"), nullable=False, index=True)
    evidence_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    rule: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_weight: Mapped[int] = mapped_column(Integer, default=0)
    decay_adjustment: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    previous_confidence: Mapped[int] = mapped_column(Integer, default=0)
    new_confidence: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_suppressed: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("device_id", "evidence_id", "rule", name="uq_ledger_device_evidence_rule"),
        Index("ix_ledger_device_created", "device_id", "created_at"),
    )


class ConfidenceLedger:
    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        device: Device,
        *,
        rule: str,
        points: int,
        evidence_id: Optional[str] = None,
        raw_weight: Optional[int] = None,
        decay_adjustment: int = 0,
        explanation: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> Optional[ConfidenceLedgerEntry]:
        """
        Record a contribution. Returns None if duplicate-suppressed.
        Updates device.confidence.
        """
        if evidence_id:
            existing = (
                self.session.query(ConfidenceLedgerEntry)
                .filter(
                    ConfidenceLedgerEntry.device_id == device.id,
                    ConfidenceLedgerEntry.evidence_id == evidence_id,
                    ConfidenceLedgerEntry.rule == rule,
                )
                .first()
            )
            if existing:
                # already counted — do not mark original as suppressed
                return None
            # pending check
            for obj in self.session.new:
                if (
                    isinstance(obj, ConfidenceLedgerEntry)
                    and obj.device_id == device.id
                    and obj.evidence_id == evidence_id
                    and obj.rule == rule
                ):
                    return None

        prev = int(device.confidence or 0)
        new_conf = prev + int(points)
        entry = ConfidenceLedgerEntry(
            device_id=device.id,
            evidence_id=evidence_id,
            rule=rule,
            raw_weight=raw_weight if raw_weight is not None else points,
            decay_adjustment=decay_adjustment,
            points=points,
            previous_confidence=prev,
            new_confidence=new_conf,
            explanation=explanation or rule,
            meta=meta,
        )
        device.confidence = new_conf
        self.session.add(entry)
        return entry

    def entries_for_device(self, device_id: str) -> list[ConfidenceLedgerEntry]:
        return (
            self.session.query(ConfidenceLedgerEntry)
            .filter(ConfidenceLedgerEntry.device_id == device_id)
            .order_by(ConfidenceLedgerEntry.created_at.asc())
            .all()
        )

    def summary(self, device: Device) -> dict:
        rows = self.entries_for_device(device.id)
        return {
            "device": device.model_number,
            "confidence": device.confidence,
            "contributions": [
                {
                    "rule": r.rule,
                    "points": r.points,
                    "evidence_id": r.evidence_id,
                    "previous": r.previous_confidence,
                    "new": r.new_confidence,
                    "explanation": r.explanation,
                    "at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
                if not r.duplicate_suppressed
            ],
        }
