"""
SQLAlchemy models. Designed so PostgreSQL can replace SQLite later
with minimal changes (just the connection URL + dialect specifics).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid4())


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    manufacturer: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    marketing_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    codename: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    family_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True)
    is_variant: Mapped[bool] = mapped_column(Boolean, default=False)

    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # v0.2 knowledge enrichment (nullable, never invent)
    family_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    product_tier: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    variant_label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    possible_launch_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expected_chipset_class: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    knowledge_confidence: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    explicit_family_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("device_families.id"), nullable=True)
    base_confidence: Mapped[int] = mapped_column(Integer, default=0)  # pre-decay sum of contributions

    evidence: Mapped[list["Evidence"]] = relationship(
        "Evidence", back_populates="device", cascade="all, delete-orphan"
    )
    family: Mapped[Optional["Device"]] = relationship("Device", remote_side=[id])

    __table_args__ = (
        UniqueConstraint("manufacturer", "model_number", name="uq_manufacturer_model"),
        Index("ix_devices_confidence", "confidence"),
        Index("ix_devices_last_seen", "last_seen"),
    )


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    model_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    confidence_contribution: Mapped[int] = mapped_column(Integer, default=0)  # current (post-decay)
    original_weight: Mapped[int] = mapped_column(Integer, default=0)           # initial weight
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    decays: Mapped[bool] = mapped_column(Boolean, default=True)               # official never decays

    device: Mapped["Device"] = relationship("Device", back_populates="evidence")

    __table_args__ = (
        Index("ix_evidence_source_hash", "source", "content_hash"),
    )


class Source(Base):
    """Track known sources / pages we monitor."""
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_success: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class Snapshot(Base):
    """HTML / content snapshots for multi-hash change detection."""
    __tablename__ = "snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # full HTML
    text_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)       # visible text
    dom_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)        # structural
    download_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)   # download section
    image_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)      # image srcs
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # optional full store
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    change_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    model_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    collector: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    content_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    classifications: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    meaningful: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    fingerprint_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_snapshots_source_url", "source", "url"),
        Index("ix_snapshots_model", "model_number"),
    )


class CollectorRun(Base):
    __tablename__ = "collector_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    collector: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(nullable=True)
    discoveries: Mapped[int] = mapped_column(Integer, default=0)
    new_devices: Mapped[int] = mapped_column(Integer, default=0)
    updated_devices: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    # production_scheduled | production_manual | validation | demo | test | fixture
    run_reason: Mapped[str] = mapped_column(String(32), default="production_manual")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)  # new_device | confidence_up | new_source
    message: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_at_alert: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    discord_message_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class Alias(Base):
    """
    Persistent alias table.
    Links codenames, marketing names, and alternate model numbers
    to a canonical device. Survives restarts.
    """
    __tablename__ = "aliases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"), nullable=False, index=True)
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False)  # model | marketing | codename | other
    value: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # where this alias was learned
    confidence: Mapped[int] = mapped_column(Integer, default=50)

    __table_args__ = (
        UniqueConstraint("manufacturer", "alias_type", "value", name="uq_alias_mfr_type_value"),
    )


class TimelineEvent(Base):
    """
    Chronological event history for a device.
    Events are never deleted — only appended.
    """
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)  # evidence source or system event
    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    evidence_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_timeline_device_occurred", "device_id", "occurred_at"),
    )


class DeviceFamily(Base):
    """
    Explicit family grouping (e.g. Galaxy S27 family).
    Models and regional variants hang under families.
    """
    __tablename__ = "device_families"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    manufacturer: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "Galaxy S27"
    series: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # S / Z / A / Pixel
    tier: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("manufacturer", "name", name="uq_family_mfr_name"),
    )


# Extend Device with optional knowledge + family link fields via alteration
# (kept additive — existing columns unchanged)


class HistoricalStat(Base):
    """
    Aggregated lead-time and evidence statistics.
    Updated periodically from observed devices that reached launch.
    """
    __tablename__ = "historical_stats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    metric: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # e.g. "avg_days_bluetooth_to_launch", "avg_evidence_count_before_launch"
    value: Mapped[float] = mapped_column(nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("manufacturer", "metric", name="uq_stat_mfr_metric"),
    )



class PageMonitor(Base):
    """Track consecutive failures for page-removal safety."""
    __tablename__ = "page_monitors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    consecutive_not_found: Mapped[int] = mapped_column(Integer, default=0)
    last_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_removed: Mapped[bool] = mapped_column(Boolean, default=False)
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    restored_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("source", "url", name="uq_page_monitor_source_url"),
    )


class DownloadAsset(Base):
    """Tracked downloadable assets linked to devices / pages."""
    __tablename__ = "download_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    filename: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("source", "normalized_url", name="uq_download_source_nurl"),
    )


class SitemapProductUrl(Base):
    """Per-URL fetch ledger for Samsung sitemap product pages."""
    __tablename__ = "sitemap_product_urls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    product_slug: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    series_hint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_discovered_in_sitemap_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_successful_fetch_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_content_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_result: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    active_in_sitemap: Mapped[bool] = mapped_column(Boolean, default=True)
    next_eligible_fetch_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    associated_device_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True, index=True)
    last_model_extracted: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("source_id", "normalized_url", name="uq_sitemap_url_source_nurl"),
        Index("ix_sitemap_url_next_eligible", "source_id", "next_eligible_fetch_at"),
        Index("ix_sitemap_url_last_success", "source_id", "last_successful_fetch_at"),
    )


class WebhookDelivery(Base):
    """Structured record of every Discord webhook send attempt (newsroom or maintenance)."""
    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # newsroom | maintenance
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    test_mode: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)
    attempted: Mapped[bool] = mapped_column(Boolean, default=False)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_webhook_deliveries_channel_created", "channel", "created_at"),
    )


class SitemapTraversalState(Base):
    """Cycle-level traversal state for a sitemap source."""
    __tablename__ = "sitemap_traversal_state"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    sitemap_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    total_eligible_urls: Mapped[int] = mapped_column(Integer, default=0)
    cursor_position: Mapped[int] = mapped_column(Integer, default=0)
    last_completed_cycle_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    current_cycle_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    urls_attempted_in_cycle: Mapped[int] = mapped_column(Integer, default=0)
    urls_succeeded_in_cycle: Mapped[int] = mapped_column(Integer, default=0)
    urls_failed_in_cycle: Mapped[int] = mapped_column(Integer, default=0)
    cycles_completed: Mapped[int] = mapped_column(Integer, default=0)
    last_run_start_cursor: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_run_end_cursor: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    strategy: Mapped[str] = mapped_column(String(64), default="oldest_checked_first")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
