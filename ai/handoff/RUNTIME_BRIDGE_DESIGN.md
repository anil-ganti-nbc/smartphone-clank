# Runtime Bridge Design (draft) — version / identity / health adapter

**Status: design sketch only. Not implemented.** No CLI command, no new
importable module with working logic, no change to `main.py` behavior exists
as a result of this document. Per Tier D scope, implementing a merged,
working `identity`/`health` CLI command would cross into "deployment
prep beyond architecture planning" — this doc stops at the sketch.

## Why

Other repos in this cloud-migration project (Free Game Tracker) expose a
small, honest triad of introspection commands — `version`, `identity`,
`health` — that a container orchestrator (or a human) can query without
guessing from logs. Smartphone Clank has none of these today:

- No `version` command. Version info is fragmented (see
  `CLOUD_READINESS_BLOCKERS.md` §7): `runtime/daemon.py`'s
  `VERSION = "0.3.6"` is never surfaced via CLI; `database/migrate.py`'s
  `CURRENT_VERSION = "0.3.0"` is a schema version, a different concept.
- No `identity` command — nothing reports "what am I" (config provenance
  exists via `python main.py production scope`, but that's collector/config
  scope, not process identity).
- No `health` command in the container-healthcheck sense. `main.py` does
  have `report daily` / `health_score()` logic (per-collector health,
  0-100 scored), which is a *reporting* feature, not a fast liveness probe.

A future container port (whichever scheduler model is chosen — see the open
question in `CLOUD_READINESS_CHECKLIST.md`) will want a cheap, fast,
dependency-light way to answer "is this process alive and basically sane"
for `HEALTHCHECK`/orchestrator probes, separate from the existing
`report daily` business-logic health scoring (which hits the DB, computes
resighting/alert stats, and is not meant to run every 30 seconds).

## Where it would hook in

A new module alongside the existing entry points — **not inside
`runtime/daemon.py`** (off-limits this phase) and not modifying `main.py`'s
existing command behavior:

```
smartphone-clank/
  main.py              # existing Typer CLI — unchanged
  runtime/
    daemon.py           # existing scheduler process — unchanged
    runtime_bridge.py    # NEW (future phase): thin identity/health adapter
```

`runtime_bridge.py` would be imported by `main.py` to register three new
**read-only, side-effect-free** Typer commands (`version`, `identity`,
`health`), and separately importable by `runtime/daemon.py` if a future
container wants an in-process HTTP or file-based healthcheck endpoint — but
that wiring is future work, not part of this sketch.

## Sketched fields (not implemented)

### `version`
Plain string or JSON, single source of truth (would need to replace the
two independent `VERSION`/`CURRENT_VERSION` constants, or at minimum
compose them so they can't silently disagree):

```json
{
  "app_version": "0.3.9",
  "schema_version": "<from database/migrate.py CURRENT_VERSION, or read live via alembic_version table>",
  "daemon_version": "<from runtime/daemon.py VERSION, if daemon module is importable without side effects>"
}
```

Open question for a real implementation: today `runtime/daemon.py` has
top-level side effects on import (`os.chdir(ROOT)` at module scope,
line 28) — a version adapter that merely imports it to read `VERSION`
would need that guarded or the constant relocated, which is itself a
`runtime/` change and therefore out of scope this phase. Flagging, not
fixing.

### `identity`
Mirrors what `python main.py production scope` already computes
(`Settings.effective_source_summary()`), reframed as process identity
rather than collector scope:

```json
{
  "config_source": "config/config.yaml",
  "local_override_active": false,
  "production_samsung_only": true,
  "runtime_mode": "<would need CLANK_RUNTIME_MODE actually wired — currently PowerShell-only, see blockers doc>",
  "release_channel": "<no equivalent concept exists today — would be new>"
}
```

`release_channel` (production/experimental, as Free Game Tracker uses) has
no analog in this codebase today. Introducing one is a real design decision
for whoever implements this, not something this sketch pre-decides.

### `health`
A **fast** probe, deliberately distinct from `report daily`'s
`health_score()` (which is a slower, DB-heavy business report). Sketched
fields:

```json
{
  "operational_state": "healthy | degraded | unknown",
  "database_reachable": true,
  "database_path": "<resolved database.url>",
  "last_collector_run_at": "<most recent CollectorRun.completed_at, cheap indexed lookup only>",
  "status_reasons": []
}
```

Design intent: this should answer "is the process/DB minimally alive"
in well under a second, suitable for a container `HEALTHCHECK` polling
every 30-60s — not replicate `report daily`'s full resighting/alert
analysis. Distinguishing "fast liveness probe" from "business health
report" is the main design decision this sketch is flagging for whoever
implements it.

## Explicitly not part of this sketch

- No code in `runtime_bridge.py` exists — this phase adds no such file.
- No `main.py` command registration change.
- No decision on `release_channel` semantics or values.
- No decision on how `health` would behave under the still-undecided
  scheduler model (one-shot containers arguably don't need a long-polled
  `HEALTHCHECK` at all — an external scheduler already knows the last run
  exited 0; a long-lived daemon container does need one). This is a second
  angle on the same open scheduler-model question raised in
  `CLOUD_READINESS_CHECKLIST.md` and is left there, not resolved here.
