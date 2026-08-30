"""Analyst QC decision writes — the STD-UI-COM-002 decision contract.

`analyst_actions` is the operator decision record (written by the
`qc-action` CLI, ingested read-only by Motherclank). The contract:

- exactly ONE authoritative TERMINAL decision per
  (target_type, target_id), enforced by the partial unique index
  ``uq_analyst_action_terminal`` (migration 0008). A collision is
  resolved as an explicit rejection — the table stays append-only and a
  prior terminal decision is never mutated or re-written;
- ``note`` is a non-terminal annotation channel and remains append-only.
  The terminal/non-terminal split is defined here, in code
  (NON_TERMINAL_ACTIONS), and a test pins the migration's index predicate
  to this set — adding a future non-terminal action forces a conscious
  migration change instead of silently reclassifying it as terminal;
- every row carries a provenance snapshot of what the operator was
  deciding against (before_state / after_state / related_evidence),
  written in the SAME transaction as the decision itself.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

TERMINAL_ACTIONS = frozenset({"confirm", "reject", "quarantine", "promote"})
NON_TERMINAL_ACTIONS = frozenset({"note"})
KNOWN_ACTIONS = TERMINAL_ACTIONS | NON_TERMINAL_ACTIONS

ACTOR_CLI = "operator-cli"


class UnknownActionError(Exception):
    """Fail-closed: only the known vocabulary may be recorded, so a future
    action can never silently slide past the terminal-decision index."""


class UnknownTargetTypeError(Exception):
    """target_type must be a known entity kind ('device' | 'evidence')."""


class DuplicateTerminalDecision(Exception):
    """A terminal decision already exists for this target. Carries the
    existing row's identity so the caller can state exactly what was
    already recorded and by whom."""

    def __init__(self, existing: dict[str, Any]):
        self.existing = existing
        super().__init__(
            "terminal decision already recorded for "
            f"{existing.get('target_type')}:{existing.get('target_id')}"
            f" ({existing.get('action')} by {existing.get('actor_label')}"
            f" at {existing.get('created_at')})"
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _resolve_target_snapshot(
    session: Session, target_type: str, target_id: str
) -> tuple[Optional[dict[str, Any]], Optional[list[dict[str, Any]]]]:
    """Best-effort resolution of the target's current state, so the decision
    row records what the operator was actually looking at. Unknown ids are
    recorded honestly as unresolved rather than dropped."""
    from database.models import Device, Evidence

    if target_type == "device":
        row = session.get(Device, target_id)
        if row is None:
            row = (
                session.query(Device)
                .filter(Device.model_number == target_id.upper())
                .first()
            )
        if row is None:
            return None, None
        related = [
            {"id": e.id, "source": e.source, "url": e.url}
            for e in session.query(Evidence)
            .filter(Evidence.device_id == row.id)
            .limit(20)
            .all()
        ]
        before = {
            "model_number": row.model_number,
            "manufacturer": row.manufacturer,
            "marketing_name": row.marketing_name,
            "confidence": row.confidence,
            "first_seen": _iso(row.first_seen),
            "last_seen": _iso(row.last_seen),
            "active": row.active,
        }
        return before, related

    if target_type == "evidence":
        row = session.get(Evidence, target_id)
        if row is None:
            return None, None
        before = {
            "source": row.source,
            "source_type": row.source_type,
            "url": row.url,
            "title": row.title,
            "confidence_contribution": row.confidence_contribution,
        }
        return before, [{"id": row.id, "source": row.source, "url": row.url}]

    return None, None


def _existing_terminal(session: Session, target_type: str, target_id: str) -> dict[str, Any]:
    from database.models import AnalystAction

    row = (
        session.query(AnalystAction)
        .filter(
            AnalystAction.target_type == target_type,
            AnalystAction.target_id == target_id,
            AnalystAction.action != "note",
        )
        .order_by(AnalystAction.created_at.desc())
        .first()
    )
    if row is None:
        return {}
    return {
        "target_type": row.target_type,
        "target_id": row.target_id,
        "action": row.action,
        "actor_label": row.actor_label,
        "created_at": row.created_at,
    }


def record_analyst_action(
    session_factory: sessionmaker[Session],
    *,
    action: str,
    target_type: str,
    target_id: str,
    reason: Optional[str] = None,
    actor: str = ACTOR_CLI,
) -> dict[str, Any]:
    """Record one operator decision under the COM-002 contract. Returns a
    small result dict on success; raises DuplicateTerminalDecision on a
    collision (rejection — the caller must surface it distinctly, never
    report success) and UnknownActionError for out-of-vocabulary actions."""
    action_n = (action or "").strip().lower()
    if action_n not in KNOWN_ACTIONS:
        raise UnknownActionError(
            f"unknown action {action!r}; known actions: "
            f"{', '.join(sorted(KNOWN_ACTIONS))}"
        )
    target_type_n = (target_type or "").strip().lower()
    if target_type_n not in ("device", "evidence"):
        raise UnknownTargetTypeError(
            f"unknown target_type {target_type!r}; known: device, evidence"
        )
    target_id_n = (target_id or "").strip()
    if not target_id_n:
        raise ValueError("target_id must not be empty")

    from database.models import AnalystAction

    session = session_factory()
    try:
        try:
            with session.begin():
                before, related = _resolve_target_snapshot(
                    session, target_type_n, target_id_n
                )
                if before is None:
                    before = {"resolved": False, "given_id": target_id_n}
                now = _now_iso()
                action_id = str(uuid4())
                session.add(
                    AnalystAction(
                        id=action_id,
                        action=action_n,
                        target_type=target_type_n,
                        target_id=target_id_n,
                        actor_label=actor,
                        reason=reason or None,
                        before_state=before,
                        after_state={
                            "action": action_n,
                            "reason": reason or None,
                            "recorded_at": now,
                        },
                        related_evidence=related,
                        created_at=now,
                    )
                )
                session.flush()
            return {
                "id": action_id,
                "state": "recorded",
                "action": action_n,
                "target_type": target_type_n,
                "target_id": target_id_n,
                "target_resolved": before is not None
                and before.get("resolved") is not False,
            }
        except IntegrityError:
            # The partial unique index caught a second terminal decision
            # for this target. Roll back (context manager already did) and
            # resolve the collision as an explicit rejection carrying the
            # existing decision's identity.
            existing = _existing_terminal(session, target_type_n, target_id_n)
            raise DuplicateTerminalDecision(existing) from None
    finally:
        session.close()
