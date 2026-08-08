"""v0.3.2 analyst actions and audit log

Revision ID: 0004_v032
Revises: 0003_v031
Create Date: 2026-08-02
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0004_v032"
down_revision: Union[str, None] = "0003_v031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analyst_actions (
            id VARCHAR(36) PRIMARY KEY,
            action VARCHAR(64) NOT NULL,
            target_type VARCHAR(32) NOT NULL,
            target_id VARCHAR(64) NOT NULL,
            actor_label VARCHAR(64) DEFAULT 'analyst',
            reason TEXT,
            before_state JSON,
            after_state JSON,
            related_evidence JSON,
            created_at DATETIME
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduler_jobs (
            id VARCHAR(36) PRIMARY KEY,
            job_key VARCHAR(128) NOT NULL UNIQUE,
            source_id VARCHAR(64),
            url VARCHAR(1024),
            polling_state VARCHAR(32),
            interval_minutes INTEGER,
            next_run DATETIME,
            last_run DATETIME,
            run_reason TEXT,
            failure_count INTEGER DEFAULT 0,
            lock_owner VARCHAR(64),
            lock_expiry DATETIME,
            enabled BOOLEAN DEFAULT 1,
            meta JSON
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scheduler_jobs")
    op.execute("DROP TABLE IF EXISTS analyst_actions")
