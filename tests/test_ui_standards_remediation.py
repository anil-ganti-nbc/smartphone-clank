"""STD-UI remediation regression coverage for smartphone-clank.

- STD-UI-COM-002: the qc-action decision contract — one authoritative
  TERMINAL decision per (target_type, target_id) (Option A partial unique
  index), explicit rejection on collision, append-only `note` channel,
  provenance snapshot populated in the same transaction, and a CLI that
  distinguishes rejection from success via a non-zero exit status.
- STD-UI-COM-009: per-run detail (status, phase-attributable counters,
  regression notes) is reachable and discoverable from /metrics.
- STD-UI-COM-010: a stated "All times UTC" convention on every surface;
  the dossier timeline names its timestamp semantic (Observed).
"""

from __future__ import annotations

import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.analyst_actions import (
    KNOWN_ACTIONS,
    NON_TERMINAL_ACTIONS,
    TERMINAL_ACTIONS,
    DuplicateTerminalDecision,
    UnknownActionError,
    record_analyst_action,
)
from dashboard.app import create_app
from database.models import AnalystAction, Device, Evidence
from database.schema_guard import init_fresh_database
from observability.metrics import CollectorRunRecord


@pytest.fixture()
def db(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'clank.db').as_posix()}"
    init_fresh_database(database_url)
    factory = sessionmaker(bind=create_engine(database_url))
    session = factory()
    yield session, factory, database_url
    session.close()


def _seed_device(db):
    session, _, _ = db
    device = Device(
        manufacturer="samsung", model_number="SM-A036", marketing_name="Galaxy A03",
        confidence=40,
    )
    session.add(device)
    session.flush()
    session.add(
        Evidence(
            device_id=device.id, source="samsung_support", source_type="support_page",
            url="https://www.samsung.com/SM-A036", title="SM-A036 support page",
        )
    )
    session.commit()
    return device


def _record(db, action, target_id="SM-A036", **kwargs):
    _, factory, _ = db
    return record_analyst_action(
        factory, action=action, target_type="device", target_id=target_id, **kwargs
    )


# ---------------------------------------------------------------- COM-002


def test_terminal_vocabulary_is_explicit():
    """Operator constraint (Option A): the terminal set is defined in code,
    not implied by `action <> 'note'` forever."""
    assert TERMINAL_ACTIONS == {"confirm", "reject", "quarantine", "promote"}
    assert NON_TERMINAL_ACTIONS == {"note"}
    assert KNOWN_ACTIONS == TERMINAL_ACTIONS | NON_TERMINAL_ACTIONS


def test_fresh_db_has_partial_unique_index(db):
    from sqlalchemy import text

    _, _, database_url = db
    with create_engine(database_url).connect() as conn:
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='index' AND name='uq_analyst_action_terminal'")
        ).fetchone()
    assert ddl is not None, "partial unique index missing on fresh database"
    assert "action <> 'note'" in ddl[0]


def test_terminal_decision_records_provenance_snapshot(db):
    session, _, _ = db
    device = _seed_device(db)
    result = _record(db, "confirm", reason="support page is live")
    assert result["state"] == "recorded"

    row = session.query(AnalystAction).filter_by(target_id="SM-A036").one()
    assert row.action == "confirm"
    before = row.before_state
    assert before["model_number"] == "SM-A036"
    assert before["manufacturer"] == "samsung"
    assert before["last_seen"]
    assert row.related_evidence and row.related_evidence[0]["url"] == (
        "https://www.samsung.com/SM-A036"
    )
    assert row.after_state["action"] == "confirm"
    assert row.after_state["recorded_at"]
    assert row.actor_label == "operator-cli"
    assert row.reason == "support page is live"  # resolved via model_number lookup


def test_duplicate_terminal_decision_is_rejected_not_duplicated(db):
    _record(db, "confirm")
    with pytest.raises(DuplicateTerminalDecision) as excinfo:
        _record(db, "confirm")
    assert excinfo.value.existing["action"] == "confirm"
    session, _, _ = db
    rows = session.query(AnalystAction).filter_by(target_id="SM-A036").all()
    assert len(rows) == 1, "collision must not write a second row"


def test_conflicting_terminal_decision_is_rejected_option_a(db):
    """One authoritative terminal decision per target: confirm then reject is
    a collision, not two coexisting truths."""
    _record(db, "confirm")
    with pytest.raises(DuplicateTerminalDecision):
        _record(db, "reject")
    session, _, _ = db
    terminal = session.query(AnalystAction).filter(
        AnalystAction.target_id == "SM-A036", AnalystAction.action != "note"
    ).all()
    assert [r.action for r in terminal] == ["confirm"]


def test_note_channel_remains_append_only(db):
    _record(db, "confirm")
    _record(db, "note", reason="watching this one")
    _record(db, "note", reason="second annotation")
    session, _, _ = db
    notes = session.query(AnalystAction).filter_by(
        target_id="SM-A036", action="note"
    ).all()
    assert len(notes) == 2
    assert notes[0].reason != notes[1].reason


def test_unknown_action_fails_closed_before_any_write(db):
    with pytest.raises(UnknownActionError):
        _record(db, "suspend")
    session, _, _ = db
    assert session.query(AnalystAction).count() == 0


def test_unresolved_target_recorded_honestly(db):
    result = _record(db, "note", target_id="no-such-thing")
    assert result["target_resolved"] is False
    session, _, _ = db
    row = session.query(AnalystAction).one()
    assert row.before_state == {"resolved": False, "given_id": "no-such-thing"}


def test_migration_index_predicate_matches_code_vocabulary(db):
    """A future non-terminal action requires a conscious migration change:
    the persisted index predicate is pinned to NON_TERMINAL_ACTIONS."""
    from alembic import command
    from alembic.config import Config

    session, _, database_url = db
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.set_main_option("sqlalchemy.url", database_url)

    command.downgrade(cfg, "0007_wave1_baseline_state")
    with create_engine(database_url).connect() as conn:
        from sqlalchemy import text

        gone = conn.execute(
            text("SELECT name FROM sqlite_master WHERE name='uq_analyst_action_terminal'")
        ).fetchone()
    assert gone is None, "downgrade must remove the index"

    command.upgrade(cfg, "head")
    with create_engine(database_url).connect() as conn:
        from sqlalchemy import text

        restored = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE name='uq_analyst_action_terminal'")
        ).fetchone()
    assert restored is not None
    excluded = re.findall(r"'([a-z]+)'", restored[0])
    assert set(excluded) == NON_TERMINAL_ACTIONS


def test_cli_success_and_rejection_exit_statuses(db, monkeypatch):
    """Automation (Motherclank) must be able to tell rejection from success:
    success exits 0, a duplicate/conflicting terminal write exits non-zero
    with a distinct 'rejected' message."""
    from types import SimpleNamespace

    from typer.testing import CliRunner

    import main as cli
    from database.schema_guard import init_fresh_database as _init

    session, _, database_url = db
    _seed_device(db)

    monkeypatch.setattr(
        "config.settings.load_settings",
        lambda config: SimpleNamespace(database_url=database_url),
    )
    runner = CliRunner()

    ok = runner.invoke(
        cli.app,
        ["qc-action", "--action", "confirm", "--target-type", "device",
         "--target-id", "SM-A036", "--reason", "verified live"],
    )
    assert ok.exit_code == 0, ok.output
    assert "recorded" in ok.output

    dup = runner.invoke(
        cli.app,
        ["qc-action", "--action", "reject", "--target-type", "device",
         "--target-id", "SM-A036"],
    )
    assert dup.exit_code != 0, "duplicate terminal write must not exit 0"
    assert "rejected" in dup.output

    rows = session.query(AnalystAction).filter(AnalystAction.action != "note").all()
    assert len(rows) == 1 and rows[0].action == "confirm"


# ---------------------------------------------------------------- COM-009


def _seed_run(session, collector="casio_jp", status="failed", notes=None):
    run = CollectorRunRecord(
        collector_name=collector,
        started_at=datetime.utcnow(),
        status=status,
        pages_fetched=12,
        parser_failures=2,
        http_failures=0,
        candidates_found=3,
        notes=notes,
    )
    session.add(run)
    session.commit()
    return run


def test_metrics_links_recent_runs_and_detail_shows_notes(db):
    session, _, _ = db
    run = _seed_run(session, notes="REGRESSION: candidate_collapse 3 vs median 40.0")

    client = TestClient(create_app(db[2]))
    page = client.get("/metrics")
    assert page.status_code == 200
    assert "Recent runs" in page.text
    assert f'/metrics/runs/{run.id}' in page.text

    detail = client.get(f"/metrics/runs/{run.id}")
    assert detail.status_code == 200
    assert "Phase counters" in detail.text
    assert "REGRESSION: candidate_collapse" in detail.text
    assert "Parser failures" in detail.text


def test_run_detail_404s_for_unknown_run(db):
    _, _, database_url = db
    from dashboard.app import create_app

    client = TestClient(create_app(database_url))
    assert client.get("/metrics/runs/999999").status_code == 404


# ---------------------------------------------------------------- COM-010


def test_every_surface_states_the_utc_convention(db):
    _, _, database_url = db
    from dashboard.app import create_app

    client = TestClient(create_app(database_url))
    _seed_run(sessionmaker(bind=create_engine(database_url))())
    for path in ("/", "/devices", "/metrics", "/discord"):
        page = client.get(path)
        assert page.status_code == 200, path
        assert "All times UTC" in page.text, path


def test_dossier_timeline_names_its_timestamp_semantic(db):
    _, _, database_url = db
    from dashboard.app import create_app

    session = sessionmaker(bind=create_engine(database_url))()
    device = Device(manufacturer="samsung", model_number="SM-A037")
    session.add(device)
    session.commit()

    client = TestClient(create_app(database_url))
    page = client.get("/devices/SM-A037")
    assert page.status_code == 200
    assert ">Observed<" in page.text
    assert ">When<" not in page.text
    assert "All times UTC" in page.text
