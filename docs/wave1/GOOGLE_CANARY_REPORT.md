# Google Production Canary Report

Date: 2026-08-10. Scope: promote Google (only) from Wave1 staging into real
production, per `docs/wave1/PROMOTION_REPORT.md`'s `PROMOTE_WITH_CONDITIONS`
verdict. OnePlus, Nothing, Xiaomi remain untouched (staged/unpromoted).

## 0. What changed to make this possible

`docs/wave1/promotion/google.md` flagged two prerequisites — neither existed
before this phase:

1. **Production-safe wiring.** `main.py run` (production) never imported
   `collectors.wave1` before this phase. Added:
   - `collectors/wave1/__init__.py::WAVE1_PRODUCTION_SCOPE = {"google"}` and
     `build_wave1_production_collectors()` — the explicit second gate (config
     `wave1.<oem>.enabled: true` alone is not sufficient; the OEM must also
     be in this allowlist). Mirrors `collectors/__init__.py::production_scope()`'s
     own philosophy for Samsung.
   - `runtime/daemon.py` now builds wave1 production collectors, asserts
     `runtime.environment.assert_db_matches_environment(url, "production")`
     first, and schedules each via the same `run_oem_staging_cycle()` used in
     staging (environment-agnostic function; caller enforces the environment
     check — see its updated docstring).
   - **Concurrency fix required by this change**: `DiscordAlerter.backfill` is
     a mutable flag on the single shared `IntelligencePipeline` instance.
     APScheduler's default executor runs distinct jobs concurrently
     (thread pool), so a wave1 job and Samsung's own job could have
     interleaved and let one job's backfill state leak into the other's
     alert decision. Fixed by giving `BlockingScheduler` a single-worker
     executor (`ThreadPoolExecutor(max_workers=1)`), making all collector
     runs — Samsung and wave1 alike — strictly sequential. This was not
     scope creep — it's a correctness bug this exact change would have
     introduced if left unfixed.
2. **Scope gate.** Addressed by (1) above.

## 1. Pre-promotion safety check (all verified before touching production)

```text
prod runtime -> prod tree               PASS (PID 34508+27348, cmdline confirmed via Win32_Process)
dev work -> dev tree                    PASS (all edits made in C:\Users\anil\Desktop\smartphone-clank)
production DB integrity -> OK           PASS (PRAGMA integrity_check = ok)
production schema -> HEAD               PASS (alembic_version = 0007_wave1_baseline_state)
production manufacturers -> Samsung only PASS (97 samsung, 0 others, before promotion)
Google staging state -> clean           PASS (7 devices, 0 rejected, confidence flat 10)
Google validator -> strict              PASS (tests/wave1/test_validators.py, 2 google-specific + shared)
pollution regression -> passing         PASS (tests/wave1/test_pollution_cannot_recur.py, 10 tests)
production Discord configuration        PASS (environment=production, webhook + maintenance webhook configured,
  -> understood                              min_confidence_for_alert=20; values never printed)
```

Fresh production DB backup taken immediately before promotion:
`data/backups/clank_20260810_125238.db` (in the production tree).

## 2. Deployment

Reviewed, tested (dev tree canonical suite green) files deployed as
one-off copies into the frozen production tree — consistent with
`docs/infra/DEPLOYMENT_MODEL.md`'s dev → test → review → deploy model, not a
full tree recopy:

```text
main.py
dashboard/app.py
database/schema_guard.py
collectors/samsung/sitemap_collector.py
collectors/wave1/__init__.py
collectors/wave1/staging_pipeline.py
runtime/daemon.py
```

Config delta applied directly to the production tree's `config/config.yaml`
(matches `docs/wave1/promotion/google.md`, `interval_minutes: 45` — the
shorter end of the recommended 30-60 min range given the source's
demonstrated news value):

```yaml
wave1:
  google:
    enabled: true
    max_fetches_per_run: 20
    interval_minutes: 45
```

Production daemon stopped cleanly (no in-progress run — last Samsung cycle
had finished; verified via `collector_run_metrics`), restarted via the
already-fixed `start-runtime.ps1`. Exactly one daemon process confirmed
after restart (PID 31920 + child 28028).

## 3. Baseline import (cycle 1, production_scheduled, startup job)

```text
OEMCycleResult(google_store_category_phones: candidates=7 valid=7 rejected=0
  new=7 updated=0 resighted=0 baseline_complete_before=False
  baseline_just_completed=True)
```

Inspected directly in production `data/clank.db`:

```text
manufacturer counts: google=7, samsung=97 (unchanged)
PIXEL 10, PIXEL 10 PRO, PIXEL 10 PRO FOLD, PIXEL 10A, PIXEL 11, PIXEL 9, PIXEL 9A
confidence: flat 10 (single support-page-tier evidence each)
evidence: 7 rows, all https://store.google.com/us/product/... or the category
  page itself — matches docs/wave1/promotion/google.md's declared source exactly
rejected_candidates (google): 0
duplicate marketing_name across manufacturer: none
duplicate model_number across manufacturer: none
webhook_deliveries created by this run: 0
```

Verified against the hostile-audit checklist (spec section 6):
manufacturer=google ✓, plausible Pixel names ✓, no marketing sentences ✓, no
accessories/watches/buds ✓, no navigation text ✓, no malformed pseudo-models
✓, no Samsung/Google identity collisions ✓, evidence points to the expected
official source ✓, confidence entries explainable ✓, 0 newsroom alerts from
the baseline import ✓ (baseline-not-newsroom-alert semantics correctly
applied via `pipeline.alerter.backfill`). No row resembling the August
incident's marketing-text pollution appeared.

Production devices were **discovered independently from the live source**,
not copied from staging (staging and production are separate SQLite files;
the production Google rows were created by production's own live HTTP
request to `store.google.com`, timestamped 2026-08-10 in `evidence.url`
alongside a freshly-generated device id — not the staging rows).

## 4. Canary cycles (4 additional, `production_manual`)

Run manually via a short verification script invoking the exact same
reviewed path the daemon's scheduled job uses
(`build_wave1_production_collectors` + `assert_db_matches_environment` +
`run_oem_staging_cycle`) — not a new production code path, and the daemon's
own scheduled interval (45 min) was never shortened to rush this. All 4:

```text
OEMCycleResult(google_store_category_phones: candidates=7 valid=7 rejected=0
  new=0 updated=0 resighted=7 baseline_complete_before=True
  baseline_just_completed=False)
```

Identical across all 4 — stable resighting, no drift, no duplication.

After 5 total cycles (1 baseline + 4 resighting):

```text
devices:                google=7, samsung=97 (unchanged throughout)
evidence:                105 total, 7 google (no growth cycle-over-cycle — dedup works)
confidence_ledger:       220 total (98+... unaffected by resighting, as expected)
wave1_baseline_state:    google_store_category_phones, run_count=5
duplicate marketing_name across manufacturer: none
duplicate model_number across manufacturer:   none
webhook_deliveries:      5 (all predate this promotion — 2026-08-08 synthetic
                          tests; zero new deliveries from any of the 5 Google
                          cycles)
collector_run_metrics:   every Google row has run_reason in
                          {production_scheduled, production_manual}, status=success
integrity_check:         ok (checked after every cycle)
```

Samsung ran on its own normal schedule throughout (own `collector_run_metrics`
rows interleaved, `run_reason=production_scheduled`, unaffected by any Google
cycle — no cross-collector interference, confirming the single-worker
executor fix serializes safely without starving either collector).

## 5. Discord

`docs/wave1/promotion/google.md`'s expectation held exactly: 0 newsroom
alerts for the baseline's 7 devices, and no alert-eligible event occurred
during the 4 resighting cycles (resightings are not "new," so they never
reach eligibility checks). No production event was manufactured to test
Discord — the mission explicitly prohibits that. Transport/eligibility logic
itself is covered by the existing regression suite
(`tests/wave1/test_discord_safety.py`, 5 tests, part of the canonical run
below). No webhook URL was ever printed.

## 6. Tests

```bash
PYTHONPATH=. python -m pytest -q
```

```text
137 passed, 0 failed, 0 skipped, 0 xfailed
```

(132 prior + 5 new: `tests/wave1/test_production_scope.py`, covering
`WAVE1_PRODUCTION_SCOPE == {"google"}`, the config-typo-cannot-enable-OnePlus
regression, and the daemon's environment-guard refusal on a staging-looking
DB.) Includes: Google validator tests, pollution-cannot-recur regression,
production-scope tests (both Samsung's and wave1's), schema-authority tests,
Discord eligibility/transport tests.

## 7. Promotion verdict

```text
PROMOTED
```

Google is live in production: `wave1.google.enabled: true`,
`interval_minutes: 45`, discovering independently from
`store.google.com/us/category/phones`, baseline complete (7 devices),
4 additional stable cycles with 0 pollution, 0 unwarranted alerts, 0 Samsung
impact, 0 cross-OEM collisions. Scheduled to continue running every 45
minutes going forward via the live daemon.

Conditions carried forward from `docs/wave1/PROMOTION_REPORT.md` (not
resolved by this canary, not blockers): US region only (recon documented
~40 regional storefronts — expand deliberately, later); OTA/factory-image
acknowledgment wall remains unresolved (does not affect discovery).

## 8. What stays unpromoted

- **OnePlus** — `PROMOTE_WITH_CONDITIONS` per `PROMOTION_REPORT.md`, staging
  only. Not enabled in `WAVE1_PRODUCTION_SCOPE`. Candidate for next session.
- **Nothing** — same status, same non-promotion, candidate for the session
  after OnePlus.
- **Xiaomi** — `KEEP_STAGING`, unchanged.

Rollback (documented, not needed): `wave1.google.enabled: false` in
production `config/config.yaml`, restart daemon. No destructive cleanup
implemented or recommended — existing Google devices/evidence would remain,
simply stop receiving new discoveries.
