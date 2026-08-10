# Scheduler migration: BlockingScheduler daemon -> external one-shot

2026-08-10. Implements the previously-reviewed and approved Architecture A
(external scheduler + one-shot application execution). This document is the
required behavioral mapping -- every responsibility the prior
`runtime/daemon.py` (`apscheduler.schedulers.blocking.BlockingScheduler`)
provided, and its explicit replacement or justification for not needing one.

## Before re-reading this: re-verified against current `main` first

Confirmed unchanged from the prior architecture review before implementing
anything: same scheduled jobs, same cadences (45/60/60/60/60/180/180/240
x4/300/360x3 minutes across `config.yaml` + `samsung_sources.yaml`), same
`max_instances=1`/`coalesce=True`/`replace_existing=True` job settings, same
one-time `DateTrigger` startup jobs staggered 5/20/30s, same
`samsung_us_support_sitemap` critical-registration check, same signal
handlers, same lack of any daemon-liveness health dependency.

## Complete responsibility mapping

| BlockingScheduler responsibility | Replacement | Why |
|---|---|---|
| Multiple independent cadences (`IntervalTrigger` per collector) | Preserved as-is: `runtime/run_once.py`'s `is_due()` reads the same `interval_minutes` from the same `config.yaml`/`samsung_sources.yaml` | No change needed -- the cadence data was never scheduler-internal state |
| Per-source schedules | Preserved (same source, same mechanism) | Same reason |
| `max_instances=1` (same-collector duplicate prevention) | External `flock` wrapper around the whole one-shot invocation, at the cron level (`deploy_run.sh` on Hetzner) | This was **already only an in-process guarantee** -- APScheduler's default job store is in-memory, so it never actually protected against two separate OS processes. No lock code of any kind exists anywhere in this codebase prior to this change. `flock` is new safety, not a replacement for something that worked before across processes. |
| `coalesce=True` (collapse missed runs into one) | Not needed | There is no in-process missed-run queue under an external-scheduler model to collapse in the first place -- each tick either finds a collector due or it doesn't |
| One-time `DateTrigger` startup jobs (staggered 5/20/30s) | Not needed | The very first tick against a fresh/empty `CollectorRunRecord` table finds every collector due (no recorded run) and runs all of them -- equivalent first-run coverage without a separate startup concept |
| Retry/backoff | Unchanged | This was never implemented by the scheduler itself -- a failed collector simply remains "due" per the same `interval_minutes` and is retried on the next natural tick, exactly as before |
| "Daemon alive" heartbeat | N/A -- never existed | `dashboard/app.py`'s `/healthz` was independently confirmed (during the prior architecture review) to only check DB connectivity, never daemon liveness. Nothing to preserve, nothing fabricated. |
| Startup registry validation (`samsung_us_support_sitemap` must be registered) | Preserved verbatim in `run_once.py` | Direct copy of the same check |
| Signal handling / graceful shutdown | N/A under one-shot model | A one-shot process either completes a collector run or the whole container is killed before starting the next one -- there is no long-lived loop to signal out of |

## What changed vs. what didn't

**Changed**: `runtime/run_once.py` is new. `Dockerfile` /
`docker-compose.staging.yml` are new (the `.draft` files predate this
implementation and were promoted/replaced). `config/config.docker.yaml` is
new (a local-config-overlay file using the *already-existing*
`CLANK_LOCAL_CONFIG` mechanism in `config/settings.py` -- no changes to
`settings.py` itself -- to point the database at the mounted volume instead
of the repo-relative default).

**Not changed**: `runtime/daemon.py` itself (left in place, still valid for
any future Windows/local use), collector registry, collector scope,
production allowlist, database schema, database initialization logic
(`database/session.py`'s `Base.metadata.create_all` -- already safe,
additive-only, not touched), any collector/parser/entity-resolution code,
notification behavior.

## Provenance

Same pattern as every other clank in this fleet:
`org.opencontainers.image.revision` (OCI label, from a `GIT_REVISION` build
arg) plus `CLANK_SOURCE_REVISION` env var. This project had no existing
identity/version contract; exposing `source_revision` through a
dashboard-facing endpoint was assessed as not cleanly compatible without
touching `dashboard/app.py`'s existing `/healthz` shape more than this
scheduler-migration task's scope allows -- **GitHub SHA == OCI revision** is
therefore the authoritative provenance record for this deployment, per the
brief's own explicit fallback rule ("if exposing `source_revision` would
require an invasive shared-runtime schema change, stop and report that
architectural boundary rather than hacking around it"). Verifiable via
`docker inspect <image> --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'`.

## Persistent state

Fresh isolated Hetzner volume (`smartphone_clank_staging_data`) -- the
Windows local database was not copied, per the default migration model and
this being under-construction/staging soak, not a promotion of existing
production state.

## Locking, proven

An external `flock`-wrapped deliberate overlap test (two `docker compose
run` invocations, fired truly simultaneously) confirmed the second is
refused before it starts (no output, no writer), the first completes
normally. See `ai/handoff/HETZNER_DEPLOYMENT.md` for the actual command
and result.
