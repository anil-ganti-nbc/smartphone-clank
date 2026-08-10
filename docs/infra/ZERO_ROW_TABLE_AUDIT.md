# Zero-Row Table Audit

Code-backed audit of the 15 production tables with zero rows, identified by
`docs/wave2/POST_WAVE2_COMPLEXITY_AUDIT.md`. Per
`docs/ENGINEERING_PRINCIPLES.md` Rule 10/12 — empty is not evidence of
dead; each table below was checked for an ORM class, a migration, a
reader, and a writer before classification. **No tables are removed or
altered in this phase** — this is documentation only.

(`rejected_candidates` had zero rows at the time of the original
complexity audit but now has 545 — Wave 2 staging/canary work populated
it — so it is excluded from this list; it was never actually dead.)

## Classification table

| Table | Model class | Migration | Reader | Writer | Classification |
|---|---|---|---|---|---|
| `analyst_actions` | **none** | `0004_v032.py` (raw SQL) | none | none | **DEAD** |
| `device_relationships` | `database/models_v03.py::DeviceRelationship` | `0002_v030` (via `migrate.py`) | none in live code | `demo/samsung_lifecycle_demo.py` only | **OPTIONAL_FEATURE** |
| `discovered_urls` | **none** | `0003_v031.py` (raw SQL) | none | none | **LEGACY** |
| `discovery_runs` | **none** | `database/migrations_ordered.py` (raw SQL) | none | none | **LEGACY** |
| `download_assets` | `database/models.py::DownloadAsset` | (with `models.py`) | `collectors/support_monitor.py` (orphaned, see below) | same | **LEGACY** |
| `historical_stats` | `database/models.py::HistoricalStat` | (with `models.py`) | `main.py`'s `report` command | none anywhere | **OPTIONAL_FEATURE** |
| `maintenance_alerts` | (mapped via `alerts/maintenance.py`) | (with `models.py`) | `observability/metrics.py` | `alerts/maintenance.py` | **ACTIVE_BUT_CURRENTLY_EMPTY** |
| `page_monitors` | `database/models.py::PageMonitor` | (with `models.py`) | `collectors/support_monitor.py` (orphaned, see below) | same | **LEGACY** |
| `regional_sightings` | `database/models_v03.py::RegionalSighting` | `0002_v030` | none in live code | `demo/samsung_lifecycle_demo.py` only | **OPTIONAL_FEATURE** |
| `rolling_stats` | `observability/metrics.py::RollingStat` | (with `models.py`) | `main.py`, `database/schema_guard.py` (schema-presence checks) | `MetricsRecorder.recompute_rolling()` — implemented, **never called** from `main.py`/`runtime/daemon.py` | **OPTIONAL_FEATURE** |
| `scheduler_jobs` | **none** | `0004_v032.py` (raw SQL) | none | none | **DEAD** |
| `schema_version` | `database/models_v03.py::SchemaVersion` | `database/migrate.py` (pre-Alembic) | `database/migrate.py`, one test | `database/migrate.py` | **LEGACY + DUPLICATE_SEMANTICS_RISK** |
| `snapshots` | `database/models.py::Snapshot` | (with `models.py`) | `dashboard/app.py`, `database/snapshot_retention.py::prune_snapshots()` (called every collector run, but only prunes — nothing left to prune since nothing writes) | `collectors/support_monitor.py` (orphaned, see below) | **LEGACY** |
| `source_health` | `database/models_v03.py::SourceHealth` | `0002_v030` | none in live code | `database/migrate.py` only (one-time backfill, not ongoing) | **DEAD + DUPLICATE_SEMANTICS_RISK** |
| `sources` | `database/models.py::Source` | (with `models.py`) | none in live code | none anywhere | **DEAD** |

## The orphaned-collector finding (page_monitors, snapshots, download_assets)

`collectors/support_monitor.py::SupportPageMonitor` is a fully-implemented
collector — it fetches pages, computes content hashes, and writes both
`PageMonitor` and `Snapshot` (and, via a related path, `DownloadAsset`)
rows on real content changes. **It is never imported or registered
anywhere** — not in `collectors/__init__.py::build_collectors()`, not in
`runtime/daemon.py`, not in `main.py`. It is dead code that happens to be
fully functional, reachable only from `demo/support_diff_demo.py`.

This explains three of the fifteen tables at once: the writer exists and
works, it is simply never invoked by anything that runs. Classified
LEGACY rather than DEAD because the code is complete and could be wired in
directly if a future mission wanted full-page-diff monitoring — it isn't
a half-finished stub, it's a finished feature that was superseded by the
simpler sitemap/support-page approach the live collectors actually use.

## Duplicate-semantics risks flagged (not consolidated — Part 12)

- **`schema_version` vs Alembic's `alembic_version`** — two competing
  "what schema version is this database at" mechanisms. `alembic_version`
  is unambiguously authoritative (`database/schema_guard.py` checks it
  exclusively; see `docs/infra/MIGRATION_AUDIT.md` from the isolation-
  hardening phase). `schema_version` is a pre-Alembic relic, written only
  by `database/migrate.py`'s old upgrade path. `DUPLICATE_SEMANTICS_RISK`.
- **`source_health` vs `collector_run_metrics`/`collector_runs`** — both
  conceptually answer "is this source healthy." `collector_run_metrics`
  is unambiguously the live mechanism (every collector run writes one,
  `main.py report`/dashboard read it). `source_health` was written once
  by a migration backfill and never touched again. `DUPLICATE_SEMANTICS_RISK`.
- **`scheduler_jobs` vs APScheduler's in-memory job store** — the table
  looks like it was designed to persist job state across restarts
  (`next_run`, `last_run`, `lock_owner`, `lock_expiry` columns), but
  `runtime/daemon.py` uses `BlockingScheduler` with no persistent
  jobstore configured — job state is entirely in-memory, rebuilt fresh on
  every daemon restart from `config.yaml`. No live code ever reads or
  writes this table. `DUPLICATE_SEMANTICS_RISK` (in intent, not in current
  competing writes — there's only one active mechanism, APScheduler's
  in-memory state).

## Part 13 — removal candidates

**Do not remove anything this phase.** Classification only.

| Table | Recommendation |
|---|---|
| `analyst_actions` | `NEEDS_DECISION` — either build the analyst-action-logging feature it implies, or mark for removal in a dedicated cleanup migration |
| `device_relationships` | `KEEP` — demo-proven, plausible future use (successor/variant device links) |
| `discovered_urls` | `SAFE_TO_REMOVE_LATER` — superseded design, zero code references outside its own migration |
| `discovery_runs` | `SAFE_TO_REMOVE_LATER` — same as above |
| `download_assets` | `NEEDS_DECISION` — tied to `support_monitor.py`'s fate (see below) |
| `historical_stats` | `NEEDS_DECISION` — `main.py report` actively queries it; either build the writer or remove the read path too |
| `maintenance_alerts` | `KEEP` — real, active feature; empty because no maintenance-eligible event has fired yet, not because it's unused |
| `page_monitors` | `NEEDS_DECISION` — tied to `support_monitor.py`'s fate |
| `regional_sightings` | `KEEP` — demo-proven, plausible future use |
| `rolling_stats` | `NEEDS_DECISION` — wire `recompute_rolling()` into a scheduled job, or remove |
| `scheduler_jobs` | `SAFE_TO_REMOVE_LATER` — zero Python mapping exists at all |
| `schema_version` | `SAFE_TO_REMOVE_LATER` — fully superseded by `alembic_version`; keep only if any old-format DB still needs upgrading through `migrate.py` |
| `snapshots` | `NEEDS_DECISION` — tied to `support_monitor.py`'s fate |
| `source_health` | `SAFE_TO_REMOVE_LATER` — fully superseded by `collector_run_metrics` |
| `sources` | `SAFE_TO_REMOVE_LATER` — zero writers anywhere, zero readers anywhere |

**`support_monitor.py`'s fate is the one decision that resolves three
tables at once** (`page_monitors`, `snapshots`, `download_assets`): either
wire it into `build_collectors()` as a real production monitoring source,
or formally retire it (move to `deprecated/`, per
`docs/ENGINEERING_PRINCIPLES.md` Rule 10) and drop its three tables in a
future migration. Not decided this phase — flagged for a dedicated
follow-up.
