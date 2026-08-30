"""analyst_actions gains a terminal-decision uniqueness index (STD-UI-COM-002)

Operator decisions recorded by `qc-action` previously had no integrity
guard: two concurrent (or merely repeated) terminal decisions for the same
target both committed as indistinguishable rows, and provenance snapshot
columns were never populated.

Contract (Option A, operator-approved 2026-08-31): one authoritative
TERMINAL decision per (target_type, target_id), enforced by a partial
unique index; `note` stays a non-terminal, append-only annotation channel
and is exempt via the index predicate. The terminal/non-terminal split is
defined in database/analyst_actions.py (NON_TERMINAL_ACTIONS) and a test
pins this predicate to that set, so a future non-terminal action forces a
conscious migration change rather than being silently reclassified as
terminal. Collisions are resolved as explicit rejections by the write
path — never a second row, never an in-place update.

Revision ID: 0008_analyst_action_integrity
Revises: 0007_wave1_baseline_state
Create Date: 2026-08-31
"""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0008_analyst_action_integrity"
down_revision: Union[str, None] = "0007_wave1_baseline_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_analyst_action_terminal"
        " ON analyst_actions (target_type, target_id)"
        " WHERE action <> 'note'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_analyst_action_terminal")
