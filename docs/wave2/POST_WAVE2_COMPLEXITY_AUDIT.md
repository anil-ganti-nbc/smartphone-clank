# Post-Wave-2 Complexity Audit

Run 2026-08-10, gating decision for the Motorola production canary in this
mission, per `docs/ENGINEERING_PRINCIPLES.md`. All counts below are measured
directly (`find`, `wc`, `pytest --collect-only`, live SQLite queries against
`smartphone-clank-prod/data/clank.db`), not estimated.

## Raw counts

| Metric | Count |
|---|---|
| Python files (excl. `.venv`, `__pycache__`) | 135 |
| Python LOC (naive line count, same scope) | 16,361 |
| Test files | 27 |
| Tests collected | 157 |
| Alembic migrations | 7 (HEAD: `0007_wave1_baseline_state`) |
| Database tables (production) | 30 |
| Tracked config files | 8 |
| Documentation files (`docs/**/*.md`) | 67 |
| Task Scheduler entries (this project) | 4 (`DailyBackup`, `DailyReport`, `HealthCheck`, `WeeklyReport`) |
| Long-running production processes | 2 (runtime daemon, dashboard server) |

## Production ingestion path map

    Samsung   -> collectors/samsung/sitemap_collector.py (specialized collector)
                 -> pipeline.IntelligencePipeline.process_discoveries()
                 -> runtime/daemon.py (dedicated scheduled job, interval_minutes from config)

    Google    -> collectors/wave1/google/discovery.py -> validator -> bridge
                 -> collectors/wave1/staging_pipeline.run_oem_staging_cycle()
                 -> pipeline.IntelligencePipeline.process_discoveries()
                 -> runtime/daemon.py (generic wave1-collector scheduling loop, shared with Nothing/OnePlus)

    Nothing   -> same shared wave1 path as Google, different adapter/validator
    OnePlus   -> same shared wave1 path as Google, different adapter/validator

**Two** distinct production ingestion paths exist: Samsung's specialized
collector (pre-dates Wave 1, never migrated — see Known limitations below)
and the shared Wave 1 adapter/bridge path that Google, Nothing, and OnePlus
all use identically. This matches the architecture goal in
`docs/ENGINEERING_PRINCIPLES.md` — not one pipeline per OEM.

Collector inventory by state:

| Directory | Adapters (discovery.py present) | Validator-only (recon/qualification, no discovery.py) |
|---|---|---|
| `collectors/samsung/` | 1 (specialized, pre-Wave-1) | — |
| `collectors/wave1/` | 4 (google, nothing, oneplus, xiaomi) | — |
| `collectors/wave2/` | 2 (motorola, honor) | 4 (oppo, vivo, realme, asus — validators built for the pollution-regression test per the qualification mission's Phase 6, never wired to a live discovery source) |

The four Wave 2 validator-only directories are correctly *not* counted as
collectors or coverage — no `discover()` method exists, so nothing could
call them from `staging_pipeline.py` even if a manufacturer entry existed.
This is Rule 3 (no fake coverage) working as intended, not an oversight.

## Answering the audit questions

### 1. Did Wave 2 introduce duplicate mechanisms?

No. Wave 2 extended three existing, singular mechanisms additively rather
than duplicating them:
- `models/schemas.py::Manufacturer` — six new enum members (Motorola,
  Honor, Oppo, Vivo, Realme, ASUS), same enum, not a second manufacturer
  concept.
- `collectors/wave1/staging_pipeline.py::_validator_for()` — two new dict
  entries, same lookup function, not a second dispatcher.
- `config/config.staging.yaml`'s `manufacturers:` allowlist — two new
  entries, same list.

No new pipeline, no new resolver, no new alert path, no new scheduler
mechanism was created for Wave 2.

### 2. Did any abstraction become substantially harder to understand?

No, with one caveat noted for the record: the `collectors/wave1/` package
name now houses Wave 2 adapters' shared infrastructure too
(`staging_pipeline.py`, `adapter.py`, `validator.py`, `common.py`,
`bridge.py`, `baseline.py` are all imported by `collectors/wave2/*`
adapters). The name "wave1" is historically accurate but no longer
precisely scoped. This is a real naming imprecision, not a functional
problem — see Rule 1's `PRODUCTION_OEM_SCOPE` question (Part D §24) for
the same tension applied to the production-scope constant specifically.
Not renamed this mission (see that section for the correctness-over-purity
reasoning).

### 3. Is dead code active-looking?

One finding, pre-existing (not introduced by Wave 2): **15 of the 30
production tables have zero rows in production** as of this audit —
`analyst_actions`, `device_relationships`, `discovered_urls`,
`discovery_runs`, `download_assets`, `historical_stats`,
`maintenance_alerts`, `page_monitors`, `regional_sightings`,
`rolling_stats`, `scheduler_jobs`, `snapshots`, `source_health`, `sources`,
`schema_version`. These are declared in `database/models.py`/
`database/models_v03.py` and therefore appear as fully active schema, but
several (`sources`, `source_health`, `scheduler_jobs`) look like they were
built for a health-reporting subsystem that isn't wired into the current
metrics path (`collector_run_metrics`/`collector_runs` are what's actually
used — see Rule 6/Rule 12 tension flagged below). This is a legitimate
audit finding, not something Wave 2 introduced, but Wave 2's own tables
(`wave1_baseline_state`, `rejected_candidates`) are actively populated (3
and 11 rows respectively) and not part of this problem.

**Recommendation, not executed this mission** (out of scope per the
"no speculative refactors" instruction): a future focused mission should
determine whether these 15 tables are (a) planned-but-unbuilt
functionality that should be finished, or (b) superseded designs that
should move to `deprecated/`/be dropped via migration. Do not guess which
without dedicated investigation.

### 4. Does configuration disagree with runtime truth?

No new disagreement found. `config/config.staging.yaml`'s manufacturer
allowlist now includes `motorola`/`honor`, both of which have real,
callable adapters (`collectors/wave2/{motorola,honor}/discovery.py`) — no
enabled-but-unregistered state. Wave 2 did not touch production
`config.yaml`.

### 5. Has production coupling increased?

No — zero Wave 2 code paths are reachable from production before Part D
of this mission (Motorola canary) explicitly extends the production
allowlist, which is a deliberate, gated, tested action, not incidental
coupling.

### 6. Are there old/stale collectors that should eventually be retired?

None found among the *wired* collectors (Samsung, Google, Nothing, OnePlus
all showed successful runs within the last day at Phase 0 of the Wave 2
qualification mission). Xiaomi's adapter exists and is exercised in
`tests/wave1/` but is deliberately `KEEP_STAGING`, not stale — its source
is unstable, not abandoned. See finding #3 above for schema-level (not
collector-level) staleness.

### 7. Can one developer still understand the main execution path in an afternoon?

**YES.** The path is exactly the two branches diagrammed above — a
single specialized Samsung collector, and one shared adapter/validator/
bridge/pipeline path that four wave1 OEMs and (as of this phase) two Wave 2
OEMs all use identically. `docs/ARCHITECTURE_MAP.md` (this phase) renders
it on one page. 16,361 LOC across 135 files for a system now covering 4
production OEMs + 2 staging-qualified OEMs + 4 recon-only validators is not
small, but the *shape* of the system — one pipeline, one resolver, one
alert path, one migration authority — has not multiplied. Motorola
promotion may proceed.

## Part F — database growth snapshot

Measured against `smartphone-clank-prod/data/clank.db`, ~8.2 days of
production history (2026-08-02 11:51 to 2026-08-10 17:11), covering
Samsung + Google + Nothing + OnePlus. Whole DB file: **1.03 MB**.

| Table | Rows now | Approx rows/day | Classification |
|---|---|---|---|
| `collector_run_metrics` | 149 | ~18 | Permanent audit history — one row per collector run, small fixed row size |
| `collector_runs` | 126 | ~15 | Permanent audit history (legacy-compat table, see `pipeline.py::run_collector`) |
| `confidence_ledger` | 257 | ~31 | Permanent audit history — append-only by design, explains every confidence change |
| `timeline_events` | 142 | ~17 | Permanent audit history — append-only, powers device timelines |
| `evidence` | 142 | ~17 | Permanent — one row per observation, core intelligence data, never deleted |
| `devices` | 129 | ~16 | Bounded naturally — grows only with genuinely new devices, not per-observation |
| `webhook_deliveries` | 5 | <1 | Permanent audit history — every alert transport decision, low volume so far (mostly baseline-suppressed) |
| `alerts` | 129 | ~16 (historical; 0/day expected going forward post alert-semantics fix) | Permanent — now delivered-only per the alert-persistence-semantics cleanup; the 129 are pre-fix phantom rows, documented in HANDOFF.md §9, not deleted |
| `rejected_candidates` | 11 | ~1 | Potential future retention candidate — diagnostic value decays over time, currently trivial volume |
| `snapshots` | 0 | 0 | Unknown — table exists, `database/snapshot_retention.py::prune_snapshots()` is called every collector run but nothing writes rows currently observed |

At current volume (~1 MB after 8 days across 4 OEMs), growth is not a
near-term risk even scaled by 5-10x for a larger production OEM roster.
**No retention system is warranted or implemented this mission** — this
snapshot exists to make future retention decisions evidence-based, not to
justify building one now.

## Verdict

**Proceed to Part D (Motorola canary).** No STOP condition triggered. The
one real finding (15 zero-row tables) is pre-existing schema debt, not a
Wave 2 regression, and does not block a canary that only adds rows to
already-active tables (`devices`, `evidence`, `webhook_deliveries`,
`wave1_baseline_state`, `collector_run_metrics`, `confidence_ledger`,
`timeline_events`).

## Part 14 update (scope-unification phase, five-OEM state)

Rechecked after Motorola's promotion and this phase's canary/testing work,
~8.27 days of production history (2026-08-02 11:51 to 2026-08-10 18:18).
Whole DB file: **1.20 MB** (was 1.03 MB at the four-OEM snapshot — +17%
over the time this phase's work took, most of it one-off canary testing,
not steady-state growth).

| Table | Rows now | Classification | Note |
|---|---|---|---|
| `devices` | 144 | Bounded naturally | +15 (Motorola baseline) |
| `evidence` | 160 | Permanent | +18 |
| `confidence_ledger` | 275 | Permanent audit history | +18 |
| `collector_run_metrics` | 163 | Permanent audit history | +14 (Motorola baseline + repeats) |
| `timeline_events` | 160 | Permanent audit history | +18 |
| `webhook_deliveries` | 23 | Permanent audit history | +18 (Motorola baseline + 3 repeats' suppression records) |
| `alerts` | 129 | Permanent (delivered-only) | unchanged — Motorola baseline correctly suppressed, 0 new |
| `rejected_candidates` | 545 | Potential future retention candidate | **+534, almost entirely Motorola (530 of 545)** — flagged below |
| `snapshots` | 0 | LEGACY (see `docs/infra/ZERO_ROW_TABLE_AUDIT.md`) | unchanged |
| `wave1_baseline_state` | 4 | Bounded naturally (one row per source) | +1 (Motorola) |

**Obvious growth risk flagged**: `rejected_candidates` grew 49x this phase,
530 of 545 rows from Motorola. This is not itself a bug — Motorola's
sitemap adapter genuinely finds 106 `AMBIGUOUS` candidates every cycle
(the known slug-normalizer gap documented in
`docs/wave2/MOTOROLA_CANARY_REPORT.md`, fails closed, never false-accepts).
At the scheduled production cadence (360 min = 4 polls/day), Motorola
alone would add **~424 rejected-candidate rows/day** going forward if that
gap is never narrowed — roughly 150,000 rows/year from this one source.
Still small in absolute size (each row is a short text string, not a full
page), but the fastest-growing table in the schema by a wide margin.
**No retention system is being built this phase** — this is a measurement,
not an incident; flagged for whoever eventually narrows the Motorola
validator gap or decides retention policy for this specific table.
