"""
v0.3 additive tables: regional sightings, source health, relationships, schema version.
Imported by migrations and init paths.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from database.models import Base


def _uuid() -> str:
    return str(uuid4())


class SchemaVersion(Base):
    __tablename__ = "schema_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RegionalSighting(Base):
    __tablename__ = "regional_sightings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str] = mapped_column(String(8), nullable=False)
    locale: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    model_as_presented: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    marketing_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    evidence_confidence: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        UniqueConstraint("device_id", "source_id", "region", name="uq_sighting_device_source_region"),
    )


class DeviceRelationship(Base):
    """Proposed or confirmed relationships between variants / models / families."""
    __tablename__ = "device_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    parent_device_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True)
    child_device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)  # regional_variant | family_member | proposed
    status: Mapped[str] = mapped_column(String(32), default="proposed")  # proposed | confirmed | rejected
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    reasons: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    supporting_evidence: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    manual_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SourceHealth(Base):
    __tablename__ = "source_health"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    last_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_success_http: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_success_parse: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_empty_parses: Mapped[int] = mapped_column(Integer, default=0)
    last_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status_code_counts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    candidates_extracted: Mapped[int] = mapped_column(Integer, default=0)
    candidates_accepted: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    meaningful_discoveries: Mapped[int] = mapped_column(Integer, default=0)
    baseline_candidate_count: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    health_status: Mapped[str] = mapped_column(String(32), default="unknown")
    breakage_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RejectedCandidate(Base):
    __tablename__ = "rejected_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_value: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    category_hint: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
