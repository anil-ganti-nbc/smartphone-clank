"""
Device Family relationships.

Galaxy S27 family
  ├── Ultra
  ├── Plus
  ├── Base
  └── FE
Regional variants hang under a model; models hang under a family.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Device, DeviceFamily
from knowledge.enrichment import KnowledgeBase

logger = logging.getLogger("clank.families")


class FamilyService:
    def __init__(self, session: Session, knowledge: Optional[KnowledgeBase] = None):
        self.session = session
        self.kb = knowledge or KnowledgeBase()

    def get_or_create_family(
        self,
        manufacturer: str,
        name: str,
        series: Optional[str] = None,
        tier: Optional[str] = None,
        year: Optional[int] = None,
    ) -> DeviceFamily:
        existing = (
            self.session.query(DeviceFamily)
            .filter(
                DeviceFamily.manufacturer == manufacturer.lower(),
                DeviceFamily.name == name,
            )
            .first()
        )
        if existing:
            return existing
        fam = DeviceFamily(
            manufacturer=manufacturer.lower(),
            name=name,
            series=series,
            tier=tier,
            year=year,
        )
        self.session.add(fam)
        self.session.flush()
        return fam

    def infer_and_attach(self, device: Device) -> Optional[DeviceFamily]:
        """
        Use knowledge enrichment to guess family name, then attach.
        Never invent a family name that has no supporting pattern.
        """
        enriched = self.kb.enrich(
            model_number=device.model_number,
            manufacturer=device.manufacturer,
            marketing_name=device.marketing_name,
            codename=device.codename,
        )
        if not enriched.family:
            return None

        # Try to make a more specific family name if we have marketing name
        fam_name = enriched.family
        if device.marketing_name:
            # e.g. "Galaxy S27 Ultra" → family "Galaxy S27"
            m = re.match(r"(?i)(galaxy\s+s\s*\d+|galaxy\s+z\s+\w+|pixel\s+\d+|nothing\s+phone\s*\d*)", device.marketing_name)
            if m:
                fam_name = m.group(1).strip().title()

        fam = self.get_or_create_family(
            manufacturer=device.manufacturer,
            name=fam_name,
            series=enriched.family,
            tier=enriched.product_tier,
        )
        device.explicit_family_id = fam.id
        device.family_name = fam.name
        if enriched.product_tier and not device.product_tier:
            device.product_tier = enriched.product_tier
        return fam

    def family_tree(self, family_id: str) -> dict:
        fam = self.session.query(DeviceFamily).filter(DeviceFamily.id == family_id).first()
        if not fam:
            return {}
        members = (
            self.session.query(Device)
            .filter(Device.explicit_family_id == family_id)
            .order_by(Device.model_number)
            .all()
        )
        return {
            "family": fam.name,
            "manufacturer": fam.manufacturer,
            "tier": fam.tier,
            "members": [
                {
                    "model": d.model_number,
                    "marketing": d.marketing_name,
                    "variant": d.variant_label or d.region,
                    "confidence": d.confidence,
                    "is_variant": d.is_variant,
                }
                for d in members
            ],
        }
