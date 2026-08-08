# Cloud Readiness Blockers — Smartphone Intel Clank

Companion to `CLOUD_READINESS_CHECKLIST.md`. This file is the detailed,
evidence-backed list of what would actually need to change before a real
Linux/Docker port — as opposed to what's already fine. Nothing here is
fixed in this phase (Tier D: architecture prep only, no code changes to
`collectors/`, `entity_resolution/`, `normalizers/`, `alerts/`, `runtime/`,
`database/`, or migrations).

---

## 1. `.env.example`'s `CLANK_*` path vars are declared but not wired

`.env.example` advertises:

```
CLANK_DATABASE_URL=sqlite:///./data/clank.db
CLANK_DASHBOARD_HOST=127.0.0.1
CLANK_DASHBOARD_PORT=8200
CLANK_LOG_LEVEL=INFO
CLANK_DATA_DIR=data
CLANK_BACKUP_DIR=runtime/backups
CLANK_REPORT_DIR=runtime/reports
CLANK_RUNTIME_MODE=production
```

Grepping the entire Python source tree for each of these names:

| Var | Actually read anywhere in `.py` source? |
|---|---|
| `CLANK_DATABASE_URL` | **No.** |
| `CLANK_DATA_DIR` | **No.** |
| `CLANK_BACKUP_DIR` | **No.** |
| `CLANK_REPORT_DIR` | **No.** |
| `CLANK_DASHBOARD_HOST` | No (only read in `scripts/windows/_common.ps1` / `start-dashboard.ps1`, PowerShell only). |
| `CLANK_DASHBOARD_PORT` | No (same — PowerShell only, `install.ps1` / `_common.ps1`). |
| `CLANK_RUNTIME_MODE` | No (same — PowerShell only, `_common.ps1`). |
| `CLANK_LOG_LEVEL` | **Yes** — `runtime/daemon.py:69`, via `os.environ.get("CLANK_LOG_LEVEL", "INFO")`. |

The only `CLANK_*` env vars actually consumed by Python are:
- `CLANK_ENV_FILE` (`config/settings.py:61` — which `.env` file to load)
- `CLANK_LOCAL_CONFIG` (`config/settings.py:73` — which local overlay YAML to load)
- `CLANK_CONFIG` (`runtime/daemon.py:72` — which `config.yaml` to load, daemon only)
- `CLANK_LOG_LEVEL` (`runtime/daemon.py:69`, daemon only)

`Settings` (in `config/settings.py`) is a `pydantic_settings.BaseSettings`
subclass with `env_prefix = "CLANK_"`, but its only declared fields are
`config_path`, `raw`, and `local_config_loaded` — none named `database_url`,
`data_dir`, `backup_dir`, or `report_dir` — so the `CLANK_` env-prefix
mechanism has nothing to bind those names to even though pydantic-settings
is in play. `database_url` is a computed `@property` that reads
`self.get("database", "url", ...)` from YAML, not from environment.

**Practical effect today**: the only way to relocate the database is editing
`database.url` inside `config/config.yaml` or `config/config.local.yaml`.
Backup/report directories are hard-coded literal defaults
(`"data/backups"` in both `database/migrate.py:40` and
`database/migrations_ordered.py:317`, duplicated rather than centralized).
**This directly contradicts the assumption that these vars are "already
wired through `config/settings.py`."** They are declared as an interface
contract in `.env.example` but nothing implements that contract. A real
container port needs either (a) `Settings` gains real fields for these and
`config/settings.py` wires them into `database_url`/backup/report paths, or
(b) `.env.example` is corrected to stop advertising an interface that
doesn't exist. Neither is done here — this phase only documents the gap.

## 2. Three uncoordinated "where do files live" definitions

- `config/config.yaml` → `database.url` (the only one Python actually reads
  for the DB path).
- `.env.example` → `CLANK_DATA_DIR` / `CLANK_BACKUP_DIR` / `CLANK_REPORT_DIR`
  (declared, unread — see item 1).
- `config/windows_runtime.yaml` → a `paths:` block
  (`data_dir`, `log_dir`, `pid_dir`, `backup_dir`, `report_dir`,
  `diagnostics_dir`), read only by `scripts/windows/_common.ps1` (confirmed
  by grep — `windows_runtime.yaml` is referenced in exactly two places, both
  PowerShell: `_common.ps1:14` and `collect-diagnostics.ps1:21`). Python
  never opens this file.

A real port needs one source of truth for storage locations, not three that
happen to agree today by coincidence of matching literal defaults.

## 3. Windows-only orchestration layer has no Linux equivalent yet

`scripts/windows/` contains 14 PowerShell scripts (`install.ps1`,
`uninstall.ps1`, `start-runtime.ps1`, `stop-runtime.ps1`,
`restart-runtime.ps1`, `status.ps1`, `health-check.ps1`,
`backup-database.ps1`, `generate-daily-report.ps1`,
`generate-weekly-report.ps1`, `collect-diagnostics.ps1`,
`validate-runtime-supervision.ps1`, `start-dashboard.ps1`,
`stop-dashboard.ps1`, `_common.ps1`) plus a matching `docs/WINDOWS_*.md`
runbook set (`WINDOWS_INSTALL.md`, `WINDOWS_OPERATIONS.md`,
`WINDOWS_READINESS_AUDIT.md`, `WINDOWS_TROUBLESHOOTING.md`,
`WINDOWS_VALIDATION_CHECKLIST.md`). None of this is Python, so it isn't a
"Windows assumption in the app" in the portability-bug sense — but it *is*
the entire install/health/backup/reporting operational surface today, and
none of it carries over to Linux/Docker. Replacing it is exactly what a
real port would need to do (systemd timers or cron in place of Task
Scheduler, shell scripts or the future `runtime_bridge.py`/container
healthcheck in place of `health-check.ps1`, etc.) — flagged as real,
non-trivial work, not something already solved by the app being
"basically portable" at the Python level.

## 4. Scheduler model — open design question (see checklist for full writeup)

`runtime/daemon.py` runs `apscheduler.schedulers.blocking.BlockingScheduler`
in a long-lived resident process, launched once via Task Scheduler
(`.venv\Scripts\python.exe -m runtime.daemon`, per the module's own
docstring) and expected to stay running indefinitely. This is a different
execution model from the "external scheduler triggers a one-shot container,
container exits" pattern this migration prefers elsewhere (Free Game
Tracker, OEM Radar). Needs a product decision (keep in-process + long-lived
container, vs. refactor to one-shot + external scheduler) before a real
port. Not decided or implemented here — `runtime/` is explicitly off-limits
for this phase.

## 5. No `pytest` in `.venv` — CI portability gap

This project's own `.venv` has no `pytest` installed; the working
convention (confirmed) is running test files directly:
`.venv\Scripts\python.exe test_file.py`. Per `HANDOFF.md` §3.5: "78 passed /
0 failed / 3 blocked" is itself qualified as true only "under correct
invocation" — four files (`test_aliases_timeline`, `test_decay`,
`test_entity_resolution`, `test_knowledge`) only pass when run with a
`sys.path` bootstrap that direct `python file.py` invocation on those
specific files doesn't have by default. This dual convention (some files
runnable bare, some need path setup) is itself fragile and would need
resolving — either by adding `pytest` (trivial, but changes the project's
current testing convention, which is out of scope here) or by porting the
direct-invocation runner to something Linux-CI-friendly. No CI system
(GitHub Actions, etc.) currently exists in this repo to wire either option
into. This is a real gap, not a Windows-specific one — it would block
automated testing in *any* CI, container-based or not.

## 6. No Dockerfile/compose ever existed before this phase

Confirmed: no `Dockerfile*` or `docker-compose*` file existed in this repo
prior to this branch. `Dockerfile.draft` and `docker-compose.draft.yml`
added in this phase are drafts only — not built, not tested, named
`.draft` specifically so they aren't mistaken for active deployable config.

## 7. Fragmented versioning

- `runtime/daemon.py:30` — `VERSION = "0.3.6"` (daemon's own version string,
  logged at startup, not surfaced anywhere else).
- `database/migrate.py:23` — `CURRENT_VERSION = "0.3.0"` (schema/migration
  version — a different axis than app version entirely; do not conflate).
- Prose docs (`HANDOFF.md`, `PROGRESS_v0.3.7.md`, `docs/PROGRESS_v0.3.8.md`)
  narrate the project as being at "v0.3.9" as of this session.

No single machine-readable place answers "what version is this process
running." A future container image would want one canonical identity
source (see `RUNTIME_BRIDGE_DESIGN.md`) instead of three numbers that can
drift independently.

## 8. Minor dependency-hygiene notes (not blockers, worth recording)

- `playwright>=1.40.0` is declared in `requirements.txt` ("only if
  absolutely needed for JS-heavy pages") but is not imported anywhere in
  current source (confirmed by grep). If a future collector starts using
  it, a real Docker image will need extra system packages (browser
  binaries, fonts, shared libs) not accounted for in `Dockerfile.draft`
  today. Not needed for the current collector set.
- `lxml` and `selectolax` are compiled/native-extension dependencies.
  Whether `python:3.12-slim`-family base images need extra build tooling
  (e.g. `gcc`, `libxml2-dev`) to install them hasn't been verified — that
  would require actually running `pip install`/`docker build`, which is out
  of scope for this phase.

## 9. Documented known blockers, carried faithfully from `HANDOFF.md` §4 and §3.5

These are pre-existing, real, and already known to the project — listed
here for completeness, not re-derived or newly discovered by this audit:

1. `collectors/samsung/sitemap_collector.py` cycle-completion counter
   increments on every run after the first full lap, not only on genuine
   fresh laps (`cycles_completed = 42` live, not a meaningful count;
   coverage accuracy itself is unaffected).
2. 3 tests in `tests/test_change_detection.py` blocked by a stale import —
   expects `extract_hashes`/`compare_hashes`, `knowledge/change_detection.py`
   now exports `extract_fingerprint`/`compare_fingerprints`.
3. `samsung_us_owners_product` is validated in
   `config/samsung_sources.yaml` but has no collector implementation;
   explicitly excluded from `production_scope()`.
4. A past data-quality incident (73 junk device rows from a misconfigured
   manual run) has already been fully investigated, backed up, and cleaned
   up, and is now structurally prevented by `production_scope()`'s unified
   eligibility gate.

None of these four are cloud-migration blockers per se — they are correctness
issues in the existing single-OEM system, orthogonal to portability. They're
listed here only because they were explicitly requested to be carried
forward faithfully.
