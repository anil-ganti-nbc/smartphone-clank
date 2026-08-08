"""v0.3.9 run provenance — run_reason + resighted counters

Revision ID: 0006_run_provenance
Revises: 0005_webhook_deliveries
Create Date: 2026-08-08
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0006_run_provenance"
down_revision: Union[str, None] = "0005_webhook_deliveries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE collector_runs ADD COLUMN run_reason VARCHAR(32) DEFAULT 'production_manual'")
    op.execute("ALTER TABLE collector_run_metrics ADD COLUMN resighted INTEGER DEFAULT 0")
    op.execute("ALTER TABLE collector_run_metrics ADD COLUMN run_reason VARCHAR(32) DEFAULT 'production_manual'")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_run_metrics_run_reason ON collector_run_metrics(run_reason)"
    )


def downgrade() -> None:
    # SQLite doesn't support DROP COLUMN pre-3.35 without a table rebuild; no-op downgrade.
    pass
