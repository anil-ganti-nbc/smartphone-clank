# Pre-Split Production Snapshot

Captured: 2026-08-10, before any physical production/development tree split.
All facts below are from live inspection of the actual running system, not
assumptions.

## 1. Production database

```text
Path:              data/clank.db (relative to C:\Users\anil\Desktop\smartphone-clank)
Integrity check:    ok
Devices:            97, 100% samsung, 0 non-samsung
Evidence rows:       98
Confidence ledger:   213
Collector runs:      121
Sitemap coverage:    126/126 eligible URLs attempted, cycles_completed=74 (climbing live)
SHA-256:             07340f4e3ee83b8f860950f6ed84df8d4969fe83cb0b9454925e1d89cd9b988c
                     (NOT expected to stay constant — see §5, the live scheduler
                     is actively writing during this investigation)
```

Backup taken this session: `data/backups/clank_pre_wave1_integration_20260810_144540.db`
(from the prior phase; still the most recent full-file backup at time of writing).

## 2. Application / schema version

```text
database/migrate.py (custom):    current_version() = None (schema_version table
                                  either missing or its rows don't match the
                                  format this function expects)
database.migrations_ordered.py:  current_version() = None
Alembic:                          `alembic current` returns nothing —
                                  alembic_version table does not exist in
                                  production. Production has never been
                                  stamped by Alembic despite having a schema
                                  that substantially matches migrations
                                  0001-0006's cumulative DDL.
```

See `docs/infra/MIGRATION_AUDIT.md` for the full three-way schema-mechanism
analysis.

## 3. Application commit

```text
git log -1 --oneline: ddfc2a3 "Add Wave 1 candidate OEM collectors (Google,
                        OnePlus, Nothing, Xiaomi) behind a hard-isolated
                        staging environment"
git status:            multiple modified/untracked files present (active
                        development in progress in this same tree — this is
                        the exact condition this phase exists to fix)
```

## 4. Scheduled tasks referencing this project (Windows Task Scheduler)

Discovered via `Get-ScheduledTask`. **Only the four `SmartphoneIntelClank-*`
tasks below are in scope for this project** — `FeaturePhoneClank HMD Soak`,
`OEM Radar Hourly Crawl`, `OEM Radar Quote Test3/4`, `Smartwatch Clank -
Samsung Production Soak`, and `WatchClank-CasioJapan` are **other, unrelated
projects on this machine** and must not be touched.

| Task | State | Last run | Last result | Action |
|---|---|---|---|---|
| SmartphoneIntelClank-DailyBackup | Ready | 08/10 03:00:01 | 0 (success) | `powershell.exe -File "...\smartphone-clank\scripts\windows\backup-database.ps1"`, WorkDir=`...\smartphone-clank` |
| SmartphoneIntelClank-DailyReport | Ready | 08/10 06:00:01 | 0 (success) | `...\generate-daily-report.ps1`, same WorkDir |
| SmartphoneIntelClank-HealthCheck | **Running** | 08/10 17:15:01 | `2147946720` (0x800702E4 = ERROR_ELEVATION_REQUIRED) | `...\health-check.ps1`, runs every 15 min, same WorkDir |
| SmartphoneIntelClank-WeeklyReport | Ready | 08/09 12:56:07 | 0 (success) | `...\generate-weekly-report.ps1`, same WorkDir |

**All four reference `C:\Users\anil\Desktop\smartphone-clank` — the exact
tree under active development.** This is the core problem this phase exists
to fix.

**Pre-existing issue found, not caused by this phase**: `SmartphoneIntelClank-HealthCheck`'s
last run returned `ERROR_ELEVATION_REQUIRED`. Not investigated further this
session (out of scope — infra isolation, not a general bugfix pass) but
flagged for the operator.

## 5. Live processes

```text
PID 38132/4476    python -u -m runtime.daemon   started 2026-08-10 02:15:04
PID 35384/22400   python -u -m runtime.daemon   started 2026-08-10 14:45:04
```

Both from `C:\Users\anil\Desktop\smartphone-clank\.venv\Scripts\python.exe`.
**Two separate daemon process groups are running concurrently against the
same production `data/clank.db`.** This predates this session's own commands
(neither was started by this session).

`runtime\pids\runtime.pid` contents:
```json
{"pid":11756,"command":"SmartphoneIntelClank","started_utc":"2026-08-02T08:00:04Z","kind":"runtime"}
```
PID 11756 is **not** among any currently-running process — the PID file is
stale relative to reality. `scripts/windows/health-check.ps1::Test-ClankProcess`
checks this file; since it points at a dead PID, health-check concludes the
runtime "is not running" and calls `start-runtime.ps1` to launch a new one —
without first confirming no other daemon instance is already alive. This is
the most likely explanation for the two concurrent daemon groups above: a
real, pre-existing PID-tracking bug in `scripts/windows/_common.ps1`/`start-runtime.ps1`,
independent of Wave 1 work, but directly relevant to "exactly one intended
production runtime should remain" (this phase's success criteria). Not fixed
in this document — flagged for the tree-split execution plan.

## 6. Other unrelated scheduled infrastructure on this machine (informational only)

```text
FeaturePhoneClank HMD Soak
OEM Radar Hourly Crawl              (Running)
OEM Radar Quote Test3
OEM Radar Quote Test4               (Running)
Smartwatch Clank - Samsung Production Soak
WatchClank-CasioJapan
```

These belong to other projects. `python.exe -m oem_radar.cli run` (PID 44184)
observed in the live process list is one of these unrelated tasks — not
Smartphone Intel Clank, not touched, not investigated further.

## 7. `.env` / secrets

Not read into this document (per policy — never print secrets). Confirmed to
exist at repo root; `config/settings.py::Settings.load()` and
`scripts/windows/_common.ps1::Import-ClankEnv` both load it. Redaction
convention (`alerts/delivery.py::redact_webhook_url`) confirmed still in
effect throughout this session's work.

## 8. What this snapshot is for

This is the reference point for the physical production/development tree
split described in `docs/infra/PROD_DEV_SPLIT.md`. No directory move, no
Task Scheduler edit, and no process termination has happened yet as of this
document. Those steps require explicit operator confirmation before
execution — see `docs/infra/PROD_DEV_SPLIT.md` §"Execution status."
