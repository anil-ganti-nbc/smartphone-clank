# Migration Audit

Date: 2026-08-10. Full inventory of every schema-creation mechanism in this
codebase, and exactly how `wave1_baseline_state` was able to leak into
production. Written before touching production schema.

## Three competing mechanisms, confirmed

### 1. `Base.metadata.create_all()` (SQLAlchemy, implicit, environment-agnostic)

Occurrences in non-test/non-demo code:

| Call site | Invoked by | Risk |
|---|---|---|
| `database/session.py::init_db()` | `main.py` (11 call sites: `init`, `run`, `status`, `timeline`, `inspect`, `decay`, `stats`, `snapshots`, `family`, `test_alert`, others) **and `runtime/daemon.py:74`, `runtime/run_once.py:125`** | **Highest** — this runs on every single production runtime startup, including the live scheduled daemon, on every restart cycle |
| `database/migrate.py::upgrade()` (called `ensure_v03()`) | `main.py db upgrade` | **Confirmed mechanism for the `wave1_baseline_state` leak** — see below |
| `main.py:979` (inside `report` command) | `main.py report daily`, scheduled daily via `SmartphoneIntelClank-DailyReport` | Medium — runs daily against production |

**Root cause of the `wave1_baseline_state` leak, now confirmed (not just theorized):**
`database/migrate.py` imports `from database.models_v03 import SchemaVersion,
RegionalSighting, DeviceRelationship, SourceHealth, RejectedCandidate` at
module level. Adding `SourceBaselineState` to `database/models_v03.py` during
Wave 1 integration meant that module now also registers `wave1_baseline_state`
on the same shared `Base.metadata`. The next time `main.py db upgrade` (or
any other call site that imports `database.migrate` and then calls
`Base.metadata.create_all()`) ran against `sqlite:///./data/clank.db`, it
created `wave1_baseline_state` there too — table-shape only, zero rows,
because nothing in production code ever queries or writes that table. This
is not "a stray external process leaking schema" — it's this project's own
documented `db upgrade` operational command, whose actual implementation is
`create_all()`, exactly the anti-pattern this phase exists to eliminate.
(An earlier report from the previous session speculated the culprit was an
independent scheduled process sharing the working tree; that speculation is
superseded by this finding. The independent-process risk is still real —
see §"Why this still matters even with the mechanism identified" below — but
it was not the proven mechanism for this specific incident.)

### 2. `database/migrations_ordered.py` (custom, raw SQL, versioned)

Ordered revision functions `migrate_021`, `migrate_030`, `migrate_031`,
tracked via its own `schema_version` table reads (`current_version()`),
applied via `upgrade(url, target=None)`. Creates 16 tables via raw
`CREATE TABLE IF NOT EXISTS` SQL: `aliases`, `confidence_ledger`,
`device_relationships`, `devices`, `discovered_urls`, `discovery_runs`,
`download_assets`, `evidence`, `maintenance_alerts`, `page_monitors`,
`regional_sightings`, `rejected_candidates`, `schema_version`, `snapshots`,
`source_health`, `timeline_events`.

Never used by the CLI's `db upgrade` command — only ever invoked directly
(this session ran it once, manually, against `data/clank-staging.db`, to
give the fresh staging DB the tables Wave 1 integration needed). Production
was never run through this path this session.

### 3. Alembic (`alembic/versions/0001`-`0006`)

Explicit raw-SQL DDL per revision (confirmed by reading the files — genuinely
`op.execute("CREATE TABLE IF NOT EXISTS ...")`, not `create_all()` — this
part of the existing design is already correct). Creates 11 tables across the
6 revisions: `analyst_actions`, `confidence_ledger`, `devices`,
`discovered_urls`, `evidence`, `maintenance_alerts`, `regional_sightings`,
`scheduler_jobs`, `schema_version`, `source_health`, `webhook_deliveries`.

**Production has never been stamped** — `alembic_version` table does not
exist in `data/clank.db`. `alembic current` returns nothing. Staging is the
same (no `alembic_version` table in `data/clank-staging.db` either).

## Full table inventory (production, 28 tables as of this audit)

| Table | In Alembic 0001-0006? | In migrations_ordered.py? | ORM model exists (create_all-reachable)? |
|---|---|---|---|
| devices | yes | yes | yes |
| evidence | yes | yes | yes |
| confidence_ledger | yes | yes | yes |
| regional_sightings | yes | yes | yes |
| source_health | yes | yes | yes |
| webhook_deliveries | yes | no | yes |
| discovered_urls | yes | yes | **no ORM model — raw SQL only** |
| maintenance_alerts | yes | yes | **no ORM model — raw SQL only** |
| schema_version | yes | yes | yes |
| analyst_actions | yes | no | not checked this session (out of scope, no Wave 1 dependency) |
| scheduler_jobs | yes | no | not checked this session |
| aliases | no | yes | yes |
| device_relationships | no | yes | yes |
| download_assets | no | yes | yes |
| page_monitors | no | yes | yes |
| snapshots | no | yes | yes |
| timeline_events | no | yes | yes |
| rejected_candidates | no | yes | yes |
| discovery_runs | no | no | **no ORM model — raw SQL only, origin not identified this session** |
| device_families | no | no | yes (create_all only) |
| historical_stats | no | no | yes (create_all only) |
| collector_runs | no | no | yes (create_all only) |
| collector_run_metrics | no | no | yes (create_all only) |
| metrics_baselines | no | no | yes (create_all only) |
| rolling_stats | no | no | yes (create_all only) |
| sitemap_product_urls | no | no | yes (create_all only, Samsung-specific) |
| sitemap_traversal_state | no | no | yes (create_all only, Samsung-specific) |
| sources | no | no | yes (create_all only) |
| alerts | no | no | yes (create_all only) |

**9 tables exist only because some `create_all()` call created them at some
point in this project's history** (`device_families`, `historical_stats`,
`collector_runs`, `collector_run_metrics`, `metrics_baselines`,
`rolling_stats`, `sitemap_product_urls`, `sitemap_traversal_state`,
`sources`, `alerts` — 10, not 9, correcting count). None of these have any
migration-authored history at all in either Alembic or the custom ordered
runner. This is the real, structural version of the problem Wave 1 exposed
at small scale: **this production database's actual schema has never been
fully reproducible from any single migration history.** `create_all()` has
been the silent safety net papering over that gap since early in the
project, not something Wave 1 introduced — Wave 1 just made a normally
invisible gap visible by adding one new table during active development.

## Why this still matters even with the mechanism identified

Even though this specific incident traces to `main.py db upgrade` (a real
command someone/something ran, not a phantom process), the underlying risk
the mission describes is still completely real and still present:
- `init_db()`/`create_all()` runs on **every** production daemon startup
  (`runtime/daemon.py:74`) — if a *shared* model (`database/models.py`, not
  just `models_v03.py`) gains a new field or table while the live daemon's
  tree is being actively edited, the daemon's next restart applies it
  immediately, with no review step.
- Two daemon process groups were found running concurrently against
  production during this audit (see `PRE_SPLIT_PRODUCTION_SNAPSHOT.md` §5) —
  both importing from, and executing, the same live-edited tree.
- `main.py db upgrade`'s only safety net today is a file backup before
  `create_all()` — it does not check whether the resulting schema change was
  *intended*, does not require a migration file to exist, and cannot be
  distinguished from "someone fat-fingered a command against production" in
  its own logs.

## Recommended consolidation strategy (not applied this session — see §"What was actually changed")

Per the mission's own preferred approach (§35-36): **Alembic becomes the
sole authority going forward.** Concretely:
1. A new migration (`0007_wave1_baseline_state.py`) adds `wave1_baseline_state`
   properly, so it stops being "the accidentally-created table" and becomes
   "the deliberately migrated table" (spec's decision A: universal schema,
   harmless-if-empty).
2. `main.py db upgrade` is repointed to call Alembic (`alembic upgrade head`)
   instead of `database.migrate.upgrade()`. `database/migrate.py::upgrade()`/`ensure_v03()`
   remain in the codebase as legacy/reference only — not deleted (the
   mission explicitly says not to delete working migration logic without
   understanding lineage), but no longer reachable from any CLI command or
   production code path.
3. A new `db adopt` command safely stamps a DB that already has the right
   shape without re-running DDL — see `docs/infra/PRODUCTION_RUNTIME.md`.
4. Production and staging `main.py db upgrade`/`db adopt` were **run this
   session, deliberately, with the checks below** — see §"What was actually
   changed."
5. **Not done this session** (flagged, not solved): writing an Alembic
   migration that retroactively captures the 10 create_all-only tables'
   exact shape, and the 3 raw-SQL-only tables' origin story. These tables
   already exist correctly in production and staging; the gap is
   historical/documentary for *those two DBs*, but it is an **active,
   reproducible bug for a genuinely fresh database**: migration 0006 does
   `ALTER TABLE collector_runs ADD COLUMN ...`, and no migration (0001-0007)
   ever creates `collector_runs` — running Alembic 0001→0007 against an empty
   database fails outright (`OperationalError: no such table: collector_runs`),
   confirmed by actually trying it this session. `database/schema_guard.py::init_fresh_database()`
   works around this *for now* by using `Base.metadata.create_all()` — safe
   specifically because the target database is empty (no existing data to
   silently mutate, which is the actual risk this whole document is about) —
   then stamping the result at head, rather than replaying DDL. `db init` and
   `reset-staging` both go through this path; `db upgrade`/`db adopt` (for a
   database that already has data) still go through real Alembic DDL only.
   Recommended follow-up, not done this session: a `0008_baseline_remaining_tables.py`
   that creates all 10 (and captures the 3 raw-SQL-only tables' origin) so
   `init_fresh_database()` can be retired in favor of pure Alembic replay.

## What was actually changed this session

- `alembic/versions/0007_wave1_baseline_state.py` added.
- `database/schema_guard.py` added — `current_revision()`, `head_revision()`,
  `is_up_to_date()`, `upgrade_to_head()`, `verify_schema_shape()` (the "does
  this DB already have the tables a given revision claims to create" check
  used by `db adopt`).
- `main.py db` command group extended: `db current`, `db history`, `db check`,
  `db init`, `db adopt`, alongside the existing `db version` (kept,
  deprecated in favor of `db current`), `db upgrade` (repointed to Alembic),
  `db backup` (unchanged).
- `main.py run`/`main.py init` (production path only — staging unaffected)
  and `runtime/daemon.py` no longer call `init_db()` unconditionally; they
  call a new `ensure_schema_or_refuse()` that checks the Alembic revision and
  refuses to start with a clear message if the schema is behind, rather than
  silently mutating it.
- Production (`data/clank.db`) and staging (`data/clank-staging.db`) were
  both adopted (stamped to 0006, verified schema shape first) and then
  upgraded to 0007 — see `docs/infra/PRODUCTION_RUNTIME.md` for the exact
  before/after.
