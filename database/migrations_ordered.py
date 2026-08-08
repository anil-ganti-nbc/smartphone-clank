"""
Ordered schema migrations (lightweight Alembic-style without requiring alembic package).

Each revision is an explicit function that alters schema.
create_all is NOT used as a migration step.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

REVISIONS: list[tuple[str, str, Callable[[sqlite3.Connection], None]]] = []


def _revision(version: str, description: str):
    def deco(fn):
        REVISIONS.append((version, description, fn))
        return fn
    return deco


@_revision("0.2.1", "baseline v0.2.1 core tables")
def migrate_021(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id VARCHAR(36) PRIMARY KEY,
            manufacturer VARCHAR(32) NOT NULL,
            model_number VARCHAR(64) NOT NULL,
            marketing_name VARCHAR(128),
            codename VARCHAR(64),
            region VARCHAR(32),
            family_id VARCHAR(36),
            is_variant BOOLEAN DEFAULT 0,
            first_seen DATETIME,
            last_seen DATETIME,
            confidence INTEGER DEFAULT 0,
            notes TEXT,
            active BOOLEAN DEFAULT 1,
            family_name VARCHAR(128),
            product_tier VARCHAR(32),
            variant_label VARCHAR(64),
            possible_launch_month INTEGER,
            expected_chipset_class VARCHAR(32),
            knowledge_confidence VARCHAR(16),
            explicit_family_id VARCHAR(36),
            base_confidence INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS evidence (
            id VARCHAR(36) PRIMARY KEY,
            device_id VARCHAR(36) NOT NULL,
            source VARCHAR(64) NOT NULL,
            source_type VARCHAR(32) NOT NULL,
            title VARCHAR(256),
            model_number VARCHAR(64),
            url VARCHAR(1024),
            published_at DATETIME,
            first_seen DATETIME,
            last_seen DATETIME,
            raw_data JSON,
            confidence_contribution INTEGER DEFAULT 0,
            original_weight INTEGER DEFAULT 0,
            content_hash VARCHAR(64),
            decays BOOLEAN DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            id VARCHAR(36) PRIMARY KEY,
            source VARCHAR(64) NOT NULL,
            url VARCHAR(1024) NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            text_hash VARCHAR(64),
            dom_hash VARCHAR(64),
            download_hash VARCHAR(64),
            image_hash VARCHAR(64),
            content TEXT,
            fetched_at DATETIME,
            status_code INTEGER,
            change_summary JSON,
            manufacturer VARCHAR(32),
            model_number VARCHAR(64),
            collector VARCHAR(64),
            content_length INTEGER,
            title VARCHAR(512),
            classifications JSON,
            meaningful BOOLEAN,
            fingerprint_json JSON
        );
        CREATE TABLE IF NOT EXISTS aliases (
            id VARCHAR(36) PRIMARY KEY,
            device_id VARCHAR(36) NOT NULL,
            alias_type VARCHAR(32) NOT NULL,
            value VARCHAR(128) NOT NULL,
            manufacturer VARCHAR(32),
            first_seen DATETIME,
            last_seen DATETIME,
            source VARCHAR(64),
            confidence INTEGER DEFAULT 50
        );
        CREATE TABLE IF NOT EXISTS timeline_events (
            id VARCHAR(36) PRIMARY KEY,
            device_id VARCHAR(36) NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            source VARCHAR(64),
            title VARCHAR(256),
            url VARCHAR(1024),
            occurred_at DATETIME NOT NULL,
            recorded_at DATETIME,
            evidence_id VARCHAR(36),
            meta JSON
        );
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version VARCHAR(32) NOT NULL,
            applied_at DATETIME,
            description TEXT
        );
        """
    )


@_revision("0.3.0", "v0.3 ledger, sightings, health, relationships")
def migrate_030(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS confidence_ledger (
            id VARCHAR(36) PRIMARY KEY,
            device_id VARCHAR(36) NOT NULL,
            evidence_id VARCHAR(36),
            rule VARCHAR(64) NOT NULL,
            raw_weight INTEGER DEFAULT 0,
            decay_adjustment INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            previous_confidence INTEGER DEFAULT 0,
            new_confidence INTEGER DEFAULT 0,
            duplicate_suppressed BOOLEAN DEFAULT 0,
            explanation TEXT,
            meta JSON,
            created_at DATETIME
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_device_evidence_rule
            ON confidence_ledger(device_id, evidence_id, rule);
        CREATE TABLE IF NOT EXISTS regional_sightings (
            id VARCHAR(36) PRIMARY KEY,
            device_id VARCHAR(36) NOT NULL,
            source_id VARCHAR(64) NOT NULL,
            region VARCHAR(8) NOT NULL,
            locale VARCHAR(16),
            model_as_presented VARCHAR(64),
            marketing_name VARCHAR(128),
            url VARCHAR(1024),
            first_seen DATETIME,
            last_seen DATETIME,
            active BOOLEAN DEFAULT 1,
            evidence_confidence INTEGER DEFAULT 0,
            snapshot_id VARCHAR(36)
        );
        CREATE TABLE IF NOT EXISTS device_relationships (
            id VARCHAR(36) PRIMARY KEY,
            parent_device_id VARCHAR(36),
            child_device_id VARCHAR(36) NOT NULL,
            relationship_type VARCHAR(32) NOT NULL,
            status VARCHAR(32) DEFAULT 'proposed',
            confidence FLOAT DEFAULT 0.5,
            reasons JSON,
            supporting_evidence JSON,
            manual_review BOOLEAN DEFAULT 0,
            created_at DATETIME
        );
        CREATE TABLE IF NOT EXISTS source_health (
            id VARCHAR(36) PRIMARY KEY,
            source_id VARCHAR(64) UNIQUE NOT NULL,
            last_attempt DATETIME,
            last_success_http DATETIME,
            last_success_parse DATETIME,
            consecutive_failures INTEGER DEFAULT 0,
            consecutive_empty_parses INTEGER DEFAULT 0,
            last_latency_ms INTEGER,
            status_code_counts JSON,
            pages_fetched INTEGER DEFAULT 0,
            candidates_extracted INTEGER DEFAULT 0,
            candidates_accepted INTEGER DEFAULT 0,
            rejected_count INTEGER DEFAULT 0,
            meaningful_discoveries INTEGER DEFAULT 0,
            baseline_candidate_count FLOAT,
            health_status VARCHAR(32) DEFAULT 'unknown',
            breakage_reason TEXT,
            meta JSON,
            updated_at DATETIME
        );
        CREATE TABLE IF NOT EXISTS rejected_candidates (
            id VARCHAR(36) PRIMARY KEY,
            source_id VARCHAR(64) NOT NULL,
            raw_value VARCHAR(128) NOT NULL,
            reason VARCHAR(128) NOT NULL,
            url VARCHAR(1024),
            category_hint VARCHAR(32),
            created_at DATETIME
        );
        CREATE TABLE IF NOT EXISTS page_monitors (
            id VARCHAR(36) PRIMARY KEY,
            source VARCHAR(64) NOT NULL,
            url VARCHAR(1024) NOT NULL,
            manufacturer VARCHAR(32),
            model_number VARCHAR(64),
            consecutive_not_found INTEGER DEFAULT 0,
            last_status INTEGER,
            last_checked DATETIME,
            is_removed BOOLEAN DEFAULT 0,
            removed_at DATETIME,
            restored_at DATETIME,
            meta JSON
        );
        CREATE TABLE IF NOT EXISTS download_assets (
            id VARCHAR(36) PRIMARY KEY,
            device_id VARCHAR(36),
            source VARCHAR(64) NOT NULL,
            url VARCHAR(1024) NOT NULL,
            normalized_url VARCHAR(1024) NOT NULL,
            title VARCHAR(256),
            filename VARCHAR(256),
            file_type VARCHAR(32),
            category VARCHAR(64),
            language VARCHAR(16),
            region VARCHAR(32),
            version VARCHAR(64),
            first_seen DATETIME,
            last_seen DATETIME,
            active BOOLEAN DEFAULT 1
        );
        """
    )


@_revision("0.3.1", "v0.3.1 discovery URLs, polling state, novelty")
def migrate_031(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS discovered_urls (
            id VARCHAR(36) PRIMARY KEY,
            url VARCHAR(1024) NOT NULL UNIQUE,
            origin_type VARCHAR(32) NOT NULL,
            origin_source VARCHAR(64) NOT NULL,
            discovered_at DATETIME,
            first_fetched_at DATETIME,
            last_fetched_at DATETIME,
            discovery_run_id VARCHAR(36),
            status VARCHAR(32) DEFAULT 'new',
            polling_state VARCHAR(32) DEFAULT 'newly_discovered',
            previous_polling_state VARCHAR(32),
            state_changed_at DATETIME,
            next_run DATETIME,
            interval_minutes INTEGER DEFAULT 180,
            state_reason TEXT,
            failure_backoff INTEGER DEFAULT 0,
            meaningful_change_count INTEGER DEFAULT 0,
            etag VARCHAR(128),
            last_modified VARCHAR(128),
            meta JSON
        );
        CREATE TABLE IF NOT EXISTS discovery_runs (
            id VARCHAR(36) PRIMARY KEY,
            source_id VARCHAR(64) NOT NULL,
            started_at DATETIME,
            finished_at DATETIME,
            pages_fetched INTEGER DEFAULT 0,
            urls_discovered INTEGER DEFAULT 0,
            models_found INTEGER DEFAULT 0,
            errors JSON,
            meta JSON
        );
        CREATE TABLE IF NOT EXISTS maintenance_alerts (
            id VARCHAR(36) PRIMARY KEY,
            alert_key VARCHAR(128) NOT NULL,
            source_id VARCHAR(64),
            severity VARCHAR(16) DEFAULT 'warning',
            message TEXT NOT NULL,
            first_sent_at DATETIME,
            last_sent_at DATETIME,
            resolved_at DATETIME,
            send_count INTEGER DEFAULT 1,
            payload JSON
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_maint_alert_key ON maintenance_alerts(alert_key);
        """
    )


def _db_path_from_url(url: str) -> Optional[str]:
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "")
    return None


def current_version(url: str) -> Optional[str]:
    path = _db_path_from_url(url)
    if not path or not Path(path).exists():
        return None
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        if not cur.fetchone():
            return None
        row = conn.execute(
            "SELECT version FROM schema_version ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def backup(url: str, backup_dir: str = "data/backups") -> Optional[str]:
    path = _db_path_from_url(url)
    if not path or not Path(path).exists():
        return None
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    dest = str(Path(backup_dir) / f"clank_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db")
    shutil.copy2(path, dest)
    return dest


def history(url: str) -> list[tuple[str, str]]:
    path = _db_path_from_url(url)
    if not path or not Path(path).exists():
        return []
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        if not cur.fetchone():
            return []
        rows = conn.execute(
            "SELECT version, COALESCE(description,'') FROM schema_version ORDER BY id"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        conn.close()


def upgrade(url: str, target: Optional[str] = None) -> list[str]:
    """Apply pending revisions in order. Returns list of applied versions."""
    path = _db_path_from_url(url)
    if path is None:
        raise ValueError("ordered migrations currently support sqlite:/// paths only")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    applied: list[str] = []
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version VARCHAR(32) NOT NULL,
                applied_at DATETIME,
                description TEXT
            )
            """
        )
        existing = {
            r[0]
            for r in conn.execute("SELECT version FROM schema_version").fetchall()
        }
        for version, desc, fn in REVISIONS:
            if version in existing:
                continue
            if target and version > target:
                break
            fn(conn)
            conn.execute(
                "INSERT INTO schema_version(version, applied_at, description) VALUES (?,?,?)",
                (version, datetime.utcnow().isoformat(), desc),
            )
            conn.commit()
            applied.append(version)
            existing.add(version)
        return applied
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
