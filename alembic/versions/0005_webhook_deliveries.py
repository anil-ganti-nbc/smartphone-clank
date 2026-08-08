"""v0.3.9 webhook delivery log

Revision ID: 0005_webhook_deliveries
Revises: 0004_v032
Create Date: 2026-08-08
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0005_webhook_deliveries"
down_revision: Union[str, None] = "0004_v032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
            id VARCHAR(36) PRIMARY KEY,
            channel VARCHAR(16) NOT NULL,
            reason VARCHAR(64) NOT NULL,
            dedupe_key VARCHAR(64),
            test_mode BOOLEAN DEFAULT 0,
            eligible BOOLEAN DEFAULT 0,
            suppressed BOOLEAN DEFAULT 0,
            attempted BOOLEAN DEFAULT 0,
            delivered BOOLEAN DEFAULT 0,
            status_code INTEGER,
            error_type VARCHAR(32),
            error_message VARCHAR(320),
            attempted_at DATETIME,
            delivered_at DATETIME,
            created_at DATETIME
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_channel_created ON webhook_deliveries(channel, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webhook_deliveries")
