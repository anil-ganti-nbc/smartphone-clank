# Scheduler remediation: resident APScheduler to source-level systemd timers

## Decision

Use one external systemd timer and one-shot service per accepted production
source. Do not use a worker pool and do not increase APScheduler's misfire
grace as the primary fix.

Production evidence from the resident scheduler showed 165 lost due
executions by 2026-08-14 19:59 UTC, with lateness up to 95.480 seconds. The
single worker avoided database races, but APScheduler discarded other due jobs
when Samsung occupied that worker beyond the default grace window.

## Re-evaluated options

### A. Source-specific external timers — selected

Each source has an independent systemd timer and visible one-shot service.
The process first obtains a non-blocking same-source lock, then waits on a
blocking shared execution lock. This keeps the current database safety
property (only one complete pipeline run writes at a time) without letting a
different source's due invocation disappear.

### B. Bounded worker pool — rejected for now

Network collection could run concurrently, but the current pipeline shares
entity, evidence, timeline, baseline, alert, and absence/removal state. A
worker-pool change would require splitting collection from persistence across
both collector families and proving more logical invariants than this P1 fix
needs.

### C. APScheduler executor redesign — rejected

More workers would expose the same unproven concurrent-write semantics. A
larger grace window would keep the single queue and merely hide/delay the
observed failure mode.

## Current database/concurrency evidence

- SQLite journal mode: `delete`.
- Connection busy timeout: 5000 ms.
- Foreign keys are enabled by SQLAlchemy's connection hook for application
  connections; an independent read-only audit connection correctly reported
  its own default as off.
- Base collectors perform network work before a transaction, while Wave OEM
  cycles also discover before opening their persistence transaction.
- Both paths write shared device/evidence/timeline/alert/metrics tables.
- Wave cycles temporarily set an in-process `DiscordAlerter.backfill` flag.
- WAL alone would not resolve duplicate entity/alert or absence/removal races.

Cross-source concurrent writes are therefore **not proven safe**. The selected
design serializes the complete one-shot run. This is conservative but bounded:
the process for every due source already exists and waits on a kernel lock, so
there is no scheduler grace window that can discard it.

## Responsibility mapping

| Old responsibility | Replacement |
|---|---|
| independent interval jobs | one timer per source with the same configured cadence |
| `max_instances=1` | systemd service-instance state plus non-blocking per-source file lock |
| `coalesce=True` | an active service instance remains the single surviving invocation |
| default misfire grace | removed; the started service waits for the shared execution lock |
| staggered startup dates | distinct `OnActiveSec` offsets, relative to timer activation on both cutover and reboot |
| startup scope validation | fail-closed target construction before source selection |
| failure isolation | one service/process per source; a nonzero exit does not stop other timers |
| run/health recording | existing pipeline and immutable metrics rows |
| retry behavior | unchanged: next configured interval, no new immediate retry |
| graceful shutdown | one-shot process lifecycle managed by systemd |
| daemon restart after reboot | timers start from their staggered boot offsets |

The canonical source/cadence map remains:

| Source ID | Cadence |
|---|---:|
| `samsung_us_support_sitemap` | 180 min |
| `google_store_category_phones` | 45 min |
| `nothing_products_sitemap` | 90 min |
| `oneplus_regional_sitemap` | 90 min |
| `motorola_regional_sitemap` | 360 min |
| `honor_global_sitemap` | 360 min |
| `oppo_global_sitemap` | 360 min |
| `realme_regional_sitemap` | 360 min |

No source is added or removed.

## Provenance

Every one-shot logs `source_revision=<full SHA>` by reading the actual checkout
with `git rev-parse HEAD`. `CLANK_SOURCE_REVISION` may be supplied only as a
full 40-character SHA; malformed values report `unknown`. Deployment must
still compare GitHub's accepted merge SHA, the checkout SHA, and the logged
runtime SHA rather than trusting a tag or directory name.

## Soak rule

Installing this runtime starts a new soak clock. Historical database and run
evidence remains intact but cannot be counted as unattended evidence for the
new scheduler architecture.
