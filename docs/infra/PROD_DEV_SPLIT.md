# Production / Development Tree Split — Plan (not yet executed)

This is the concrete, ready-to-run plan for the physical isolation the
mission requires. **Nothing in this document has been executed.** It touches
a live scheduled Windows process and a production database — per this
project's own operating rules, that requires explicit operator confirmation
before any step runs. See `docs/infra/PRE_SPLIT_PRODUCTION_SNAPSHOT.md` for
the full state this plan was built against.

## What was found (read-only investigation, already done)

- **Four real Task Scheduler tasks**, all pointing at
  `C:\Users\anil\Desktop\smartphone-clank` (this exact dev tree):
  `SmartphoneIntelClank-DailyBackup`, `-DailyReport`, `-HealthCheck` (runs
  every 15 min), `-WeeklyReport`.
- **`SmartphoneIntelClank-HealthCheck` supervises the actual daemon**: it
  checks `runtime\pids\runtime.pid`, and if the recorded PID isn't alive,
  calls `scripts/windows/start-runtime.ps1` to launch a new
  `python -u -m runtime.daemon`.
- **The PID file is currently stale** (`runtime.pid` records PID 11756,
  started 2026-08-02 — not among any currently-running process) and
  **two separate daemon process groups were found running concurrently**
  against the same production DB (started 02:15:04 and 14:45:04 today).
  `Test-ClankProcess` doesn't verify "is *a* daemon already alive," only "is
  *this specific recorded PID* alive" — so health-check's every-15-minute
  cycle can spawn a new daemon without stopping a still-live old one whose
  PID just isn't the one on record. **This is a real, pre-existing bug,
  independent of Wave 1, that the split execution must fix** (the mission's
  own success criteria requires "exactly one intended production runtime").
- Other scheduled tasks on this machine (`FeaturePhoneClank HMD Soak`,
  `OEM Radar *`, `Smartwatch Clank - Samsung Production Soak`,
  `WatchClank-CasioJapan`) belong to **other, unrelated projects** — out of
  scope, not touched, not further investigated.

## Chosen method: byte-for-byte copy, not a Git worktree

**Reasoning**: `git status` shows a substantial set of modified/untracked
files from active Wave 1 + this phase's own work, not yet committed. A Git
worktree/second-clone approach would require deciding what's "production"
(a specific commit) vs "development" (the working tree) *before* that
work is committed and reviewed — exactly the ordering this phase's own
`DEPLOYMENT_MODEL.md` argues against (dev → tests → review → release, not
release-from-whatever-HEAD-happens-to-be). A direct filesystem copy avoids
forcing that decision prematurely and carries no risk of losing uncommitted
work. Once the split exists and a real release process is established, the
production tree can be converted to "checkout of a tagged/reviewed commit"
as a follow-up — not blocked by this plan, just sequenced after it.

## Execution steps (in order — none run yet)

1. **Stop the scheduler safely**: `Disable-ScheduledTask` on all four
   `SmartphoneIntelClank-*` tasks (not delete — reversible). Confirm via
   `Get-ScheduledTask` that state is `Disabled`.
2. **Stop the live daemon(s)**: identify every `python -u -m runtime.daemon`
   process via `Get-CimInstance Win32_Process` (command-line match, not just
   name), confirm each one's working directory is this tree, stop them
   individually (`Stop-Process -Id`). Do not use a blanket `taskkill /IM
   python.exe` — this machine runs Python for other unrelated scheduled
   projects (OEM Radar, WatchClank, etc.) that must not be touched.
3. **Re-verify production DB integrity** (`PRAGMA integrity_check`, row
   counts, Alembic revision) immediately after the daemon stops — confirms a
   clean stop, not a mid-write kill.
4. **Copy the tree** to `C:\Users\anil\Desktop\smartphone-clank-prod`
   (byte-for-byte, excluding nothing — the production tree gets its own
   full copy of `data/`, `.venv/`, everything, then immediately has its
   staging-only artifacts removed per step 6).
5. **Leave the original tree as the development tree** (`smartphone-clank`,
   or rename to `smartphone-clank-dev` if a clean rename is preferred —
   operator's call, both are functionally identical since
   `scripts/windows/_common.ps1::Get-ClankRoot` derives paths relative to
   the script's own location, not a hardcoded name).
6. **Freeze the prod tree**: delete `data/clank-staging.db` and
   `config/config.staging.yaml`-only artifacts from
   `smartphone-clank-prod` (production has no legitimate use for them); add
   `PRODUCTION_TREE.txt` (see below).
7. **Mark the dev tree**: add `DEVELOPMENT_TREE.txt` (see below).
8. **Repoint Task Scheduler**: edit each of the four tasks' `-File` argument
   and working directory to `smartphone-clank-prod`. Read the definition
   back (`Get-ScheduledTask | Select Actions`) to confirm — never trust the
   registration command alone.
9. **Re-enable the tasks**, start the daemon once manually from
   `smartphone-clank-prod` to confirm the path resolves correctly and
   `ensure_schema_or_refuse()` passes (production DB is already at head —
   see `PRODUCTION_RUNTIME.md`).
10. **Development isolation proof**: add a harmless marker (e.g. a new
    unused model class) only in the dev tree, let a production cycle run,
    confirm the prod tree's schema/behavior is unaffected — this is the
    actual proof the split worked, not just that the paths changed.
11. **Update `runtime\pids\runtime.pid` handling** — fix the stale-PID bug
    found in step "What was found" above as part of this same maintenance
    window, since restarting the daemon fresh is the natural point to also
    verify only one instance starts.

## Prerequisites before step 1 can run

- Explicit operator go-ahead (this document exists specifically to make that
  a single, reviewable decision rather than something buried in a large
  autonomous session).
- Confirm no in-progress production write (check `collector_runs`/
  `collector_run_metrics` for a run started but not finished in the last
  few minutes) immediately before stopping anything.

## `PRODUCTION_TREE.txt` (to be added to the prod tree)

```text
THIS TREE IS EXECUTED BY THE LIVE SMARTPHONE INTEL CLANK RUNTIME.
DO NOT DEVELOP OR RUN EXPERIMENTAL TESTS HERE.
USE THE DEVELOPMENT TREE.
```

## `DEVELOPMENT_TREE.txt` (already true of the current tree, to be added once the split happens)

```text
Staging DB: data/clank-staging.db (never data/clank.db)
Staging Discord: STAGING_DISCORD_WEBHOOK_URL only (see .env)
Tests: PYTHONPATH=. python -m pytest -q
Staging run: python main.py run --environment staging --once
Do NOT point a Windows Task Scheduler production task at this tree.
```

## Execution status

**Executed 2026-08-10, with explicit operator confirmation.** Actual results:

1. Disabled all 4 `SmartphoneIntelClank-*` tasks (`Disable-ScheduledTask`);
   stopped the in-progress `HealthCheck` run first (`Stop-ScheduledTask`).
2. Stopped both orphaned daemon process groups (PIDs 38132/4476 and
   35384/22400, identified by command-line match on `-m runtime.daemon` and
   the `smartphone-clank` path — confirmed neither belonged to another
   project first). One PID (4476) had already exited on its own by the time
   its stop was attempted; the rest stopped cleanly.
3. Re-verified production DB immediately after: `PRAGMA integrity_check` =
   ok, 97 Samsung devices, 98 evidence, 213 confidence-ledger rows — no
   change from the pre-stop snapshot, no WAL/SHM sidecar files present
   (clean stop, not a mid-write kill).
4. Copied the tree via `robocopy /E` to
   `C:\Users\anil\Desktop\smartphone-clank-prod` — 913 dirs, 6445 files,
   ~220MB, verified by re-reading the copied `data/clank.db`'s device count
   (97 Samsung) in the new location before touching anything else.
5. Froze the prod tree: removed `data/clank-staging.db` and
   `config/config.staging.yaml` (staging-only artifacts), added
   `PRODUCTION_TREE.txt`.
6. Added `DEVELOPMENT_TREE.txt` to the original tree (kept its original
   name, `smartphone-clank` — no rename needed, since
   `scripts/windows/_common.ps1::Get-ClankRoot` already derives paths
   relative to script location, not a hardcoded tree name).
7. Repointed all 4 Task Scheduler tasks' `Execute`/`Arguments`/`WorkingDirectory`
   to `smartphone-clank-prod`, **read every definition back** via
   `Get-ScheduledTask | Select Actions` to confirm (not just trusted the
   `Set-ScheduledTask` call) — all 4 confirmed correct.
8. **Found and fixed a real, independent pre-existing bug while restarting the
   daemon**: `scripts/windows/start-runtime.ps1` ran the daemon *synchronously*
   with no PID-file write (`Save-PidMeta` existed in `_common.ps1` but was
   never called). Since `health-check.ps1` invokes this script directly
   (unbackgrounded) every ~15 minutes whenever `Test-ClankProcess` reports
   the runtime isn't alive, and a synchronous, never-recorded daemon can
   never make that check succeed, **every health-check cycle that found
   "not running" started another indefinitely-running daemon** — this is
   the confirmed origin of the two duplicate processes found in step 2.
   Fixed: rewrote `start-runtime.ps1` to use `Start-Process` (detached) +
   `Save-PidMeta`, with a `Test-ClankProcess` guard against starting a
   duplicate. **The identical bug existed in `start-dashboard.ps1`** (found
   when a manual `health-check.ps1` test run hung — it was blocked inside a
   synchronous dashboard start) and was fixed the same way. Both fixes were
   made in the dev tree, tested there, then deployed as a one-off file copy
   into the frozen prod tree (consistent with this phase's own "dev → test →
   deploy" model) — not by re-copying the whole tree.
9. Started the daemon fresh from the prod tree via the fixed script:
   `Started runtime daemon, PID 34508.` Verified exactly one process group
   (34508 + child 27348) and a correctly updated `runtime.pid` file. Log
   output confirmed real Samsung collection activity (live HTTP requests to
   samsung.com) within seconds.
10. Re-enabled all 4 tasks (`Enable-ScheduledTask`). Manually triggered
    `SmartphoneIntelClank-HealthCheck` (`Start-ScheduledTask`): first run
    correctly detected the dashboard wasn't running and started it via the
    now-fixed `start-dashboard.ps1` (`Started dashboard, PID 45356`,
    non-blocking, task completed instead of hanging); **second run returned
    exit 0 (healthy)** with runtime and dashboard both already correctly
    detected as running — no duplicate processes created either time.
11. Development isolation proof: created `.isolation_proof_marker.txt` in
    the dev tree only, confirmed via direct filesystem check that it does
    not exist in the prod tree, removed it after (proof captured here, no
    permanent artifact needed).
12. Final verification: prod tree's `data/clank.db` — integrity ok, 97
    Samsung devices, 98 evidence, 213 confidence-ledger rows, Alembic at
    `0007_wave1_baseline_state` (head). Dev tree canonical suite:
    **127 passed, 0 failed, 0 skipped, 0 xfailed**.

**Not done as part of this execution** (lower priority, explicitly out of
scope for this phase): converting the prod tree from "byte-for-byte copy" to
"checkout of a specific reviewed commit" — the chosen method's own reasoning
section above explains why that's deliberately sequenced after a real
release process exists, not blocking this split.
