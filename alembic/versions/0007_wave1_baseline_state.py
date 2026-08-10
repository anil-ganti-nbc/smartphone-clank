"""Wave 1 per-source baseline epoch tracking (universal schema — harmless
empty table on any deployment not running Wave 1 collectors)

Revision ID: 0007_wave1_baseline_state
Revises: 0006_run_provenance
Create Date: 2026-08-10
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0007_wave1_baseline_state"
down_revision: Union[str, None] = "0006_run_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wave1_baseline_state (
            source_id VARCHAR(64) PRIMARY KEY,
            manufacturer VARCHAR(32) NOT NULL,
            baseline_started_at DATETIME,
            baseline_completed_at DATETIME,
            baseline_version INTEGER DEFAULT 1,
            run_count INTEGER DEFAULT 0,
            last_run_at DATETIME,
            completion_criterion VARCHAR(64)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wave1_baseline_state_manufacturer ON wave1_baseline_state(manufacturer)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS wave1_baseline_state")
