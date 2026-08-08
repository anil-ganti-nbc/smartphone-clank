"""v0.2.1 baseline core tables

Revision ID: 0001_v021
Revises:
Create Date: 2026-08-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001_v021"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Explicit DDL — not create_all
    op.execute(
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
        )
        """
    )
    op.execute(
        """
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
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version VARCHAR(32) NOT NULL,
            applied_at DATETIME,
            description TEXT
        )
        """
    )


def downgrade() -> None:
    pass  # baseline retained
