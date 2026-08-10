# Production Runtime

What actually governs schema and startup for the live Smartphone Intel Clank
process, after this phase's fixes. Companion to `docs/infra/MIGRATION_AUDIT.md`
(the "how we got here" document) — this one is "how it works now."

## Startup sequence (production)

```text
python main.py run                      (no --environment flag = production)
  -> _load_environment(config, "production")
       -> runtime.environment.assert_db_matches_environment(url, "production")
            (refuses if url looks staging-shaped)
  -> database.schema_guard.ensure_schema_or_refuse(url, context="main.py run")
       -> current_revision(url) vs head_revision(url)
       -> raises SchemaError (never mutates) if unstamped or behind
  -> IntelligencePipeline(settings, session_factory)
  -> collectors run
```

`runtime/daemon.py::main()` (the actual live scheduled process,
`python -u -m runtime.daemon`) and `runtime/run_once.py::main()` (the
prepared cloud one-shot path) follow the identical pattern — both call
`ensure_schema_or_refuse()` before doing anything else, both `return 1`
(logged, not a stack trace) if the schema is behind.

**What this means operationally**: if a future code change adds a model
without a matching migration + `db upgrade`, the daemon's *next restart*
refuses to start with a clear log line, instead of silently expanding
production's schema via whatever `Base.metadata` happens to contain in that
process. This is the direct fix for the `wave1_baseline_state` incident.

## Database commands (`python main.py db ...`)

| Command | Mutates schema? | For |
|---|---|---|
| `db current` | no | any DB — shows stamped revision vs head |
| `db history` | no | migration lineage (not DB-specific) |
| `db check` | no | non-mutating up-to-date check, exit 0/1 — safe to run before a cycle |
| `db init` | yes (only on empty DB) | brand-new database, refuses if any table already exists |
| `db adopt` | yes (only creates genuinely-missing tables, via CREATE-only DDL, never touches an existing table) | existing unstamped DB whose tables already look right |
| `db upgrade` | yes | already-stamped DB, applies pending revisions in order, backs up first |
| `db backup` | no | file copy only |

`db version` still exists (legacy `schema_version` table reader) but is
marked deprecated in its own help text — `db current` is the real answer
going forward.

## Production adoption, this session (exact before/after)

```text
Before:  alembic_version: none (never stamped)
         Samsung: 97 devices, 98 evidence, 213 confidence_ledger rows
         Missing tables (vs revision 0006's claimed DDL): analyst_actions, scheduler_jobs

db adopt --yes:
         Backed up: data/backups/clank_20260810_120022.db
         Created (empty, safe, CREATE-only): analyst_actions, scheduler_jobs
         Stamped: 0006_run_provenance

db upgrade:
         Backed up: data/backups/clank_20260810_120032.db
         Applied: 0006_run_provenance -> 0007_wave1_baseline_state
         (creates wave1_baseline_state — the table that had leaked in
         earlier via create_all(); this run made it a properly migrated,
         intentional, empty table instead)

After:   alembic_version: 0007_wave1_baseline_state (== head)
         Samsung: 97 devices, 98 evidence, 213 confidence_ledger rows — UNCHANGED
         integrity_check: ok
```

Staging (`data/clank-staging.db`) went through the identical adopt→upgrade
sequence; its pre-existing Wave 1 baseline data (Google/OnePlus/Nothing,
`run_count=3` each) was preserved throughout (`CREATE TABLE IF NOT EXISTS`
never touches a table that already has rows).

## Known gap: `db init` on a genuinely empty database

Alembic's own migration chain (0001-0007) cannot yet build a complete schema
from nothing — confirmed by trying it this session (`0006`'s
`ALTER TABLE collector_runs ADD COLUMN` fails outright because no migration
ever creates `collector_runs`; 9 other tables have the same gap). `db init`
and `reset-staging` work around this today via
`database/schema_guard.py::init_fresh_database()`: `Base.metadata.create_all()`
on the (confirmed) empty database, then stamp at head. This is safe — there
is no existing data for `create_all()` to silently mutate, which is the
entire risk this document's rules exist to prevent — but it means "a fresh
`db init` reproduces the schema through Alembic DDL alone" is **not yet
true**, and is flagged as follow-up work in `MIGRATION_AUDIT.md`.

## What still calls `create_all()` / `init_db()`

Deliberately, not by oversight:
- `database/session.py::init_db()` itself — still exists, still uses
  `create_all()`. Used by: staging's `main.py run --environment staging`/`init`
  (convenience, explicitly allowed for staging per this phase's own rules),
  and every test fixture that needs an isolated in-memory/temp database
  (tests are not "normal runtime" and were never in scope for this rule).
- `database/migrate.py::upgrade()`/`ensure_v03()` — kept as legacy/reference
  code (not deleted — "don't delete working migration logic without
  understanding lineage"), but no longer reachable from any CLI command.
  `main.py db upgrade` now calls `database.schema_guard.upgrade_to_head()`
  (real Alembic) instead.
- `main.py:report`'s own `Base.metadata.create_all(bind=eng)` (used to
  ensure metrics tables exist before reading them) — **not changed this
  session** (out of scope: this phase covered the actual schema-authority
  entry points listed above; `report` is a read path that happens to
  defensively ensure its own tables exist, lower risk than the write paths
  fixed here, flagged for the same follow-up that closes the `db init` gap).
