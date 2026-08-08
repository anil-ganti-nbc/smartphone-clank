"""
Persistent Codename / Alias Resolver.

Links internal codenames, marketing names, and alternate model numbers
to a canonical device. Aliases survive restarts and are reused automatically.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Alias, Device

logger = logging.getLogger("clank.aliases")


class AliasResolver:
    def __init__(self, session: Session):
        self.session = session

    def find_by_alias(
        self,
        value: str,
        manufacturer: Optional[str] = None,
        alias_type: Optional[str] = None,
    ) -> Optional[Device]:
        """Look up a device by any known alias."""
        q = self.session.query(Alias).filter(Alias.value == value.strip())
        if manufacturer:
            q = q.filter(Alias.manufacturer == manufacturer.lower())
        if alias_type:
            q = q.filter(Alias.alias_type == alias_type)
        alias = q.first()
        if not alias:
            # case-insensitive fallback
            q = self.session.query(Alias).filter(Alias.value.ilike(value.strip()))
            if manufacturer:
                q = q.filter(Alias.manufacturer == manufacturer.lower())
            alias = q.first()
        if alias:
            return self.session.query(Device).filter(Device.id == alias.device_id).first()
        return None

    def register(
        self,
        device: Device,
        value: str,
        alias_type: str,
        source: Optional[str] = None,
        confidence: int = 50,
    ) -> Alias:
        """
        Register or refresh an alias. Idempotent.
        """
        value = value.strip()
        if not value:
            raise ValueError("alias value cannot be empty")

        existing = (
            self.session.query(Alias)
            .filter(
                Alias.manufacturer == device.manufacturer,
                Alias.alias_type == alias_type,
                Alias.value == value,
            )
            .first()
        )
        if existing is None:
            # also check pending objects in this session
            for obj in self.session.new:
                if (
                    isinstance(obj, Alias)
                    and obj.manufacturer == device.manufacturer
                    and obj.alias_type == alias_type
                    and obj.value == value
                ):
                    existing = obj
                    break
        if existing:
            existing.last_seen = datetime.utcnow()
            if existing.device_id != device.id:
                logger.warning(
                    f"Alias conflict for {value}: existing device {existing.device_id} "
                    f"vs new {device.id}. Keeping existing."
                )
            return existing

        alias = Alias(
            device_id=device.id,
            alias_type=alias_type,
            value=value,
            manufacturer=device.manufacturer,
            source=source,
            confidence=confidence,
        )
        self.session.add(alias)
        logger.debug(f"Registered alias {alias_type}={value} → {device.model_number}")
        return alias

    def ensure_core_aliases(self, device: Device, source: Optional[str] = None) -> None:
        """Always keep model number + marketing name + codename as aliases."""
        self.register(device, device.model_number, "model", source=source, confidence=100)
        if device.marketing_name:
            self.register(device, device.marketing_name, "marketing", source=source, confidence=80)
        if device.codename:
            self.register(device, device.codename, "codename", source=source, confidence=90)

    def link_codename(self, device: Device, codename: str, source: Optional[str] = None) -> None:
        if codename:
            self.register(device, codename.strip(), "codename", source=source, confidence=85)
            if not device.codename:
                device.codename = codename.strip()
