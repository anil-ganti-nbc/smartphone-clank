"""
Pydantic models for normalized device intelligence.
Unknown fields stay null — never invent data.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


class Manufacturer(str, Enum):
    SAMSUNG = "samsung"
    GOOGLE = "google"
    ONEPLUS = "oneplus"
    NOTHING = "nothing"
    XIAOMI = "xiaomi"
    # Wave 2 qualification (docs/wave2/) — staging-only, never production
    # scope. See collectors/wave1/__init__.py::WAVE1_PRODUCTION_SCOPE, which
    # this list has no bearing on.
    MOTOROLA = "motorola"
    HONOR = "honor"
    OPPO = "oppo"
    VIVO = "vivo"
    REALME = "realme"
    ASUS = "asus"


class SourceType(str, Enum):
    CERTIFICATION = "certification"
    SUPPORT_PAGE = "support_page"
    FIRMWARE = "firmware"
    OTA = "ota"
    RETAIL = "retail"
    OFFICIAL = "official"
    OTHER = "other"


class EvidenceItem(BaseModel):
    """Single piece of evidence attached to a device."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str  # e.g. "bis", "bluetooth_sig", "samsung_support"
    source_type: SourceType
    title: Optional[str] = None
    model_number: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    raw_data: Optional[dict[str, Any]] = None
    confidence_contribution: int = 0
    content_hash: Optional[str] = None

    class Config:
        from_attributes = True


class DeviceRecord(BaseModel):
    """
    Canonical device profile. All evidence for the same logical device
    is merged here over time.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    manufacturer: Manufacturer
    model_number: str  # Primary / representative model number
    marketing_name: Optional[str] = None
    codename: Optional[str] = None
    region: Optional[str] = None
    family_id: Optional[str] = None  # Parent for regional variants
    is_variant: bool = False

    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    confidence: int = 0
    evidence: list[EvidenceItem] = Field(default_factory=list)

    # Optional metadata
    notes: Optional[str] = None
    active: bool = True

    class Config:
        from_attributes = True

    def add_evidence(self, item: EvidenceItem, weight: int) -> bool:
        """
        Add evidence if not already present (by source + content_hash or url).
        Returns True if new evidence was added.
        """
        for existing in self.evidence:
            if existing.source == item.source:
                if item.content_hash and existing.content_hash == item.content_hash:
                    existing.last_seen = datetime.utcnow()
                    return False
                if item.url and existing.url == item.url:
                    existing.last_seen = datetime.utcnow()
                    return False

        item.confidence_contribution = weight
        self.evidence.append(item)
        self.confidence += weight
        self.last_seen = datetime.utcnow()
        return True


class Discovery(BaseModel):
    """Raw discovery emitted by a collector before normalization."""
    manufacturer: Optional[Manufacturer] = None
    model_number: str
    marketing_name: Optional[str] = None
    codename: Optional[str] = None
    region: Optional[str] = None
    source: str
    source_type: SourceType
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    raw: dict[str, Any] = Field(default_factory=dict)
    content_hash: Optional[str] = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)


class CollectorRunResult(BaseModel):
    collector: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    discoveries: int = 0
    new_devices: int = 0
    updated_devices: int = 0
    errors: list[str] = Field(default_factory=list)
    retries: int = 0
