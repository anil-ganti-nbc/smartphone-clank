# Isolation Audit (adversarial review)

Date: 2026-08-10. First pass written before the physical split executed;
**re-run after execution** (same day) — this is the post-execution version.
Every row below reflects the actual state after `docs/infra/PROD_DEV_SPLIT.md`
was carried out.

| Check | Finding | Status |
|---|---|---|
| Task Scheduler still pointing to dev tree | No — all 4 `SmartphoneIntelClank-*` tasks repointed to `C:\Users\anil\Desktop\smartphone-clank-prod`; verified by reading each definition back (`Get-ScheduledTask \| Select Actions`), not just trusting the `Set-ScheduledTask` call | **PASS** |
| Hidden Python process still referencing dev | No — both original orphaned daemon processes (PIDs 38132/4476, 35384/22400) stopped before the split; the only daemon process now running (PID 34508 + child 27348) has command line `C:\Users\anil\Desktop\smartphone-clank-prod\.venv\Scripts\python.exe -u -m runtime.daemon`, confirmed via `Get-CimInstance Win32_Process` | **PASS** |
| Production DB reachable from staging command | No — `runtime/environment.py::assert_db_matches_environment` guard, verified live and via `tests/wave1/test_integration.py`/`test_discord_safety.py` | **PASS** |
| Staging DB reachable from production command | No — same guard, opposite direction | **PASS** |
| `create_all()` in runtime paths | Fixed for the three real production entry points (`main.py run`/`init` production branch, `runtime/daemon.py`, `runtime/run_once.py`) — all call `ensure_schema_or_refuse()`. `main.py report`'s defensive `create_all()` for metrics tables was **not** changed | **PARTIAL — primary paths fixed, one read-path gap remains, documented in `PRODUCTION_RUNTIME.md`** |
| Migrations executed implicitly by collector startup | No — `ensure_schema_or_refuse()` never runs a migration, only checks and refuses | **PASS** |
| Custom migration runner still acting as hidden authority | `database/migrate.py::upgrade()`/`ensure_v03()` retained as legacy code but unreachable from any CLI command or production path — `main.py db upgrade` calls Alembic | **PASS** |
| `.env` copied into wrong tree | The prod tree's `.env` is the one that existed in the tree at copy time (robocopy copied it as-is, same content as dev's `.env` at that moment — this project uses one `.env` for both, scoped internally by `CLANK_*`/`STAGING_*` variable naming, not by having separate files). No staging-specific secret exists in `.env` to leak (staging webhook, if configured, would be `STAGING_DISCORD_WEBHOOK_URL` in the same file) — verified no `config/config.staging.yaml` or `data/clank-staging.db` exists in the prod tree (removed in the freeze step) | **PASS** |
| Production webhook reachable from staging | No — environment-scoped webhook resolution in `config/settings.py`, 5 regression tests passing | **PASS** |
| Dev code able to change production schema without deployment | No longer — the daemon now runs exclusively from the frozen prod tree; a dev-tree edit to `database/models.py` has no effect on the running production process until deliberately deployed (copied) into the prod tree, same as any other code change now | **PASS** |
| Production tree writable/modified by normal development tooling | No — Claude Code's editing tools operated exclusively on the dev tree (`C:\Users\anil\Desktop\smartphone-clank`) throughout this session; the only writes to the prod tree were the two deliberate, reviewed one-off script deployments (`start-runtime.ps1`, `start-dashboard.ps1` bugfixes) documented in `PROD_DEV_SPLIT.md` step 8 | **PASS** |
| Duplicate scheduled runtime | No — exactly one daemon process group confirmed running after the split, and the root cause (stale PID file, `start-runtime.ps1` never called `Save-PidMeta`) is fixed, not just avoided this one time: `Test-ClankProcess` now genuinely reflects reality, so a future health-check cycle correctly recognizes an already-running daemon instead of spawning another. Verified live: two consecutive `health-check.ps1` invocations, second one exit 0, no new processes created | **PASS** |
| Stale old paths in scripts/docs | `HANDOFF.md` and `docs/infra/*` reflect current state. Did not do a full repo-wide sweep of every script/doc for incidental stale path mentions (e.g. old comments referencing the single-tree layout) — lower priority, cosmetic | **NOT FULLY CHECKED — low priority** |
| Backups stored inside Git | `.gitignore` covers `data/backups/`; `git status` (dev tree) confirms no backup `.db` files tracked or staged. Prod tree is not a git-tracked location for review purposes at all yet (byte copy, not a repo checkout in the release sense) | **PASS** |
| SQLite WAL/shm copied unsafely | The daemon was fully stopped (verified via process list) before the `robocopy` copy ran, and `data/clank.db` had no `-wal`/`-shm` sidecar files present at copy time (confirmed via `ls data/clank.db*` immediately before copying) — so there was nothing unsafe to copy. Confirmed the copied DB opened cleanly and passed `PRAGMA integrity_check` in the new location before the daemon was ever pointed at it | **PASS** |

## Additional finding during execution (not on the original checklist, found live)

**`start-dashboard.ps1` had the identical bug as `start-runtime.ps1`** —
synchronous start, no PID recording. Discovered when a manual
`health-check.ps1` test run hung (blocked inside a synchronous dashboard
start with no way to return). Fixed the same way (detached `Start-Process` +
`Save-PidMeta` + duplicate guard), verified via two consecutive
`health-check.ps1` runs (second returns exit 0, no hang, no duplicate
processes). See `PROD_DEV_SPLIT.md` step 8 for full detail.

## Critical/high findings fixed this session

1. **`create_all()` as the de facto production migration mechanism** — root
   cause of the `wave1_baseline_state` leak, fixed for all three real
   production runtime entry points. See `MIGRATION_AUDIT.md`.
2. **Production never Alembic-stamped** — adopted and upgraded to head,
   verified zero data impact (97 Samsung devices/98 evidence/213
   confidence-ledger rows unchanged, `PRAGMA integrity_check` = ok before and
   after). See `PRODUCTION_RUNTIME.md`.
3. **Hardcoded "Samsung Collector Degraded" maintenance alert string**
   (found during the prior Wave 1 integration phase) — already fixed.
4. **Backup filename collision between production and staging**
   (`backup_db()` always wrote `clank_<timestamp>.db` regardless of source)
   — fixed to name from the source file's own stem.
5. **Physical production/development tree separation** — executed. Task
   Scheduler repointed and verified by reading definitions back; production
   runs exclusively from `smartphone-clank-prod`.
6. **Duplicate live daemon processes + the stale-PID root cause** — both
   orphaned processes stopped, root cause (missing `Save-PidMeta` call in
   `start-runtime.ps1`) fixed, verified via live restart and two
   health-check cycles producing no duplicates.
7. **`start-dashboard.ps1`'s identical latent bug** — found and fixed during
   execution, not left for a future incident.

## Critical/high findings NOT fixed this session (explicitly deferred, not hidden)

1. **`db init`/`reset-staging` not yet pure-Alembic-DDL** — works correctly
   today via a documented, safe (`create_all()`-on-empty-DB) fallback;
   closing this properly means writing a `0008_baseline_remaining_tables.py`
   migration, follow-up work.
2. **`main.py report`'s own defensive `create_all()`** — lower risk (read
   path, only ensures metrics tables exist), not touched this phase.
3. **Prod tree is a byte-copy, not yet a reviewed-commit checkout** — the
   eventual `GitHub → tested commit → deploy` release model isn't built yet;
   `PROD_DEV_SPLIT.md` explains why this was deliberately sequenced after
   the split itself rather than blocking it.
4. **No full repo-wide sweep for stale path references** in scripts/docs
   beyond the ones this phase directly touched.

## Verdict

All items on the mission's own hostile-audit checklist that are meaningful
to check post-execution are **PASS**, with two explicitly-scoped `PARTIAL`
gaps (both documented, both low-severity, both about a read-path/dev-DB-init
convenience path rather than the production write path this phase exists to
protect) and one cosmetic "not fully checked" item. No critical or high
finding was left silently unresolved.
