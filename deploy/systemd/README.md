# Smartphone Clank source-timer cutover

These units replace the resident `smartphone-clank.service` scheduler with
eight independently scheduled one-shot services. They do not change source
scope, database schema, database path, dashboard service, or backup timer.

## Safety model

- systemd refuses a second activation of an already-active service instance;
- `runtime.locks.FileLock` also refuses a same-source duplicate from any
  launcher;
- different source services may be active concurrently, but each waits on a
  kernel-managed shared execution lock before its due-check and collector run;
- the shared lock deliberately serializes the complete run because production
  SQLite uses rollback-journal mode and cross-source logical writes are not
  proven safe;
- a process exit releases both locks even though the audit-friendly lock file
  names remain on disk.

The separate waiting services are the key behavior change: a long Samsung run
cannot cause Google or another source to exceed an in-memory APScheduler grace
window and disappear. A due service remains visible and executes when the
shared lock becomes available.

## Semantics mapping

| Resident APScheduler behavior | Source-timer replacement |
|---|---|
| `IntervalTrigger` cadence | Matching `OnUnitActiveSec` per source |
| staggered startup `DateTrigger` | Distinct `OnActiveSec` offsets from 30 seconds to 14 minutes |
| `max_instances=1` | systemd instance state plus non-blocking per-source application lock |
| `coalesce=True` | an active one-shot service is not started again; one active invocation survives |
| default one-second misfire grace | removed; independent service invocations wait rather than being discarded |
| retry behavior | unchanged: no immediate retry; the next source timer activation is the next attempt |
| failure/health records | unchanged pipeline path; Google adds explicit `degraded`/`unexpected_zero` states |
| startup registry/scope checks | `runtime.run_once.build_targets()` fails closed before selection |
| graceful daemon shutdown | one-shot services terminate naturally; systemd owns process lifecycle |

## Controlled production procedure

An authorized operator must preserve evidence before installing these files.
Do not perform this procedure from an account that cannot act as root and the
`smartphone-clank` service user.

1. Record the old SHA, units, last source rows, integrity result, and counts.
2. Confirm no collector job is active, then stop (but do not yet disable) the
   resident `smartphone-clank.service`.
3. Take a consistent SQLite backup as the service user, verify its integrity,
   record SHA-256 and schema revision, and leave the original DB in place.
4. Deploy the accepted merged Git SHA to `/opt/smartphone-clank`; verify the
   checkout and runtime both identify that exact revision.
5. Install the template and timer units, then run two controlled source
   services separately. Verify integrity, counts, event/alert deltas, and lock
   release after each.
6. Enable/start the eight timers and disable the resident scheduler. Do not
   leave both complete scheduler architectures enabled.
7. Observe natural Samsung, Google, and at least one further source activation.
   Confirm a waiting source survives a long Samsung run and no APScheduler
   misfire warnings appear after the new soak start.

Any runtime change starts a new soak clock. Preserve the old database history;
do not rebaseline.

## SOAK collector stage (generic mechanism)

`smartphone-clank-soak@.service` is the generic opt-in soak mechanism: it
runs `python -m runtime.run_once --environment staging --collector <source>`
with `CLANK_CONFIG=config/config.staging.yaml` (the isolated
`clank-staging.db`). It has **no `[Install]` section**, so an operator
enables a `smartphone-clank-soak@<source>.timer` instance explicitly once a
source's soak is approved.

- `--environment staging` forces `build_staging_targets()`, which (a) calls
  `assert_db_matches_environment(STAGING)` so a production DB cannot be
  opened, and (b) is the only route that builds soak collectors
  (`collectors.SOAK_SAMSUNG_SOURCE_IDS`, currently empty).
- `alerts/source_maturity.py` suppresses every newsroom send for a
  not-yet-promoted source (fail-closed), regardless of environment.

## CANARY (samsung_us_owners_product, since 2026-08-30)

After completing its staging soak (baseline 2026-08-26 03:48Z + 32 clean
repeat cycles, zero failures — see
`docs/infra/SAMSUNG_US_OWNERS_PRODUCT_CANARY_REPORT.md`),
`samsung_us_owners_product` was promoted SOAK → CANARY:

- The retired `smartphone-clank-soak@samsung_us_owners_product.timer`
  (staging) is replaced by the production per-source timer
  `smartphone-clank-samsung_us_owners_product.timer` →
  `smartphone-clank-source@.service` → production `config/config.yaml` and
  the production DB. Cadence is unchanged (3h).
- CANARY still has **no notification authority**: the source is absent from
  `alerts/source_maturity.py::PRODUCTION_SOURCES` (fail-closed soak
  classification), so every newsroom decision in production is suppressed
  with a `WebhookDelivery` evidence row. Full production requires the
  separate, reviewed edit to that module (Fleet Law 8).
- The production invocation's first run is a fresh baseline against the
  production DB (no state carries over from staging). Expect suppressed
  (never delivered) new-device decisions; see the canary report's baseline
  expectations.
- Rollback: `systemctl disable --now
  smartphone-clank-samsung_us_owners_product.timer` (re-enable the soak
  timer only via a reviewed revert). No data is deleted by disabling.

## Production invocation defaults

Production invocation (`--environment production`, the default) builds only
accepted production/canary collectors; soak sources are never reachable from
it (`tests/test_run_once_environment.py` pins this).
