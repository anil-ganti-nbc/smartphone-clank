# HANDOFF — Smartphone Intel Clank

Last updated: 2026-08-11. **Smartphone Intel Clank's multi-OEM production
soak began 2026-08-11** (see §12e) after the final pre-soak expansion
mission promoted Oppo and Realme (`docs/wave2/{OPPO,REALME}_CANARY_REPORT.md`).
**No new OEMs will be added during the soak** unless a production incident
forces architectural work. This followed the Honor production-canary
phase (§12d, `docs/wave2/HONOR_CANARY_REPORT.md`), the
production-scope-unification phase (§12c,
`docs/infra/PRODUCTION_SCOPE_AUDIT.md`, `docs/infra/ZERO_ROW_TABLE_AUDIT.md`),
the Wave 2 engineering-governance + Motorola production-canary phase (§12b,
`docs/ENGINEERING_PRINCIPLES.md`), the Wave 2 qualification phase, the
alert-persistence-semantics cleanup phase (`Alert` now means exactly
"delivered to Discord," see §9), the OnePlus/Nothing/Google
production-canary phases, and, before those, the production/development
isolation hardening phase.

Permanent project policy — read before any large addition:
`docs/ENGINEERING_PRINCIPLES.md`, `docs/ARCHITECTURE_MAP.md`,
`docs/SOURCE_INVENTORY.md`.

This is the authoritative "what's actually true right now" document. If this
conflicts with a `docs/V038_*`, `docs/wave1/*`, `docs/infra/*`, or
`PROGRESS_v0.3.*` doc, **this file wins** — those are historical audit
trails / detailed working documents, this is current state.

## 0. Infrastructure isolation status (read this first)

**Physical production/development tree separation is DONE, as of 2026-08-10.**

```text
Production:   C:\Users\anil\Desktop\smartphone-clank-prod
              - frozen, real Task Scheduler target (4 SmartphoneIntelClank-*
                tasks, verified by reading definitions back after repointing)
              - live daemon runs here exclusively (PID recorded, exactly one
                instance, verified via two consecutive health-check cycles)
              - production DB: data\clank.db (97 Samsung devices, 98
                evidence, Alembic head 0007_wave1_baseline_state)
              - has PRODUCTION_TREE.txt

Development:  C:\Users\anil\Desktop\smartphone-clank  (this tree, unchanged name)
              - all Claude Code editing happens here
              - staging DB: data\clank-staging.db
              - has DEVELOPMENT_TREE.txt
              - no Task Scheduler task references this tree anymore
```

Full execution log (every command run, every output): `docs/infra/PROD_DEV_SPLIT.md`.
Two real, independent pre-existing bugs were found and fixed while restarting
the daemon: `start-runtime.ps1` and `start-dashboard.ps1` both started their
process synchronously with no PID recording, so `health-check.ps1` could
never detect a running instance and would start a duplicate every ~15
minutes — this is the confirmed origin of two orphaned daemon processes
found and stopped during this phase. Both scripts now start detached with a
recorded PID and a duplicate-start guard. See `docs/infra/ISOLATION_AUDIT.md`
for the full adversarial checklist, post-execution — all items pass except
two documented, low-severity, explicitly-scoped gaps.

**What was fixed before the physical split, and still holds**: the
schema-mutation risk. Production and staging databases are Alembic-stamped
and migration-gated — the live daemon, `main.py run`/`init` (production),
and the cloud one-shot runner all refuse to start rather than silently call
`create_all()` if schema is behind. See `docs/infra/MIGRATION_AUDIT.md`,
`docs/infra/PRODUCTION_RUNTIME.md`.

Section 11's old "briefly appeared in production, root cause not fully
isolated" note is superseded — see §11.0, the root cause is fully identified
and fixed.

**Remaining `create_all()` read-path hazard (from §0's prior "known limitation")
is now also fixed**, 2026-08-10: `main.py report`, `dashboard/app.py::create_app()`
(a real production runtime path — launched by `start-dashboard.ps1`,
supervised by `health-check.ps1`), and `collectors/samsung/sitemap_collector.py`
(the highest-frequency hazard — ran on every Samsung collection cycle, not
just daily reports) all called `create_all()`/`checkfirst=True` table
creation. All three now call `database/schema_guard.py::ensure_tables_present_or_refuse()`
instead — refuse with a clear message if a required table is missing, never
create one. Regression tests: `tests/wave1/test_schema_authority.py` (5 new
tests). Canonical suite grew from 127 → 132 as a result. Two low-severity,
documented gaps remain deliberately unfixed this phase (`main.py db init`'s
create_all-on-empty-DB fallback, and a handful of manual/non-scheduled CLI
commands like `status`/`decay`/`family` that still call `init_db()` directly
— none of these are scheduled or reachable from the live daemon).

**Google, Nothing, and OnePlus all promoted to production, 2026-08-10** —
Wave 1 production expansion is complete. See §12.

## 1. Project purpose

Smartphone Intel Clank is a smartphone-release intelligence system: it
discovers phones from official first-party sources it was never explicitly
told about, resolves them into a canonical device catalogue with provenance,
tracks confidence/evidence over time, and alerts a Discord "newsroom" channel
only when something genuinely new or changed appears — never on baseline
catalogue import, never on unchanged re-sightings, never on unvalidated
marketing text.

## 2. Deployment topology

```text
LOCAL (this machine)           GITHUB                  HETZNER / CLOUD
  experimental dev               canonical source         production runtime
  staging DB + staging Discord   repository                trusted DB, real Discord
  candidate collectors                                     real monitoring
```

- **Production**: `data/clank.db`, Windows-scheduled (`runtime/daemon.py` /
  Task Scheduler), real newsroom + maintenance Discord webhooks.
- **Staging**: `data/clank-staging.db`, invoked via `python main.py --environment staging run --once`,
  isolated staging-only Discord webhook (`STAGING_DISCORD_WEBHOOK_URL`), never
  scheduled/daemonized.
- A cloud-migration one-shot execution path also exists (`runtime/run_once.py`,
  `docker-compose.staging.yml`, `config/config.docker.yaml` — added in a
  separate PR, "staging" there means "the Docker Compose staging deployment
  environment," a **different concept** from this document's `--environment staging`
  flag; do not confuse the two).

## 3. Production/staging separation (hard, not just convention)

- `runtime/environment.py::assert_db_matches_environment(database_url, environment)`
  fails closed both directions: `--environment staging` refuses to open a
  database_url that doesn't contain `"staging"`; `--environment production`
  refuses to open one that does. Checked at CLI startup before `init_db()`.
- `runtime/environment.py::assert_safe_to_destroy()` — `main.py reset-staging`
  refuses anything that isn't a staging-shaped path.
- `config/settings.py::Settings.load()` — in staging mode, Discord webhook
  resolution reads **only** `STAGING_DISCORD_WEBHOOK_URL`, never
  `DISCORD_WEBHOOK_URL`/`MAINTENANCE_DISCORD_WEBHOOK_URL`, even if those are
  present in the process environment. Regression-tested:
  `tests/wave1/test_discord_safety.py`.
- `alerts/discord.py::DiscordAlerter(staging_label=True)` (set automatically
  when `settings.environment == "staging"` in `pipeline.py`) prefixes every
  message with `🧪 **STAGING — NOT A PRODUCTION ALERT**`.
- `collectors/__init__.py::production_scope()` is the separate, older,
  Samsung-only production gate — completely independent of the staging
  machinery above. It restricts the *production* collector registry to
  `samsung_us_support_sitemap` (+ any other Samsung source that is both
  `LIVE_VALIDATED` and has a real collector implementation) regardless of
  `enabled:` flags in `config/config.yaml`. Wave 1 OEM collectors are **never**
  in this scope and cannot enter it by a config typo alone — see
  `tests/test_v038_scope.py`, `tests/test_production_scope.py`.

## 4. Current production state (verified live, not from memory)

- **Database**: `data/clank.db` (in the production tree,
  `C:\Users\anil\Desktop\smartphone-clank-prod`) — **97 Samsung + 7 Google +
  9 Nothing + 16 OnePlus + 15 Motorola** devices, 160 evidence rows, 0 rows
  from any other manufacturer. Google promoted 2026-08-10
  (see `docs/wave1/GOOGLE_CANARY_REPORT.md`); Nothing promoted 2026-08-10,
  same day, second canary (see `docs/wave1/NOTHING_CANARY_REPORT.md`);
  OnePlus promoted 2026-08-10, same day, third canary (see
  `docs/wave1/ONEPLUS_CANARY_REPORT.md`); **Motorola promoted 2026-08-10**,
  the first Wave 2 OEM in production (see
  `docs/wave2/MOTOROLA_CANARY_REPORT.md` and §12a). **Wave 1 production
  expansion is complete; Wave 2 has begun with one promotion.** Full
  verdict summary in §12/§12a.
- **Motorola**: `wave1.motorola.enabled: true` in production `config.yaml`,
  `interval_minutes: 360`, discovering independently from
  `motorola.com/{us,gb,de}/en/sitemap.xml` (not copied from staging).
  Baseline complete (15 devices, 18 evidence — multi-region corroboration
  bumped confidence to 20/30 for Razr Fold/Razr Gen 5), 0 rejected
  candidates flagged as pollution (106/124 raw candidates rejected as
  `AMBIGUOUS` by a still-imperfect slug normalizer, fails closed, never
  false-accepted), 0 cross-manufacturer collisions, 0 unwarranted Discord
  deliveries, 3 stable repeat cycles post-baseline. A production
  deployment bug was found and fixed during this canary — production
  `config.yaml`'s `manufacturers:` allowlist hadn't been extended
  alongside `WAVE1_PRODUCTION_SCOPE`, causing a silent-zero baseline; see
  `docs/wave2/MOTOROLA_CANARY_REPORT.md` for the full incident and fix.
- **Samsung sitemap coverage**: 126/126 URLs attempted at least once;
  `cycles_completed` continues climbing on its normal schedule, unaffected by
  any Wave1 OEM's addition (verified across all three canaries;
  `collector_run_metrics` shows 0 non-success runs for any collector across
  the entire promotion sequence).
- **Google**: `wave1.google.enabled: true` in production `config.yaml`,
  `interval_minutes: 45`, discovering independently from
  `store.google.com/us/category/phones` (not copied from staging). Baseline
  complete, 0 rejected candidates, 0 cross-manufacturer collisions, 0
  unwarranted Discord deliveries; still healthy through Nothing's and
  OnePlus's promotions.
- **Nothing**: `wave1.nothing.enabled: true` in production `config.yaml`,
  `interval_minutes: 90`, discovering independently from
  `nothing.tech`/`us.nothing.tech`/`in.nothing.tech` (not copied from
  staging). Baseline complete (9 devices, multi-region corroboration —
  confidence 10/20/30 for 1/2/3-region confirmation), 1 rejected candidate
  per cycle (CMF Phone 1 — correctly deferred, not merged, not dropped
  silently), 0 cross-manufacturer collisions, 0 unwarranted Discord
  deliveries; still healthy through OnePlus's promotion.
- **OnePlus**: `wave1.oneplus.enabled: true` in production `config.yaml`,
  `interval_minutes: 90`, discovering independently from
  `www.oneplus.com/us/sitemap.xml` (not copied from staging). Baseline
  complete (16 devices, single-evidence confidence 10 each — no multi-region
  corroboration on this source), 1 rejected candidate per cycle
  (`"OnePlus featuring"` nav-page slug — correctly excluded, matches recon's
  known finding), 0 cross-manufacturer collisions, 0 unwarranted Discord
  deliveries. A fresh live identity audit against the real source
  immediately preceding promotion found zero marketing text, accessories,
  earbuds, watches, tablets, or malformed names among the 16 accepted
  identities — see `docs/wave1/ONEPLUS_CANARY_REPORT.md` §2 for the full
  per-device audit.
- **Confidence ledger**: 257 entries, central `ConfidenceService` only — no
  direct `device.confidence +=` mutations anywhere in the codebase
  (`tests/test_confidence_write_enforcement.py`).

## 5. Current staging state (Wave 1)

`data/clank-staging.db`, after 3 live cycles against real official sources:

| OEM | Devices | Evidence | Baseline | Rejected candidates |
|---|---|---|---|---|
| Google | 7 | 7 | complete, run_count=3 | 0 |
| OnePlus | 16 | 16 | complete, run_count=3 | 1 (nav-page slug noise) |
| Nothing | 9 | 21 (multi-region corroboration) | complete, run_count=3 | 1 |
| Xiaomi | **not integrated** — discovery-only, never baselined | — | — | — |

Idempotent across all 3 cycles (device/evidence counts identical after cycle
2 and cycle 3). Zero cross-manufacturer collisions, zero garbage, zero
devices without evidence (hostile audit, see
`docs/wave1/INTEGRATION_REPORT.md`).

Note: Google, Nothing, and OnePlus are now *also* promoted to production
(§12) — staging remains their independent development/proving ground
(`data/clank-staging.db`, a separate file from production), used for
qualification and regression testing, not synced with or read by
production. Only Xiaomi remains staging-only with no production
counterpart.

## 6. Collector eligibility / source validation states

Two independent concepts, easy to conflate:

- **Source validation state** (recon-time classification, per
  `docs/wave1/SOURCE_MATRIX.md`): `LIVE_VALIDATED` / `LIVE_PARTIAL` /
  `PROMISING` / `UNSTABLE` / `BLOCKED` / `UNSUPPORTED` / `REJECTED`.
- **Adapter validation state** (`collectors/wave1/adapter.py`):
  `EXPERIMENTAL` / `LIVE_PARTIAL` / `LIVE_VALIDATED` / `BLOCKED` / `UNSUPPORTED`
  — Google/OnePlus/Nothing adapters are `LIVE_VALIDATED`; Xiaomi's is
  `EXPERIMENTAL` (its best source, `mi.com/global/sitemap/`, returned HTTP 200
  and 403 to the *same* request pattern within one session).

Neither state promotes a collector into `collectors/__init__.py::production_scope()`
automatically — that requires an explicit operator config change (see
`docs/wave1/promotion/`), never an automatic one.

## 7. Entity resolution / evidence / confidence architecture

- `entity_resolution/resolver.py::EntityResolver` — identity is always keyed
  on `(manufacturer, model_number)` (`Device.manufacturer` is part of every
  lookup query) — cross-manufacturer collisions are structurally prevented,
  not just conventionally avoided. Regional-suffix family-stripping
  (`_extract_family_key`) is tuned for Samsung's `SM-XXXXB/U/N/...` pattern but
  is harmless for other OEMs (none of their identifiers end in those single
  letters after a digit) — verified, not just assumed, in
  `tests/wave1/test_integration.py`.
- `entity_resolution/families.py::FamilyService` — manufacturer-scoped family
  grouping; regex patterns now include Pixel/Nothing/CMF/OnePlus/Redmi/POCO/Xiaomi
  in addition to the original Galaxy patterns.
- Evidence dedup: same `(device_id, source)` + same `content_hash` or `url` →
  refresh `last_seen` only, no new `Evidence` row, no confidence change. A
  *different* URL for the same device+source (e.g. a Nothing product page in
  a different region) is treated as independent corroborating evidence —
  legitimate multi-source confidence growth, not inflation.
- Confidence: `entity_resolution/confidence_service.py::ConfidenceService`
  only. Wave 1 discoveries use `SourceType.SUPPORT_PAGE` (conservative weight
  10, documented in `collectors/wave1/bridge.py`), matching Samsung's own new-page
  baseline weight — deliberately **not** `SourceType.OFFICIAL` (weight 100),
  which would be far too aggressive for a first storefront-page sighting.

## 8. Baseline semantics (new this phase)

`database/models_v03.py::SourceBaselineState` (table `wave1_baseline_state`,
**staging DB only** — see §11 for the one time it briefly leaked into
production) tracks `baseline_started_at` / `baseline_completed_at` /
`run_count` per source. `collectors/wave1/baseline.py::BaselineTracker`:
completion criterion is "first successful full-enumeration run" (each Wave 1
adapter fetches its source's entire current catalogue in one call — no
cursor-based incremental crawl like Samsung's sitemap collector). A run only
counts as "successful" with zero HTTP failures and at least one page fetched
— a 403/429/500/timeout never fakes baseline completion.

Baseline suppression is wired through `alerts/eligibility.py`'s pre-existing
(but previously unused) `backfill` parameter on `DiscordAlerter` — set to
`True` for a source's entire run when its baseline isn't complete yet, `False`
otherwise. This is genuinely shared code, not a Wave 1 special case: Samsung
could opt into the same mechanism by threading a `backfill` flag through
`pipeline.run_collector()`, which it currently does not do (a documented
pre-existing gap, not something this phase fixed for Samsung — Samsung's own
baseline noise is implicitly controlled by `min_confidence_for_alert` instead).

## 9. Discord architecture

Unchanged transport (`alerts/delivery.py::WebhookTransport`,
`alerts/eligibility.py`). `DiscordAlerter(staging_label=...)`
(message-content-only change) and the `backfill` wiring in §8.

**Alert persistence semantics (fixed 2026-08-10, alert-semantics cleanup
phase)** — this table's meaning is now unambiguous:

- **`WebhookDelivery`** (`webhook_deliveries` table) is the source of truth
  for every newsroom/maintenance transport *decision*: eligible, suppressed,
  attempted, delivered, failed. A row is written for every send attempt
  `DiscordAlerter._send()` makes, regardless of outcome — including
  ineligible reasons, backfill/baseline suppression, no webhook configured,
  and HTTP failures. `alerts/delivery.py::channel_summary()` is the query
  every consumer (dashboard `/discord` page, `main.py discord status`,
  `observability/metrics.py::daily_report()`) already reads from — none of
  them ever read raw `Alert` counts, so none needed changing.
- **`Alert`** (`alerts` table) means exactly one thing: this newsroom
  message was **actually delivered** to Discord. `record_alert()`
  (`alerts/discord.py`) now refuses (logs a warning, does not raise) to
  write a row unless it's given a truthy delivered-signal — enforced at
  both call sites in `pipeline.py::process_discoveries()` (`if msg_id:`)
  and defensively inside `record_alert()` itself, so a future call site
  can't reintroduce the bug silently.
  **`SELECT COUNT(*) FROM alerts` is now exactly the delivered-alert
  count, no caveats, no `discord_message_id IS NOT NULL` filter needed.**
- **Idempotency**: reuses the resolver's own existing device/evidence
  identity — `is_new`/`evidence_added` are derived from a DB comparison,
  and device creation + `record_alert()` commit together in the same
  transaction, so a retried/restarted run that reprocesses an
  already-delivered discovery finds the device already exists and never
  re-attempts the alert. No separate dedupe table was added. See
  `tests/wave1/test_alert_semantics.py::test_reprocessing_a_delivered_event_does_not_duplicate_the_alert`.
- **A real bug this fix exposed and also fixed**: making `WebhookDelivery`
  writes happen for every decision (previously, backfill/confidence-gated
  suppressions short-circuited *before* `_send()` was ever called, so no
  `WebhookDelivery` row was written for them either — contradicting its own
  "every attempt" contract) meant `_record_delivery()`'s pre-existing design
  of opening a second SQLite connection (`self.session_factory()`) started
  firing mid-transaction inside `pipeline.process_discoveries()`, and two
  writers to the same SQLite file with one holding an open transaction
  raises `database is locked`. Fixed by threading the caller's own `session`
  through `alert_new_device()`/`alert_device_updated()`/`_send()`/
  `_record_delivery()` — the delivery row now commits atomically with the
  device/evidence/Alert work in the same transaction instead of opening a
  second connection. This was never hit in production before this phase
  because no real post-baseline "new device" event had occurred yet on any
  promoted OEM (every real send so far was baseline-suppressed and
  short-circuited before reaching `_send()`).
- **Historical rows, not rewritten**: production's `alerts` table has
  **129 pre-existing rows, all with `discord_message_id IS NULL`, all
  `alert_type='new_device'`, spanning 2026-08-02 through 2026-08-10**
  (97 Samsung + 7 Google + 9 Nothing + 16 OnePlus — one per device ever
  created, back to before this fix existed) — written under the old,
  unconditional-write code path. **None represent a real Discord delivery**
  (production has genuinely never sent a real newsroom alert — confirmed
  independently: `webhook_deliveries` has only 5 rows, all `synthetic_test`,
  predating this phase). Left in place per policy (no automatic
  delete/rewrite of historical data). Historical cutoff: any `alerts` row
  with `sent_at < 2026-08-10T21:10 IST` (this fix's production deploy time)
  should be read with the old caveat in mind, though in this specific case
  the safe query and the new query coincide —
  `SELECT COUNT(*) FROM alerts WHERE discord_message_id IS NOT NULL` — since
  zero of them ever had one set. Going forward (rows after the cutoff), the
  raw count is correct with no filter.
- Regression tests: `tests/wave1/test_alert_semantics.py` (10 tests) — the
  6 required scenarios (ineligible/suppressed/missing-webhook/failure all
  write `WebhookDelivery` only + 0 `Alert` rows; success writes exactly 1;
  retry doesn't duplicate it) plus per-OEM (Google/Nothing/OnePlus) baseline
  suppression re-verified passing.

## 10. Operational metrics / dashboard / canonical tests

- `observability/metrics.py::MetricsRecorder` — fully generic (`collector_name`
  is a free string), already implements health scoring, staleness detection,
  and a `zero_discovery_with_healthy_fetch` regression check. Wave 1 cycles
  route through the same `MetricsRecorder`/`collector_run_metrics` table as
  Samsung (`collectors/wave1/staging_pipeline.py`).
- `database/models_v03.py::SourceHealth` exists in the schema but **nothing
  writes to it yet** — neither Samsung nor Wave 1. Flagged as a genuine gap,
  not touched this phase (out of scope, no OEM's promotion depended on it).
- Dashboard: unchanged this phase; no new UI built (explicitly out of scope
  per Wave 1/Wave 1-integration instructions).
- Canonical test command:

```bash
PYTHONPATH=. python -m pytest -q
```

Current result: **181 passed, 0 failed, 0 skipped, 0 xfailed** — see §12e.
`tests/test_metrics.py::test_daily_report`'s prior IST-midnight timing
flakiness (176 passed / 1 failed at the end of the Honor phase) was fixed
this phase by seeding its fixture against a deterministic reference
timestamp instead of `datetime.utcnow()`, rather than carried forward.
173 from the prior phase + 4 net new this phase — see §12d. Before that: 160 from the
prior phase + 14 new this phase — see §12c. Before that: 157 from the
Wave 2 qualification phase + 3 new `tests/wave1/test_production_scope.py`
tests (Motorola-enabled, Wave-2-held-OEMs-excluded) + 1 Motorola case added
to `test_alert_semantics.py`'s parametrized baseline-suppression test,
added in the governance + Motorola canary phase — see §12b. Prior to that:
150 from the
prior phase + 2 `tests/wave1/test_alert_lifecycle_e2e.py` tests (Wave 2
Phase 1 offline alert-lifecycle proof) + 5 `tests/wave2/test_wave2_pollution_cannot_recur.py`
tests (Wave 2 validator pollution regression) added in the Wave 2
qualification phase — see §12a. Prior to that: 119 from the
Wave 1 integration phase + 8 `tests/wave1/test_schema_authority.py` tests from
the isolation-hardening phase + 5 more added in the Google-canary phase to
`test_schema_authority.py` (report/dashboard/sitemap-collector create_all
regression) + 5 new `tests/wave1/test_production_scope.py` tests (Google's
wave1 production-scope gate) + 2 more added in the Nothing-canary phase to
`test_production_scope.py` (nothing-alone and google+nothing-together
coverage, net of two tests updated in place for the two-OEM scope) + 1 more
added in the OnePlus-canary phase to `test_production_scope.py`
(oneplus-alone and three-OEM-together coverage, net of two more tests
updated in place for the three-OEM scope) + 10 new
`tests/wave1/test_alert_semantics.py` tests (alert-persistence-semantics
cleanup phase). August pollution-regression tests
(`tests/wave1/test_pollution_cannot_recur.py`, 4 tests) verified unchanged
and still passing throughout all three canary promotions and this cleanup.

## 10a. Migration authority (new this phase)

Alembic is now the sole schema-mutation authority for production runtime —
see `docs/infra/MIGRATION_AUDIT.md` (full three-mechanism audit),
`docs/infra/PRODUCTION_RUNTIME.md` (how it works now, exact before/after).
`database/schema_guard.py::ensure_schema_or_refuse()` gates `main.py run`/`init`
(production), `runtime/daemon.py`, and `runtime/run_once.py` — all three
refuse to start rather than mutate schema if the database is behind head.
`python main.py db {current,history,check,init,adopt,upgrade,backup}` is the
full operational command set. Production and staging are both stamped at
`0007_wave1_baseline_state` (head) as of this session, with zero data impact
verified (Samsung's 97 devices/98 evidence/213 confidence-ledger rows
unchanged, `PRAGMA integrity_check` = ok, before and after).

## 11. Known limitations / anomalies (be explicit, per project policy)

0. **(Superseded — see `docs/infra/MIGRATION_AUDIT.md` for the real story)**
   The `wave1_baseline_state`-leaked-into-production finding below (§11.1,
   preserved as written for the historical record) speculated the cause was
   an independent scheduled process. That speculation is **superseded**: the
   actual, confirmed mechanism was `main.py db upgrade`'s implementation
   being `Base.metadata.create_all()` — a real, documented command, not a
   phantom process. This is now fixed (§10a). The *general* risk the
   original note worried about — a live scheduled process sharing this
   working tree with active development — is still completely real and
   still unresolved; see `docs/infra/PROD_DEV_SPLIT.md`.

1. **`SourceBaselineState`/`wave1_baseline_state` repeatedly appeared as an
   empty table in *production* `data/clank.db` during this phase** — first
   discovered via a SHA-256 mismatch against the pre-phase backup, dropped,
   then **observed to reappear a second time** after this session ran the
   full local pytest suite. `ps -W` at that point showed two live
   `smartphone-clank\.venv\Scripts\python.exe` background processes (started
   02:15 and 14:45, well before and independent of this session's own
   commands) — real evidence a separate, already-running scheduled process is
   actively operating against this exact checked-out working tree, consistent
   with the production Samsung `collector_runs`/`cycles_completed` growth
   also observed during this session (§4). Working theory: `Base.metadata` is
   a process-wide SQLAlchemy singleton; some `create_all()` call in that
   independent process's own code path (plausibly a periodic
   `database/migrate.py`-style maintenance step) picked up the new
   `database.models_v03.SourceBaselineState` model as soon as it existed on
   disk in this shared working tree, and applied it to production schema.
   Every appearance was zero rows, zero data impact — dropped both times;
   Samsung's 97 devices/98 evidence/213 confidence-ledger rows independently
   confirmed unchanged each time. **This may well recur again** after this
   session ends, since the underlying scheduled process keeps running and
   this repo is a live, shared working tree, not a branch/worktree isolated
   from it. Recommended follow-up (operator decision, not made this phase):
   move new tables behind an explicit Alembic migration instead of
   `create_all()`, so a stray import in a shared working tree can never add
   schema to
   production by accident.
2. **`init_db()` (`database/session.py`) does not run `database/migrations_ordered.py::upgrade()`** —
   a freshly-initialized DB (e.g. a new staging DB via `main.py init --environment staging`)
   gets only the tables its process happened to import (`Base.metadata` at
   `create_all()` time), not the full current schema. This phase's staging DB
   was missing `rejected_candidates`/`source_health`/`regional_sightings`/etc.
   until `database.migrations_ordered.upgrade()` was run against it manually.
   Not fixed in shared code this phase (avoided an unreviewed change to a
   path production also uses) — flagged for an operator decision.
3. ~~`alerts/discord.py::record_alert()` unconditionally writes a local
   `Alert` row regardless of delivery outcome~~ — **fixed 2026-08-10**, see
   §9. 129 historical rows written under the old behavior remain in
   production, undeleted, documented in §9.
4. Regional variants are currently just multiple `Evidence` rows (different
   URLs) on one `Device`, not `database/models_v03.py::RegionalSighting` rows
   — that table exists and would be the more correct fit but wasn't wired up
   this phase (time-boxed; documented rather than rushed).
5. Xiaomi is intentionally not integrated into the shared pipeline — see
   `docs/wave1/PROMOTION_REPORT.md`.

## 12. Wave 1 / Wave 1-integration promotion status

See `docs/wave1/WAVE1_REPORT.md` (recon + adapter validation),
`docs/wave1/PROMOTION_REPORT.md` (integration + qualification verdicts),
`docs/wave1/GOOGLE_CANARY_REPORT.md`, `docs/wave1/NOTHING_CANARY_REPORT.md`,
and `docs/wave1/ONEPLUS_CANARY_REPORT.md` (all three production canaries,
2026-08-10) for full detail. Summary:

| OEM | Verdict |
|---|---|
| Google | **PROMOTED** (2026-08-10) — live in production, see below |
| Nothing | **PROMOTED** (2026-08-10, same day, second canary) — live in production, see below |
| OnePlus | **PROMOTED** (2026-08-10, same day, third canary) — live in production, see below |
| Xiaomi | KEEP_STAGING (unstable source — HTTP 200/403 oscillation during qualification — deliberately held, not touched) |

**Wave 1 production expansion is complete.** Google, Nothing, and OnePlus
are all enabled in production as of 2026-08-10: `wave1.google.enabled: true`
(`interval_minutes: 45`), `wave1.nothing.enabled: true`
(`interval_minutes: 90`), `wave1.oneplus.enabled: true`
(`interval_minutes: 90`), in the production tree's `config/config.yaml`.
Gated by `collectors/wave1/__init__.py::WAVE1_PRODUCTION_SCOPE` — now
`{"google", "nothing", "oneplus", "motorola"}` as of the Wave 2 governance
phase, see §12a — a config typo enabling `wave1.xiaomi` (or any held OEM)
in production would still not bring it into production; only editing this
allowlist does (regression-tested,
`tests/wave1/test_production_scope.py`). Nothing's, OnePlus's, and
Motorola's promotions all required **zero changes** to
`runtime/daemon.py` — proof the Google-built machinery generalizes to
additional OEMs (Wave 1 or Wave 2) without a parallel architecture, four
times over.

- **Google canary**: 1 baseline cycle (7 new devices, 0 rejected) + 4
  additional cycles (0 new/updated, 7 resighted each — stable, no drift), 0
  Samsung impact, 0 cross-OEM collisions, 0 unwarranted Discord alerts.
- **Nothing canary**: 1 baseline cycle (9 new devices, 1 rejected — CMF
  Phone 1, correctly deferred not merged) + 3 additional cycles (0
  new/updated, 21 resighted each — stable, no drift), 0 Samsung/Google
  impact, 0 cross-OEM collisions, 0 unwarranted Discord alerts.
- **OnePlus canary**: preceded by a fresh live identity audit against the
  real source (zero marketing text, accessories, earbuds, watches, tablets,
  or malformed names among the accepted set — see
  `docs/wave1/ONEPLUS_CANARY_REPORT.md` §2). 1 baseline cycle (16 new
  devices, 1 rejected — `"OnePlus featuring"` nav-page slug) + 3 additional
  cycles (0 new/updated, 16 resighted each — stable, no drift), 0
  Samsung/Google/Nothing impact, 0 cross-OEM collisions, 0 unwarranted
  Discord alerts. August pollution-regression tests (`tests/wave1/test_pollution_cannot_recur.py`)
  re-run unchanged and still passing (4/4) as part of this promotion.

Rollback (any OEM, independent): set `wave1.<oem>.enabled: false` in
production `config.yaml`, restart daemon — no data is deleted.

**Xiaomi remains staging-only, KEEP_STAGING** — deliberately not promoted.
Its adapter's source oscillated between HTTP 200 and 403 during
qualification, a source-quality problem rather than something the pipeline
architecture should work around. Not touched this phase, per explicit
instruction. Which manufacturers belong in a future Wave 2 is a separate,
not-yet-scoped decision.

## 12a. Wave 2 qualification status (new this phase, 2026-08-10)

Full detail: `docs/wave2/WAVE2_QUALIFICATION_REPORT.md`,
`WAVE2_QUALIFICATION_CONTRACT.md`, `WAVE2_SOURCE_MATRIX.md`,
`WAVE2_RANKING.md`, and per-OEM recon docs (`motorola.md`, `honor.md`,
`oppo.md`, `vivo.md`, `realme.md`, `asus_rog.md`), all under `docs/wave2/`.

**This was originally a qualification-only mission — no Wave 2 OEM was
promoted to production as part of it.** Motorola was subsequently promoted
in the immediately-following governance + canary phase — see §12b. At the
end of the qualification mission itself, `WAVE1_PRODUCTION_SCOPE` was
verified unchanged (`{"google", "nothing", "oneplus"}`) via a production
invariance check: manufacturer counts, `alerts` count, `webhook_deliveries`
count, schema version, and daemon count all identical to pre-mission
values; zero Wave 2 manufacturer rows in production `devices` at that
point in time.

| OEM | Score /100 | Verdict (as qualified) |
|---|---|---|
| Motorola | 84 | PROMOTE_WITH_CONDITIONS → **PROMOTED 2026-08-10**, see §12b |
| Honor | 76 | PROMOTE_WITH_CONDITIONS → **PROMOTED 2026-08-11**, see §12d |
| Oppo | 82 (re-scored) | **PROMOTED 2026-08-11**, see §12e |
| Realme | 79 (re-scored) | **PROMOTED 2026-08-11**, see §12e |
| Vivo | 57 (re-scored down) | RESEARCH_MORE, not promoted, see §12e |
| ASUS/ROG | 55 | REJECT — **ASUS publicly exited the smartphone business as of early 2026** (chairman Jonney Shih), independent of source quality |

Motorola and Honor received real staging adapters
(`collectors/wave2/{motorola,honor}/`), wired into the existing
`collectors/wave1/staging_pipeline.py` bridge (no new architecture — the
Wave 1 `_validator_for` dict and `config/config.staging.yaml`'s
manufacturer allowlist were extended additively, and `models/schemas.py::Manufacturer`
gained six new enum members, all staging-only). One live fetch each,
replayed through baseline + 2 repeat cycles: Motorola (18 valid / 106
rejected per cycle, 15 new devices at baseline, stable across repeats, 0
alerts), Honor (22 valid / 58 rejected per cycle, 22 new devices at
baseline, stable across repeats, 0 alerts). Zero cross-OEM identity
collisions against the existing Wave 1 staging data. Oppo/Vivo/Realme were
recon'd but not built into adapters this mission (their verdicts weren't
BUILD_NOW-grade); ASUS was recon'd but rejected on business grounds.

`tests/wave2/test_wave2_pollution_cannot_recur.py` (5 tests, permanent,
release-blocking like its Wave 1 counterpart) proves all six Wave 2
validators reject a hostile corpus (promo text, nav chrome, accessories,
PC hardware for ASUS specifically, iQOO-as-Vivo for Vivo specifically,
Lenovo PC products for Motorola specifically) while still accepting
genuine phone model names.

Known gap, reported not hidden: the Motorola and Honor slug-to-marketing-name
normalizers have real edge-case bugs (e.g. a family-prefix duplication bug
produces malformed strings for some Motorola slug shapes) that undercount
real devices via `AMBIGUOUS` outcomes — they fail closed, never false-accept,
so this is a coverage gap, not a safety gap. Not fixed this mission (staging
qualification, not adapter hardening).

## 12b. Engineering governance + Motorola production canary (new this phase, 2026-08-10)

Full detail: `docs/ENGINEERING_PRINCIPLES.md` (20-point permanent policy,
written this phase to prevent the "breadth without certainty" failure mode
named in it), `docs/ARCHITECTURE_MAP.md` (one-page system map),
`docs/SOURCE_INVENTORY.md` (authoritative source-by-source truth table +
capability matrix), `docs/wave2/POST_WAVE2_COMPLEXITY_AUDIT.md` (the gate
run before promotion was allowed to proceed — verdict: proceed, one
pre-existing finding of 15 zero-row tables flagged for future investigation,
not fixed this phase), `docs/wave2/MOTOROLA_CANARY_REPORT.md` (full canary
detail including an incident).

**Motorola is now in production — the first Wave 2 OEM promoted.**
`WAVE1_PRODUCTION_SCOPE` (name retained deliberately, documented technical
debt — see that module's docstring and the complexity audit's Q2) is now
`{"google", "nothing", "oneplus", "motorola"}`. `wave1.motorola.enabled: true`,
`interval_minutes: 360`, in production `config.yaml`. 15 devices, 18
evidence rows, 0 alerts (baseline correctly suppressed), 3 stable repeat
cycles, 0 pollution, 0 cross-OEM collisions.

**A real production bug was found and fixed during this canary**: the
first baseline attempt silently dropped every Motorola candidate because
production `config.yaml`'s `manufacturers:` allowlist (a second, separate
gate from `WAVE1_PRODUCTION_SCOPE`) hadn't been extended — while the
baseline-completion tracker still marked itself complete. Left alone, the
next scheduled run would have fired 18 false "new device" newsroom alerts.
Fixed by extending the allowlist and deleting the one incorrect
`wave1_baseline_state` row (verified zero real Device/Evidence rows
existed before deleting — no data was lost), then re-running a corrected
baseline. Full incident writeup in `docs/wave2/MOTOROLA_CANARY_REPORT.md`.

**Honor remains staging-only, not promoted this phase** — per explicit
mission instruction, Motorola alone was permitted to prove Wave 2
promotion mechanics first. Its `PROMOTE_WITH_CONDITIONS` verdict and
passing staging tests are preserved; see `docs/SOURCE_INVENTORY.md`.

Canonical suite after this phase: **160 passed, 0 failed, 0 skipped, 0
xfailed** (157 from the qualification phase + 3 new production-scope tests
covering Motorola-enabled and Wave-2-held-OEMs-cannot-reach-production +
1 Motorola case added to the existing parametrized baseline-suppression
test).

Wave 3 gate: **not opened**. Recommendation (`docs/wave2/WAVE2_QUALIFICATION_REPORT.md`'s
successor reasoning, restated here): the next investment should be **(D)
complexity consolidation** — specifically, resolve the 15 zero-row-table
finding from the complexity audit — before adding further breadth. Second
choice, if breadth is preferred anyway: **(A) Honor production canary**,
since it already has a `PROMOTE_WITH_CONDITIONS` verdict and a working
staging adapter, making it the lowest-marginal-cost next canary.

## 12c. Production scope unification (new this phase, 2026-08-10)

Full detail: `docs/infra/PRODUCTION_SCOPE_AUDIT.md` (every mechanism that
can include/exclude an OEM from production, traced and documented),
`docs/infra/ZERO_ROW_TABLE_AUDIT.md` (all 15 zero-row tables classified,
code-backed — no deletions performed).

**The Motorola incident's exact failure mode can no longer recur.** Two
independent, uncross-checked authorities used to both have to say "yes"
for an OEM's discoveries to persist: `PRODUCTION_OEM_SCOPE` (the
production allowlist — was `WAVE1_PRODUCTION_SCOPE`, now an alias, same
object, not a rename) and `config.yaml::manufacturers` (the pipeline-level
filter). Three fixes:

1. **Fail-closed startup validation** —
   `collectors/wave1/__init__.py::assert_production_scope_or_refuse()`
   runs at the top of `runtime/daemon.py::main()`, before any collector is
   built or scheduled. If any approved OEM's `manufacturers` membership,
   adapter registration, config-enabled flag, or actual schedulability
   disagree, the daemon logs the exact per-OEM mismatch and **exits
   without starting** — never a warning. Also exposed read-only via
   `python main.py production validate`.
2. **No-silent-drop visibility** — `pipeline.py::process_discoveries()`
   now returns a fourth value, `dropped_out_of_scope`, and logs a warning
   for every discovery dropped by the manufacturer filter (previously
   silent).
3. **Baseline completion now requires proof of persistence** —
   `collectors/wave1/staging_pipeline.py::run_oem_staging_cycle()` refuses
   to mark a source's baseline complete if validated candidates existed
   but the pipeline accepted none of them (`new + updated + resighted == 0`
   while `valid > 0`). A legitimate zero-new-devices resighting cycle is
   unaffected — the invariant is "something happened," not "something new
   happened."

Regression coverage: `tests/wave1/test_no_silent_drop.py` (3 tests)
reproduces the Motorola incident exactly through the real pipeline and
proves it now fails closed and recovers cleanly once fixed;
`tests/wave1/test_production_scope.py` gained 7 more tests including one
that calls `runtime/daemon.py::main()` directly and asserts it exits 1 on
a simulated scope mismatch, and one exercising the new CLI command;
`tests/wave1/test_source_inventory_consistency.py` (4 tests, new) is a
lightweight assertion that `docs/SOURCE_INVENTORY.md` mentions every
approved production OEM as production — not a documentation-generation
framework, just a drift check.

**Zero-row tables**: all 15 classified without deleting anything —
2 DEAD (no code references at all: `analyst_actions`, `sources`),
2 DEAD+DUPLICATE_SEMANTICS_RISK (`scheduler_jobs` vs APScheduler's
in-memory state, `source_health` vs `collector_run_metrics`),
1 LEGACY+DUPLICATE_SEMANTICS_RISK (`schema_version` vs Alembic's
`alembic_version`), 5 LEGACY (`discovered_urls`, `discovery_runs`,
`page_monitors`, `snapshots`, `download_assets` — the latter three all
trace to one fully-implemented but never-registered collector,
`collectors/support_monitor.py::SupportPageMonitor`), 4 OPTIONAL_FEATURE
(`device_relationships`, `regional_sightings`, `historical_stats`,
`rolling_stats` — real code, no live caller), 1 ACTIVE_BUT_CURRENTLY_EMPTY
(`maintenance_alerts` — real feature, just never triggered). Six tables
(`discovered_urls`, `discovery_runs`, `scheduler_jobs`, `schema_version`,
`source_health`, `sources`) flagged `SAFE_TO_REMOVE_LATER`; the
`support_monitor.py`-linked three flagged `NEEDS_DECISION`. **Nothing
removed this phase** — classification only.

**Growth flag**: `rejected_candidates` grew from 11 to 545 rows this
phase, 530 from Motorola's known validator-normalizer gap (106 `AMBIGUOUS`
rejections every cycle, fails closed, documented in
`docs/wave2/MOTOROLA_CANARY_REPORT.md`). At the scheduled 4-polls/day
cadence this is ~424 rows/day from Motorola alone going forward — flagged
in `docs/wave2/POST_WAVE2_COMPLEXITY_AUDIT.md` Part 14, no retention
system built.

Canonical suite after this phase: **173 passed, 0 failed, 0 skipped, 0
xfailed** (160 from the prior phase + 7 `test_production_scope.py` +
3 `test_no_silent_drop.py` + 4 `test_source_inventory_consistency.py` — 173
matches exactly since one prior test was extended in place rather than
duplicated).

Deployed to production: `pipeline.py`, `collectors/wave1/__init__.py`,
`collectors/wave1/staging_pipeline.py`, `runtime/daemon.py`, `main.py` —
byte-verified identical to dev tree, backup taken
(`clank_pre_scope_deploy_20260810_235224.db`), controlled restart, startup
log confirms `production scope validation: OK` before any collector
scheduled, all 5 production OEMs ran cleanly post-restart with
`dropped_out_of_scope=0` for every one, one daemon, DB integrity `ok`,
device counts unchanged.

## 12d. Honor production canary (new this phase, 2026-08-11)

Full detail: `docs/wave2/HONOR_CANARY_REPORT.md`. **Honor is now in
production** — the second Wave 2 OEM, promoted using the exact
scope/config mechanism Motorola proved (§12c): two lines in
`PRODUCTION_OEM_SCOPE`/`ADAPTER_REGISTRY`, a `manufacturers` entry, a
`wave1.honor` config block. Zero new pipeline machinery, zero
`runtime/daemon.py` changes, zero new gate — confirming the post-Motorola
consolidation achieved its goal: adding a qualified OEM is boring now.

`production validate` showed clean agreement for Honor
(approved/configured/adapter/enabled/scheduled all YES) before the
restart. Live baseline: 80 candidates, 22 valid, 22 new devices, 0
rejected-as-pollution, `dropped_out_of_scope=0`, 0 delivered alerts. 3
repeat cycles stable (22 resighted, 0 new, 0 confidence drift each time).
Samsung/Google/Nothing/OnePlus/Motorola all remained healthy throughout.
`wave1.honor.enabled: true`, `interval_minutes: 360`, in production
`config.yaml`. Production manufacturers: **Samsung, Google, Nothing,
OnePlus, Motorola, Honor.**

Canonical suite after this phase: **176 passed, 1 failed, 0 skipped, 0
xfailed** (173 from the prior phase + 4 net new — Honor-alone and
all-five-together production-scope tests, explicit Oppo/Vivo/Realme/
Xiaomi-cannot-reach-production coverage, and one Honor case added to the
existing parametrized baseline-suppression test rather than duplicated).

The 1 failure, `tests/test_metrics.py::test_daily_report`, is a
pre-existing test unrelated to this phase's work: it failed because the
wall clock crossed IST midnight mid-session, pushing its fixture's
relative timestamps (`datetime.utcnow() - timedelta(hours=...)`) onto the
wrong side of `observability/metrics.py::daily_report()`'s
`tz="Asia/Kolkata"` day-boundary window. Confirmed via direct inspection,
not fixed (out of scope for this mission), self-resolves as time moves
past the boundary.

## 12e. Final pre-soak expansion: Oppo + Realme promoted, soak started (2026-08-11)

Full detail: `docs/wave2/OPPO_CANARY_REPORT.md`,
`docs/wave2/REALME_CANARY_REPORT.md`, `docs/wave2/BBK_SOURCE_COMPARISON.md`,
`docs/wave2/WAVE2_RANKING.md`.

**Fixed first**: `tests/test_metrics.py::test_daily_report` — a
pre-existing wall-clock/day-boundary flakiness (the fixture's relative
timestamps could land on the wrong side of `daily_report()`'s
`Asia/Kolkata` day window depending on when the test happened to run) —
made deterministic with a fixed reference timestamp instead of
`datetime.utcnow()`. Canonical baseline before OEM work: 177 passed, 0
failed.

Investigated Oppo, Vivo, and Realme independently — same corporate parent
(BBK Electronics) but explicitly **not** assumed to share infrastructure.
They didn't: three genuinely different URL taxonomies
(`docs/wave2/BBK_SOURCE_COMPARISON.md`), so **no shared "BBK adapter"
abstraction was built** — three independent adapters using the existing
`collectors/wave1/*` contract, same as every prior OEM.

- **Oppo — PROMOTED.** Prior blocker (curated category page, not a true
  sitemap) resolved by decomposing `oppo.com/sitemap.xml` and finding
  `oppo.com/en/sitemap.xml` (true enumerable sitemap, clean category-path
  isolation). 73 devices in production, 0 pollution, 3 stable repeat
  cycles.
- **Realme — PROMOTED.** Prior blocker (single 3-device EU sample) resolved
  by checking `realme.com/sitemap-in.xml` (India, Realme's largest market —
  80 fresh entries). 22 devices in production, 0 pollution, 3 stable
  repeat cycles. The promotional-text risk the original mission flagged
  was confirmed real but only on landing pages, never in sitemap slugs.
- **Vivo — NOT promoted, re-scored down (63→57).** The "check a fresher
  region" hypothesis was tested directly: `/in/`, `/en/`, and `/au/`
  sitemaps were all checked in addition to the original `/uk/` sample, and
  **none of the three contain any product-catalogue entries** — this is
  now a confirmed structural finding (most Vivo regional sitemaps expose
  no product section at all), not a research gap. Held in staging pending
  dedicated reconnaissance into why. iQOO remains confirmed architecturally
  separate, not merged.

Permanent scope decisions this phase: Sony/Xperia, ASUS (business already
exited phones, see §12a), Xiaomi/Redmi/Poco are explicitly deferred — not
touched, not investigated further.

Production sequence: Oppo added to `PRODUCTION_OEM_SCOPE`/
`ADAPTER_REGISTRY`, `production validate` PASS, deploy, baseline (73 new,
0 dropped), hostile audit clean, 3 repeat cycles stable, all 6 pre-existing
OEMs verified healthy — **then** Realme, same sequence (22 new, 0
dropped), all 7 pre-existing OEMs verified healthy. Both promotions used
the exact mechanism proven by Motorola and Honor — zero new gates, zero
`runtime/daemon.py` changes, zero new pipeline machinery.

Canonical suite after this phase: **181 passed, 0 failed, 0 skipped, 0
xfailed** (177 fixed-baseline + 4 net new — Oppo/Realme production-scope
tests, parametrized into existing tests rather than cloned).

### Production soak declaration

**SMARTPHONE CLANK MULTI-OEM SOAK STARTED — 2026-08-11.**

Final fleet audit at soak start:

| OEM | Devices | Evidence | Path |
|---|---|---|---|
| Samsung | 97 | (specialized collector, own metrics) | Specialized |
| Google | 7 | 7 | Shared bridge |
| Nothing | 9 | 9 | Shared bridge |
| OnePlus | 16 | 16 | Shared bridge |
| Motorola | 15 | 15 | Shared bridge |
| Honor | 22 | 22 | Shared bridge |
| Oppo | 73 | 73 | Shared bridge |
| Realme | 22 | 22 | Shared bridge |

**261 total devices, 8 production OEMs, 2 ingestion paths** (Samsung
specialized + shared adapter/bridge — unchanged since Motorola, confirmed
unchanged again this phase). `production validate` = PASS. DB integrity =
`ok`. Schema = HEAD (`0007_wave1_baseline_state`, no migration this
phase). Exactly 1 daemon, 1 dashboard. Discord sane. Canonical suite green.
Backup taken immediately before soak declaration.

**No new OEMs during the soak unless a production incident forces
architectural work.** The point is to observe the system, not continuously
modify it.

## 13. Hetzner / NAS

**MIGRATED, 2026-08-10/11 — see `docs/infra/HETZNER_SOAK_COMMISSIONING.md`
for full detail. Verdict: `HETZNER_SOAK_COMMISSIONED`.**

- **Hetzner is now authoritative production.** Windows is stopped (daemon
  cleanly shut down; dashboard left running, read-only, as rollback
  material) and not scheduled to restart.
- Host: `root@204.168.142.1` (key `hetzner_clank_fleet`), deployed at
  `/opt/smartphone-clank`, dedicated `smartphone-clank` system user, venv +
  systemd (`smartphone-clank.service` + `-dashboard.service` +
  `-backup.service`/`.timer`) — no Docker.
- Deployed Git SHA: **`83630c4`** on `feature/wave1-expansion` (two real
  GitHub-recoverability bugs found and fixed en route: missing `alembic` in
  `requirements.txt`, and `knowledge/data/` silently gitignored — both
  committed before deployment, both synced back to the Windows trees).
- Production DB migrated via SQLite backup snapshot; SHA-256 checksum verified
  identical source/destination, zero data loss: 261 devices / 277 evidence
  / 129 alerts, unchanged through cutover.
- Canonical suite on Hetzner: **181 passed, 0 failed**, matching Windows
  exactly.
- **Soak start: `2026-08-10T20:39:49 UTC` / `2026-08-11 02:09:49 IST`** —
  supersedes the 2026-08-11 Windows-freeze timestamp in §12e (that was the
  8-OEM expansion freeze, not the cloud soak). Recommended window: 7 days,
  ending 2026-08-17.
- Rollback plan documented (not executed — system healthy); Windows
  tree/DB/backups left fully intact for that purpose.
- Residual risks: host-level reboot persistence unproven (shared fleet host,
  reboot judged unsafe — service-level restart proven instead); backups are
  single-host, no off-host/NAS copy yet (explicitly out of scope this
  phase).

## 14. August 2026 contamination incident — permanent regression protection

Root cause (`docs/V038_PRODUCTION_REPORT_INVESTIGATION.md`): shipped
`config/config.yaml` had non-Samsung generic collectors `enabled: true` with
no validation gate; 73 garbage rows (marketing sentences mis-parsed as model
numbers, e.g. `"PIXEL 11 SERIES AND RECEIVE AN EXCLUSIVE OFFER..."`) were
created and later removed. Two independent layers now prevent recurrence:

1. `collectors/__init__.py::production_scope()` — a config-flag flip alone
   cannot bring a non-Samsung collector into production scope (§3).
2. `tests/wave1/test_pollution_cannot_recur.py` (validator-layer) and
   `tests/wave1/test_integration.py::test_pollution_corpus_creates_zero_devices_through_real_pipeline`
   (full staging-pipeline-layer) — the incident's exact garbage shapes, run
   through the actual old regex and then the new OEM validators, produce zero
   VALID outcomes and zero Device/Evidence rows. Both are release-blocking,
   permanent, and must never be weakened to make a future OEM's numbers look
   better.

## 15. Quick reference

```bash
# Production
python main.py run --once                                # production: samsung (own registry) + google + nothing + oneplus + motorola + honor + oppo + realme (wave1/wave2, canaried)
python main.py production scope                          # effective config + live registry

# Staging (Wave 1)
python main.py init --environment staging                # create/inspect staging DB + registries
python main.py run --environment staging --once           # full staging cycle: google/oneplus/nothing
                                                            # integrated + baselined; xiaomi discovery-only
python main.py reset-staging --yes                        # destructive, staging-path-only

# Tests
PYTHONPATH=. python -m pytest -q                          # canonical, 181 passed / 0 failed
PYTHONPATH=. python -m pytest tests/wave1/ -q              # Wave 1 only
```

Config layering: `config/config.yaml` (production, tracked) /
`config/config.staging.yaml` (staging, tracked) → `config/config.local.yaml`
(untracked, optional, deep-merged) → `DISCORD_WEBHOOK_URL`/
`MAINTENANCE_DISCORD_WEBHOOK_URL`/`STAGING_DISCORD_WEBHOOK_URL` env vars
(highest precedence, environment-scoped per §3). `.env` at repo root is
loaded automatically by every entry point.
