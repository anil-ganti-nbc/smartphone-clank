# Cloud Readiness Checklist — Smartphone Intel Clank

**Tier: D — Architecture preparation only.** No deployment, no Docker build,
no dependency installs, no changes to `collectors/`, `entity_resolution/`,
`normalizers/`, `alerts/`, `runtime/`, `database/`, migrations, or any test
file. This document and its sibling `CLOUD_READINESS_BLOCKERS.md`, plus
`Dockerfile.draft`, `docker-compose.draft.yml`, and
`RUNTIME_BRIDGE_DESIGN.md`, are the entire deliverable of this phase — planning
artifacts, not working infrastructure.

This work is also deliberately scoped to respect this project's own
`HANDOFF.md` §5 soak window ("no code changes for 2-3 days" while Samsung
sitemap coverage/re-sighting/alert behavior settles) and its active roadmap
toward Google as OEM #2. Nothing here touches application code, so it cannot
interfere with either.

Baseline commit audited: `eddf335` ("Baseline commit: current state of
Smartphone Clank before cloud migration"), branch `cloud/smartphone-prep`.

---

## Honest framing

Despite the repo's "Under Construction" self-label, this reads as a
substantially mature single-OEM production system — 6 Alembic migrations, a
real entity-resolution/confidence pipeline, a resolved data-quality incident
with a documented root cause and cleanup, a production-scope gate, Discord
delivery with retry/redaction, and a documented 2-3 day soak plan before the
next feature. It is not greenfield. That observation doesn't change this
phase's scope (Tier D stays architecture-prep-only) — it's noted here so the
checklist below is read as "hardening an existing system for a future port,"
not "porting a prototype."

---

## Already portable (verified by direct inspection, not assumption)

- **No hard-coded Windows absolute paths in Python source.** Grepped the
  entire tree (excluding `.venv`) for `C:\` / `C:/`-style patterns. The one
  regex hit (`tests/test_production_scope.py`) is a false positive — a
  literal `\n` inside a YAML string fixture (`"collectors:\n  ..."`), not a
  path. Confirms and corrects-by-verifying the prior audit's "no hard-coded
  paths found" claim: true, checked fresh, not just carried over.
- **No Windows-only imports anywhere** — grepped for `winreg`, `win32*`,
  `pywin32`, `ctypes.windll`, `os.startfile`, `msvcrt`: zero matches in `.py`
  source.
- **`requirements.txt` is pure cross-platform PyPI packages** — no
  `pywin32`/`pypiwin32`/platform-conditional entries. `httpx`, `sqlalchemy`,
  `pydantic`/`pydantic-settings`, `typer`, `apscheduler`, `fastapi`/`uvicorn`
  all run identically on Linux.
- **All filesystem paths are relative + `pathlib`-built**, not hard-coded —
  `"data/clank.db"`, `"data/backups"`, `"runtime/logs"`,
  `"config/config.yaml"`, etc., resolved relative to the working directory.
- **`runtime/daemon.py` locates its own root dynamically**
  (`ROOT = Path(__file__).resolve().parents[1]`, then `os.chdir(ROOT)`)
  instead of assuming a fixed install location — this pattern needs no
  change for Linux.
- **Config layering is already OS-agnostic**: `config/config.yaml` (tracked
  defaults) → `config/config.local.yaml` (untracked overlay, deep-merged) →
  `DISCORD_WEBHOOK_URL` / `MAINTENANCE_DISCORD_WEBHOOK_URL` env vars
  (highest precedence). This maps cleanly onto a container model (bake
  defaults into the image, mount or inject the rest).
- **`.env` is parsed by `config/settings.py` itself** (stdlib only, via
  `_load_dotenv()` / `os.environ.setdefault`), independent of the
  PowerShell wrapper that used to be the only thing reading it. One less
  Windows-specific dependency than the prior state.
- **Secret handling is already careful**: `Settings.__repr__`/`__str__`
  route through `alerts.delivery.redact_webhook_url()` so webhook URLs never
  leak into logs/reprs — a good pattern to carry into a container/secrets
  model unchanged.

## Needs work before a real port (see `CLOUD_READINESS_BLOCKERS.md` for detail)

- `CLANK_DATA_DIR` / `CLANK_BACKUP_DIR` / `CLANK_REPORT_DIR` /
  `CLANK_DATABASE_URL` are declared in `.env.example` but **not read by any
  Python source** — confirmed by grep, not assumed. See blockers doc, item 1.
- Three uncoordinated "where do files live" definitions exist
  (`config/config.yaml` → `database.url`; `.env.example`'s `CLANK_*` vars;
  `config/windows_runtime.yaml`'s `paths:` block, read only by
  `scripts/windows/_common.ps1`). A real port needs one source of truth.
- The Windows orchestration layer (14 PowerShell scripts under
  `scripts/windows/`, Task Scheduler install/uninstall, `docs/WINDOWS_*.md`
  runbooks) has no Linux/container equivalent — expected, since replacing it
  is the point of a future port, but it's real work, not "already done."
- `runtime/daemon.py`'s `BlockingScheduler` is a long-lived resident process
  model, not the one-shot "external scheduler triggers `docker run`, process
  exits" model used elsewhere in this migration. This is an **open design
  question**, not a blocker to be silently resolved — see below.
- No `pytest` in this project's own `.venv`; convention is invoking test
  files directly. Not wired into any CI. A Linux CI runner needs a decision
  here (add `pytest`, or port the direct-invocation convention) before any
  automated Linux test gate can exist.
- No `Dockerfile`, `docker-compose.yml`, or `.dockerignore` existed before
  this phase — this phase adds `.draft` versions only, deliberately not
  meant to be built or run.
- Versioning is fragmented across three places with no single source of
  truth: `runtime/daemon.py` (`VERSION = "0.3.6"`), `database/migrate.py`
  (`CURRENT_VERSION = "0.3.0"`, a schema version — different axis entirely),
  and prose docs (`HANDOFF.md` narrates "v0.3.9" as current). See
  `RUNTIME_BRIDGE_DESIGN.md`.

## Open design question flagged, not decided

**In-process scheduler vs. one-shot container.** `runtime/daemon.py` runs an
APScheduler `BlockingScheduler` inside a single long-lived process, meant to
be launched once (by Windows Task Scheduler today) and stay resident,
polling collectors on an interval. This doesn't fit the "external scheduler
→ one-shot container → exit" model this migration prefers elsewhere (see
Free Game Tracker / OEM Radar). A future actual port needs a product
decision between:

- **(a) Keep the in-process scheduler.** Run the container long-lived with
  `restart: unless-stopped`-equivalent supervision. Simpler migration (no
  scheduling-logic changes), but diverges from this migration's preferred
  one-shot pattern and reintroduces "is the daemon still alive" as an
  ongoing operational concern inside the container world too.
- **(b) Refactor to an external-scheduler one-shot model.** Strip
  `BlockingScheduler` out of `runtime/daemon.py`, expose a `run --once`-style
  entry point (already exists on the CLI side — see `main.py run --once`),
  and let cron/systemd-timer/host-scheduler trigger `docker run` per cycle,
  matching Free Game Tracker/OEM Radar. Consistent with the rest of the
  migration, but touches `runtime/daemon.py` scheduling logic — explicitly
  out of scope for this Tier D phase (`runtime/` is on the do-not-touch
  list), and would need its own reviewed change.

This document does not choose between them. That decision needs a human
call and, per this phase's scope, cannot be made or implemented here.

## Documented known blockers (carried faithfully from `HANDOFF.md`, not re-derived)

1. **Cycle-completion counter bug** —
   `collectors/samsung/sitemap_collector.py`'s
   `if cov["never_attempted"] == 0: cycles_completed += 1` increments on
   every run once the first full lap ever completes, not only on a genuine
   fresh lap. Live `cycles_completed = 42` is not a meaningful count. Does
   not affect coverage accuracy (`coverage_report()`'s numbers are computed
   independently and are correct); not wired into any report/health/CLI
   output today, so low-impact but real.
2. **3 tests blocked by a stale import rename** — `tests/test_change_detection.py`
   imports `extract_hashes`/`compare_hashes` from
   `knowledge/change_detection.py`, which now exports
   `extract_fingerprint`/`compare_fingerprints` instead. Unrelated to any
   cloud-prep work; not fixed here.
3. **`samsung_us_owners_product`** is `LIVE_VALIDATED` in
   `config/samsung_sources.yaml` but has no collector implementation.
   Explicitly excluded from `production_scope()` via
   `RUNNABLE_SAMSUNG_SOURCE_IDS` so scope never advertises a source nothing
   can run.
4. **Past data-quality incident (resolved)** — 73 non-Samsung device rows
   traced to one manual `main.py run --once` on 2026-08-05 with OEM
   collectors mistakenly enabled in `config.yaml`; parser garbage, not real
   intelligence. Backed up (`data/backups/clank_pre_v039_cleanup_*.db`),
   then deleted; `collector_runs` audit trail deliberately preserved. Now
   gated behind `production_scope()`'s unified eligibility check.

## Explicitly out of scope for this phase

- Building or running the draft Docker image.
- Deciding the scheduler model (see open question above).
- Any change to `collectors/`, `entity_resolution/`, `normalizers/`,
  `alerts/`, `runtime/daemon.py`, `database/` (including migrations), or any
  existing test file.
- Fixing any of the four documented known blockers.
- Implementing a working `identity`/`health` CLI command (design only — see
  `RUNTIME_BRIDGE_DESIGN.md`).
