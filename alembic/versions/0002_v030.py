"""v0.3.0 ledger, sightings, health

Revision ID: 0002_v030
Revises: 0001_v021
Create Date: 2026-08-02
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0002_v030"
down_revision: Union[str, None] = "0001_v021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
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
        )
        """
    )
    op.execute(
        """
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
        )
        """
    )
    op.execute(
        """
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
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_health")
    op.execute("DROP TABLE IF EXISTS regional_sightings")
    op.execute("DROP TABLE IF EXISTS confidence_ledger")
