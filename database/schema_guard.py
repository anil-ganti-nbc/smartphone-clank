"""
Alembic-backed schema authority.

The rule: schema changes happen only through explicit migrations. Normal
application startup checks the revision and refuses to proceed if the
database is behind — it never silently mutates schema via
`Base.metadata.create_all()`. That call still exists in this codebase
(`database/session.py::init_db()`, `database/migrate.py::upgrade()`) for
legacy/test/staging-convenience use, but production runtime entry points
(`main.py run`/`init` in production mode, `runtime/daemon.py`) must go
through this module instead — see `docs/infra/MIGRATION_AUDIT.md`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = ROOT / "alembic.ini"


class SchemaError(RuntimeError):
    pass


def _config(database_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _engine(database_url: str):
    return create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
    )


def head_revision(database_url: str = "") -> str:
    cfg = _config(database_url or "sqlite:///:memory:")
    script = ScriptDirectory.from_config(cfg)
    return script.get_current_head()


def current_revision(database_url: str) -> Optional[str]:
    engine = _engine(database_url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        return ctx.get_current_revision()


def is_up_to_date(database_url: str) -> bool:
    return current_revision(database_url) == head_revision(database_url)


def init_fresh_database(database_url: str) -> str:
    """
    For a genuinely empty database only. Alembic's own migration chain
    (0001-0007) is not yet sufficient to build a complete schema from base —
    10 tables (`device_families`, `historical_stats`, `collector_runs`,
    `collector_run_metrics`, `metrics_baselines`, `rolling_stats`,
    `sitemap_product_urls`, `sitemap_traversal_state`, `sources`, `alerts`)
    have no migration history at all, and 0006's `ALTER TABLE collector_runs
    ADD COLUMN ...` outright fails on a DB that never had `collector_runs`
    created by any migration. See docs/infra/MIGRATION_AUDIT.md for the full
    accounting and the plan to close this gap with a follow-up baseline
    migration. Until then: `create_all()` is safe here specifically *because*
    the database is empty (there is no existing data `create_all()` could
    silently mutate — the exact risk this whole module exists to prevent is
    about *existing* schema, not an empty file), producing the complete
    current model shape in one step, then the result is stamped at head
    (a true statement: a fresh create_all() is always a superset of what
    head's migrations claim to produce)."""
    from database.models import Base
    import database.models_v03  # noqa: F401 registers v03 tables on Base.metadata
    from entity_resolution.confidence_ledger import ConfidenceLedgerEntry  # noqa: F401
    from observability.metrics import CollectorRunRecord, MetricsBaseline, RollingStat  # noqa: F401

    engine = _engine(database_url)
    existing = inspect(engine).get_table_names()
    if existing:
        raise SchemaError(
            f"init_fresh_database refuses: {database_url!r} already has {len(existing)} table(s). "
            "This path is for genuinely new databases only — use db_adopt/upgrade_to_head for an existing one."
        )
    Base.metadata.create_all(bind=engine)
    stamp(database_url, head_revision(database_url))
    return current_revision(database_url)


def upgrade_to_head(database_url: str) -> str:
    """Applies every pending revision in order via Alembic. Raises on failure
    rather than leaving a partial state stamped as successful — Alembic's own
    transactional-DDL-per-revision behavior (see alembic/env.py) already
    ensures a failed revision does not advance `alembic_version`."""
    from alembic import command
    cfg = _config(database_url)
    command.upgrade(cfg, "head")
    return current_revision(database_url)


def stamp(database_url: str, revision: str) -> None:
    """Declares the DB is already at `revision` WITHOUT running any DDL.
    Only ever call this after verify_schema_shape() has confirmed the actual
    table shape matches — see db_adopt() below, the only sanctioned caller."""
    from alembic import command
    cfg = _config(database_url)
    command.stamp(cfg, revision)


@dataclass
class ShapeCheckResult:
    revision: str
    tables_expected: list[str]
    tables_present: list[str] = field(default_factory=list)
    tables_missing: list[str] = field(default_factory=list)

    @property
    def matches(self) -> bool:
        return not self.tables_missing


_CREATE_TABLE_RE = re.compile(r"CREATE TABLE(?: IF NOT EXISTS)?\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)


def _tables_created_through(revision: str) -> list[str]:
    """Introspects alembic/versions/*.py source for CREATE TABLE statements
    up to and including `revision`, walking down_revision links from head.
    Source-level introspection (not execution) — safe to run against any DB,
    including one that doesn't exist yet."""
    cfg = _config("sqlite:///:memory:")
    script = ScriptDirectory.from_config(cfg)
    tables: set[str] = set()
    for rev in script.walk_revisions(base="base", head=revision):
        src = Path(rev.path).read_text(encoding="utf-8")
        tables.update(m.group(1).lower() for m in _CREATE_TABLE_RE.finditer(src))
    return sorted(tables)


_OP_EXECUTE_BLOCK_RE = re.compile(
    r'op\.execute\(\s*(?:"""(.*?)"""|f?"([^"]*)"|f?\'([^\']*)\')\s*\)', re.IGNORECASE | re.DOTALL
)


def _create_statements_through(revision: str) -> dict[str, str]:
    """table_name -> the exact CREATE TABLE statement text for it, scanning
    only op.execute() blocks that do NOT also contain a DROP — i.e. never
    extracts a statement from a drop-then-recreate migration block. This is
    the safety property db_adopt() depends on: it will create a genuinely
    missing table using known-safe DDL, but will never execute anything that
    could destroy existing data in a table that already exists."""
    cfg = _config("sqlite:///:memory:")
    script = ScriptDirectory.from_config(cfg)
    out: dict[str, str] = {}
    for rev in script.walk_revisions(base="base", head=revision):
        src = Path(rev.path).read_text(encoding="utf-8")
        for m in _OP_EXECUTE_BLOCK_RE.finditer(src):
            block = next(g for g in m.groups() if g is not None)
            if "DROP" in block.upper():
                continue
            tm = _CREATE_TABLE_RE.search(block)
            if tm:
                out[tm.group(1).lower()] = block.strip()
    return out


def create_missing_tables_safely(database_url: str, revision: str) -> list[str]:
    """For any table `revision`'s history claims to create that is genuinely
    absent from the target DB, create it using the exact CREATE-only DDL
    extracted above. Never touches a table that already exists. Returns the
    list of tables actually created."""
    shape = verify_schema_shape(database_url, revision)
    statements = _create_statements_through(revision)
    engine = _engine(database_url)
    created = []
    with engine.begin() as conn:
        for table in shape.tables_missing:
            stmt = statements.get(table)
            if not stmt:
                continue  # only in a drop+recreate block — refuse to guess, leave missing
            conn.execute(text(stmt))
            created.append(table)
    return created


def verify_schema_shape(database_url: str, revision: str) -> ShapeCheckResult:
    """Does the DB already have every table that `revision`'s migration
    history claims to create? Used by `db adopt` to decide whether stamping
    is safe. Does NOT check column-level shape (a known, documented
    limitation — see docs/infra/MIGRATION_AUDIT.md) and does NOT check tables
    outside Alembic's own history (the 10 create_all-only tables and 3
    raw-SQL-only tables documented there) — a genuinely complete check is
    follow-up work, not something to fake confidence about here."""
    expected = _tables_created_through(revision)
    engine = _engine(database_url)
    present = set(inspect(engine).get_table_names())
    missing = [t for t in expected if t not in present]
    return ShapeCheckResult(revision=revision, tables_expected=expected,
                             tables_present=sorted(present), tables_missing=missing)


def ensure_tables_present_or_refuse(database_url: str, table_names: list[str], *, context: str) -> None:
    """For read-path commands (e.g. `main.py report`, the dashboard) that
    depend on specific tables but must never create or alter schema
    themselves. Raises SchemaError naming exactly what's missing and how to
    fix it; never calls create_all() or any DDL."""
    engine = _engine(database_url)
    present = set(inspect(engine).get_table_names())
    missing = [t for t in table_names if t not in present]
    if missing:
        raise SchemaError(
            f"Missing table(s) {missing} required for {context} at {database_url!r}. "
            "Run: python main.py db upgrade  (existing database behind head)  or  "
            "python main.py db adopt  (existing database never stamped)."
        )


def ensure_schema_or_refuse(database_url: str, *, context: str = "startup") -> None:
    """The production runtime entry point. Raises SchemaError (never mutates
    schema) if the DB doesn't exist yet or is behind head."""
    engine = _engine(database_url)
    with engine.connect():
        pass  # will raise OperationalError if the sqlite file truly can't be opened at all
    current = current_revision(database_url)
    head = head_revision(database_url)
    if current is None:
        raise SchemaError(
            f"Database at {database_url!r} has no Alembic revision stamped ({context}). "
            "Run: python main.py db init  (new database)  or  python main.py db adopt  "
            "(existing database with tables already present)."
        )
    if current != head:
        raise SchemaError(
            f"Database schema is behind application version ({context}): "
            f"current={current!r}, expected={head!r}.\n"
            "Run: python main.py db upgrade"
        )
