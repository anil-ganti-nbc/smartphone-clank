"""
Migration authority tests (infra-hardening phase): normal runtime never
mutates schema via create_all(); only explicit migration commands do;
importing a new model does not silently expand an existing database.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, create_engine

from database.schema_guard import (
    SchemaError,
    current_revision,
    ensure_schema_or_refuse,
    head_revision,
    init_fresh_database,
    is_up_to_date,
    upgrade_to_head,
)


@pytest.fixture()
def fresh_db(tmp_path):
    return f"sqlite:///{(tmp_path / 'schema_test.db').as_posix()}"


def test_fresh_database_starts_unstamped(fresh_db):
    engine = create_engine(fresh_db)
    with engine.connect():
        pass
    assert current_revision(fresh_db) is None


def test_ensure_schema_or_refuse_raises_on_unstamped_db(fresh_db):
    engine = create_engine(fresh_db)
    with engine.connect():
        pass
    with pytest.raises(SchemaError, match="no Alembic revision stamped"):
        ensure_schema_or_refuse(fresh_db)


def test_init_fresh_database_reaches_head(fresh_db):
    rev = init_fresh_database(fresh_db)
    assert rev == head_revision(fresh_db)
    assert is_up_to_date(fresh_db)
    # normal runtime check now passes without raising
    ensure_schema_or_refuse(fresh_db)


def test_init_fresh_database_refuses_on_populated_db(fresh_db):
    init_fresh_database(fresh_db)
    with pytest.raises(SchemaError, match="already has"):
        init_fresh_database(fresh_db)


def test_old_db_refuses_normal_startup_until_upgraded(fresh_db):
    """Simulates an existing DB stamped behind head — must refuse, not
    silently create_all() the gap."""
    init_fresh_database(fresh_db)
    from database.schema_guard import stamp
    # Roll the stamp back to simulate a DB that's behind
    stamp(fresh_db, "0006_run_provenance")
    assert current_revision(fresh_db) == "0006_run_provenance"

    with pytest.raises(SchemaError, match="behind application version"):
        ensure_schema_or_refuse(fresh_db)

    # explicit upgrade fixes it
    after = upgrade_to_head(fresh_db)
    assert after == head_revision(fresh_db)
    ensure_schema_or_refuse(fresh_db)  # no longer raises


def test_importing_new_model_does_not_mutate_existing_database(fresh_db):
    """The exact regression this phase exists to prevent: a model existing in
    Python (Base.metadata) must not, by itself, cause an existing database's
    schema to change. Only an explicit migration call does that."""
    init_fresh_database(fresh_db)
    engine = create_engine(fresh_db)
    before_tables = set(inspect(engine).get_table_names())

    # Import every model module this project has — if any of them triggered
    # create_all() as an import side effect, this would already be a bug;
    # confirm it does not.
    import database.models  # noqa: F401
    import database.models_v03  # noqa: F401
    from entity_resolution.confidence_ledger import ConfidenceLedgerEntry  # noqa: F401
    from observability.metrics import CollectorRunRecord, MetricsBaseline, RollingStat  # noqa: F401

    after_tables = set(inspect(engine).get_table_names())
    assert after_tables == before_tables, (
        "importing model modules must never change an existing database's schema"
    )


def test_migration_failure_does_not_stamp_success(fresh_db, monkeypatch):
    """A failed migration must not advance alembic_version."""
    init_fresh_database(fresh_db)
    from database.schema_guard import stamp
    stamp(fresh_db, "0006_run_provenance")
    before = current_revision(fresh_db)

    def _boom(cfg, target):
        raise RuntimeError("simulated migration failure")

    import alembic.command
    monkeypatch.setattr(alembic.command, "upgrade", _boom)

    with pytest.raises(RuntimeError):
        upgrade_to_head(fresh_db)

    assert current_revision(fresh_db) == before, "a failed migration must not change the stamped revision"


def test_reset_staging_produces_full_schema_at_head(tmp_path):
    """spec: staging reset must migrate to HEAD, not raw create_all-and-hope."""
    db_path = tmp_path / "clank-staging-reset.db"
    url = f"sqlite:///{db_path.as_posix()}"
    rev = init_fresh_database(url)
    assert rev == head_revision(url)
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert "wave1_baseline_state" in tables
    assert "devices" in tables


def test_ensure_tables_present_or_refuse_passes_when_present(fresh_db):
    from database.schema_guard import ensure_tables_present_or_refuse
    init_fresh_database(fresh_db)
    ensure_tables_present_or_refuse(fresh_db, ["devices", "evidence"], context="test")


def test_ensure_tables_present_or_refuse_raises_without_creating(fresh_db):
    """The exact property the report/dashboard/sitemap-collector fix depends
    on: a read path with missing tables must raise, and must not have
    created anything as a side effect of checking."""
    from database.schema_guard import ensure_tables_present_or_refuse
    init_fresh_database(fresh_db)
    engine = create_engine(fresh_db)
    before = set(inspect(engine).get_table_names())
    assert "collector_run_metrics" in before  # sanity: init_fresh_database already made it

    # Simulate a table this DB genuinely lacks (never created here).
    with pytest.raises(SchemaError, match=r"Missing table\(s\)"):
        ensure_tables_present_or_refuse(fresh_db, ["not_a_real_table"], context="test")

    after = set(inspect(engine).get_table_names())
    assert after == before, "checking for a missing table must never create it"


def test_report_command_refuses_on_schema_behind_db_without_mutating(fresh_db, monkeypatch):
    """spec: `main.py report` must never create/alter schema. Simulate a DB
    stamped at head but missing a metrics table (the exact shape a stale
    production DB predating a metrics migration could have) and confirm the
    report command's schema check raises rather than creating the table."""
    from database.schema_guard import ensure_tables_present_or_refuse

    init_fresh_database(fresh_db)
    engine = create_engine(fresh_db)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE collector_run_metrics")
    before = set(inspect(engine).get_table_names())
    assert "collector_run_metrics" not in before

    with pytest.raises(SchemaError, match=r"Missing table\(s\).*report"):
        ensure_tables_present_or_refuse(
            fresh_db,
            ["collector_run_metrics", "metrics_baselines", "rolling_stats"],
            context="report",
        )

    after = set(inspect(engine).get_table_names())
    assert "collector_run_metrics" not in after, "report's schema check must not silently recreate the table"


def test_dashboard_create_app_refuses_on_schema_behind_db_without_mutating(fresh_db):
    """spec: the dashboard is a real production runtime path and must never
    create/alter schema either."""
    init_fresh_database(fresh_db)
    engine = create_engine(fresh_db)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE webhook_deliveries")
    before = set(inspect(engine).get_table_names())

    from dashboard.app import create_app
    with pytest.raises(SchemaError, match=r"Missing table\(s\).*dashboard"):
        create_app(fresh_db)

    after = set(inspect(engine).get_table_names())
    assert after == before, "dashboard create_app() must not create tables when refusing"


def test_sitemap_collector_refuses_on_schema_behind_db_without_mutating(fresh_db):
    """spec: collectors' collect() must never create/alter schema either —
    this was the highest-frequency create_all() hazard (every collection
    cycle, not just daily reports)."""
    init_fresh_database(fresh_db)
    engine = create_engine(fresh_db)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE sitemap_product_urls")
    before = set(inspect(engine).get_table_names())

    from collectors.samsung.sitemap_collector import SamsungSitemapCollector
    collector = SamsungSitemapCollector(database_url=fresh_db, use_fixture_sitemap=True)
    result = collector.collect()
    assert result == []  # refuses cleanly, does not raise out of collect()

    after = set(inspect(engine).get_table_names())
    assert after == before, "collector.collect() must not create tables when its schema check fails"
