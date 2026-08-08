"""
Device Timeline — append-only chronological event history.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Device, TimelineEvent

logger = logging.getLogger("clank.timeline")


class TimelineService:
    def __init__(self, session: Session):
        self.session = session

    def add_event(
        self,
        device: Device,
        event_type: str,
        source: Optional[str] = None,
        title: Optional[str] = None,
        url: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        evidence_id: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> TimelineEvent:
        """Append a timeline event. Never deletes."""
        event = TimelineEvent(
            device_id=device.id,
            event_type=event_type,
            source=source,
            title=title or event_type,
            url=url,
            occurred_at=occurred_at or datetime.utcnow(),
            evidence_id=evidence_id,
            meta=meta,
        )
        self.session.add(event)
        return event

    def get_timeline(self, device_id: str) -> list[TimelineEvent]:
        return (
            self.session.query(TimelineEvent)
            .filter(TimelineEvent.device_id == device_id)
            .order_by(TimelineEvent.occurred_at.asc())
            .all()
        )

    def get_timeline_by_model(self, model_number: str, manufacturer: Optional[str] = None) -> list[TimelineEvent]:
        q = self.session.query(Device).filter(Device.model_number == model_number.upper())
        if manufacturer:
            q = q.filter(Device.manufacturer == manufacturer.lower())
        device = q.first()
        if not device:
            return []
        return self.get_timeline(device.id)
