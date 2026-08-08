"""
Entity Resolution — the most important component.

Merges discoveries that refer to the same logical device.
Handles regional variants (SM-S957B / SM-S957U / SM-S957N etc.).
Never creates duplicate devices for identical model numbers.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Device, Evidence
from models.schemas import Discovery, Manufacturer, SourceType


class EntityResolver:
    def __init__(self, session: Session, weights: dict[str, int], regional_suffixes: list[str] | None = None):
        self.session = session
        self.weights = weights
        # YAML may parse bare 0 as int — always coerce to str for endswith()
        raw = regional_suffixes or ["B", "U", "N", "W", "E", "J", "Z", "0"]
        self.regional_suffixes = [str(s) for s in raw if s is not None and str(s) != ""]

    def _normalize_model(self, model: str) -> str:
        return model.strip().upper().replace(" ", "").replace("-", "")

    def _extract_family_key(self, model: str) -> str:
        """
        Strip common regional suffixes to get a family key.
        SM-S957B → SMS957
        SM-S957U → SMS957
        Pixel 10 Pro → PIXEL10PRO (no change)
        """
        cleaned = self._normalize_model(model or "")
        if not cleaned:
            return ""
        # Common pattern: ends with 1-2 letter regional code after digits
        for suffix in self.regional_suffixes:
            suffix = str(suffix)
            if not suffix:
                continue
            if cleaned.endswith(suffix) and len(cleaned) > len(suffix) + 3:
                # Only strip if the character before is a digit (typical for Samsung etc.)
                if cleaned[-len(suffix) - 1].isdigit():
                    return cleaned[: -len(suffix)]
        return cleaned

    def _source_weight(self, source_type: SourceType | str) -> int:
        mapping = {
            SourceType.SUPPORT_PAGE: "support_page",
            SourceType.CERTIFICATION: "certification",
            SourceType.FIRMWARE: "firmware",
            SourceType.OTA: "ota",
            SourceType.RETAIL: "retail_listing",
            SourceType.OFFICIAL: "official_announcement",
        }
        key = mapping.get(source_type, "certification")
        if isinstance(source_type, str):
            key = source_type if source_type in self.weights else key
        return self.weights.get(key, 10)

    def find_existing(self, manufacturer: str, model_number: str) -> Optional[Device]:
        """Exact match first."""
        return (
            self.session.query(Device)
            .filter(
                Device.manufacturer == manufacturer.lower(),
                Device.model_number == model_number.upper(),
            )
            .first()
        )

    def find_family(self, manufacturer: str, model_number: str) -> Optional[Device]:
        """
        Look for a parent / family device by stripping regional suffixes.
        Returns the first non-variant device that matches the family key.
        """
        family_key = self._extract_family_key(model_number)
        candidates = (
            self.session.query(Device)
            .filter(Device.manufacturer == manufacturer.lower())
            .all()
        )
        for dev in candidates:
            if self._extract_family_key(dev.model_number) == family_key:
                # Prefer the non-variant / earliest one as parent
                if not dev.is_variant:
                    return dev
        return None

    def resolve(self, discovery: Discovery) -> tuple[Device, bool, bool]:
        """
        Resolve a discovery into a Device record.

        Returns:
            (device, is_new_device, evidence_added)
        """
        mfr = (discovery.manufacturer.value if discovery.manufacturer else "unknown").lower()
        model = discovery.model_number.strip().upper()

        # 1. Exact match?
        device = self.find_existing(mfr, model)
        is_new = False

        if device is None:
            # 2. Family match? → create as variant
            family = self.find_family(mfr, model)
            device = Device(
                manufacturer=mfr,
                model_number=model,
                marketing_name=discovery.marketing_name,
                codename=discovery.codename,
                region=discovery.region,
                first_seen=discovery.discovered_at or datetime.utcnow(),
                last_seen=discovery.discovered_at or datetime.utcnow(),
                confidence=0,
                is_variant=family is not None,
                family_id=family.id if family else None,
            )
            self.session.add(device)
            self.session.flush()  # get id
            is_new = True

        # 3. Add evidence
        # Prefer scored weight from support-page classifier when present
        weight = self._source_weight(discovery.source_type)
        if discovery.raw and isinstance(discovery.raw.get("_weight"), int) and discovery.raw["_weight"] > 0:
            weight = int(discovery.raw["_weight"])
        source_type_str = discovery.source_type.value if hasattr(discovery.source_type, "value") else str(discovery.source_type)
        evidence = Evidence(
            device_id=device.id,
            source=discovery.source,
            source_type=source_type_str,
            title=discovery.marketing_name or discovery.model_number,
            model_number=model,
            url=discovery.url,
            published_at=discovery.published_at,
            first_seen=discovery.discovered_at or datetime.utcnow(),
            last_seen=discovery.discovered_at or datetime.utcnow(),
            raw_data=discovery.raw or None,
            confidence_contribution=weight,
            original_weight=weight,
            content_hash=discovery.content_hash,
            decays=(source_type_str != "official"),
        )

        # Deduplicate evidence
        existing_ev = (
            self.session.query(Evidence)
            .filter(
                Evidence.device_id == device.id,
                Evidence.source == discovery.source,
            )
            .all()
        )
        evidence_added = True
        for ev in existing_ev:
            # Exact same content → refresh only
            if discovery.content_hash and ev.content_hash == discovery.content_hash:
                ev.last_seen = datetime.utcnow()
                evidence_added = False
                break
            # Same URL with same/missing hash → refresh only
            # Different content_hash on same URL = real page change → new evidence
            if discovery.url and ev.url == discovery.url:
                if not discovery.content_hash or not ev.content_hash or discovery.content_hash == ev.content_hash:
                    ev.last_seen = datetime.utcnow()
                    evidence_added = False
                    break

        if evidence_added:
            self.session.add(evidence)
            self.session.flush()  # evidence id available for ledger
            # Confidence is applied only via ConfidenceService in pipeline

        # Always refresh last_seen on valid re-sighting (idempotent; no evidence/confidence)
        device.last_seen = datetime.utcnow()
        if discovery.marketing_name and not device.marketing_name:
            device.marketing_name = discovery.marketing_name
        if discovery.codename and not device.codename:
            device.codename = discovery.codename
        if discovery.region and not device.region:
            device.region = discovery.region

        return device, is_new, evidence_added
