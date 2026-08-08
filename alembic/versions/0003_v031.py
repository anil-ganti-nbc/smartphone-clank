"""v0.3.1 discovery urls and polling

Revision ID: 0003_v031
Revises: 0002_v030
Create Date: 2026-08-02
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0003_v031"
down_revision: Union[str, None] = "0002_v030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
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
        )
        """
    )
    op.execute(
        """
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
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS maintenance_alerts")
    op.execute("DROP TABLE IF EXISTS discovered_urls")
