# Nothing Production Canary Report

Date: 2026-08-10. Scope: promote Nothing (only) from Wave1 staging into
production, reusing the exact machinery proven by
`docs/wave1/GOOGLE_CANARY_REPORT.md`. OnePlus and Xiaomi untouched.

## 0. What changed (tiny, on top of Google's mechanism — no rebuild)

- `collectors/wave1/__init__.py::WAVE1_PRODUCTION_SCOPE` extended from
  `{"google"}` to `{"google", "nothing"}` — the only functional code change.
- `runtime/daemon.py` needed **zero changes**: it already loops over
  `build_wave1_production_collectors(settings)` generically by
  `adapter.manufacturer`, so adding Nothing to the scope set was sufficient
  to get it scheduled, logged, and isolated from Samsung/Google failures.
- The single-worker scheduler executor (serializing all collector jobs to
  avoid the `DiscordAlerter.backfill` race — see `GOOGLE_CANARY_REPORT.md`
  §0) was left in place, unmodified, and continues to protect Nothing's jobs
  the same way it protects Google's and Samsung's. Not revisited this phase,
  per the mission's explicit instruction not to touch scheduler concurrency.

## 1. Preflight (all verified before any change)

```text
exactly one production daemon      PASS (PID 31920+28028, cmdline confirmed via Win32_Process)
runs from prod tree                PASS
production DB integrity            PASS (PRAGMA integrity_check = ok)
schema = HEAD                      PASS (alembic_version = 0007_wave1_baseline_state)
Samsung healthy                    PASS (all recent collector_run_metrics rows status=success)
Google healthy                     PASS (run_count=6 at preflight, all success, no failures)
Nothing staging catalogue clean    PASS (9 devices, 21 evidence — re-verified fresh, not
                                          assumed; matches PROMOTION_REPORT.md exactly)
Nothing validator/pollution tests  PASS (12/12: tests/wave1/test_validators.py +
                                          test_pollution_cannot_recur.py)
production Discord config          PASS (environment=production, webhook + maintenance
  understood, no secrets printed        webhook configured, min_confidence_for_alert=20)
```

Fresh backup: `data/backups/clank_20260810_142306.db` (production tree).

## 2. Nothing staging truth (fresh inspection, not assumed)

```text
9 devices:  Phone (1), (2), (3), (3a), (3a) Lite, (3a) Pro, (4a), (4a) Pro, (4b)
21 evidence rows (multi-region corroboration — uk-default + us + in URLs
   normalized to the same device, not counted as separate devices)
confidence: 10/20/30 exactly matching 1/2/3-region confirmation
0 accessories, earbuds, watches, marketing copy, navigation strings, or
   malformed names among the 9 accepted devices (checked all 9 marketing
   names against a suspicious-token list: none matched)
0 duplicate regional pages counted as separate devices — the resolver
   correctly merges same-product regional URLs into one device with
   multiple evidence rows, confirmed by inspecting evidence.url directly
```

**CMF handling**: `CMF Phone 1` is rejected on every cycle
(`unsupported_manufacturer_pending_schema_decision`, routed to
`RejectedCandidate`, never merged into `manufacturer=nothing`). This is the
existing, already-safe deferral from the integration phase — no new
brand/family policy was invented or needed for this promotion, per the
mission's explicit instruction not to solve CMF expansively here.

## 3. Deployment

```text
dev change:  collectors/wave1/__init__.py (WAVE1_PRODUCTION_SCOPE += "nothing")
             + 2 new / 1 updated regression tests
tests:       139 passed, 0 failed (dev tree canonical suite)
deploy:      collectors/wave1/__init__.py copied to prod tree, diff-verified byte-identical
config:      wave1.nothing.enabled=true, max_fetches_per_run=20,
             interval_minutes=90 added to prod config.yaml (Google's block untouched;
             Samsung's own config untouched)
restart:     no in-progress run confirmed -> clean stop (verified via
             collector_run_metrics + PRAGMA integrity_check) -> restarted via
             start-runtime.ps1 -> exactly one daemon confirmed (PID 39596)
```

## 4. Production-scope regression test

`tests/wave1/test_production_scope.py::test_config_typo_enabling_oneplus_and_xiaomi_does_not_reach_production`:
with `wave1.google.enabled`, `wave1.nothing.enabled`, `wave1.oneplus.enabled`,
and `wave1.xiaomi.enabled` all set `true` in the same settings object, only
`["google", "nothing"]` come back from `build_wave1_production_collectors()`.
OnePlus and Xiaomi require an explicit code change to `WAVE1_PRODUCTION_SCOPE`
to ever reach production — config alone is never sufficient. Confirmed live
in the daemon's own startup log too: `Collector skipped: oneplus_support
(out_of_production_scope)`, `Collector skipped: xiaomi_support
(out_of_production_scope)`.

## 5. Baseline import (cycle 1, `production_scheduled`, startup job)

```text
OEMCycleResult(nothing_products_sitemap: candidates=22 valid=21 rejected=1
  new=9 updated=12 resighted=0 baseline_complete_before=False
  baseline_just_completed=True)
```

(`updated=12` within the same cycle is expected — confidence rises as
additional regional evidence for the same device is processed later in the
same traversal, e.g. Phone (1) 10→20→30 as its uk/us/in pages are each
found; this is normal multi-region corroboration, not a bug, and matches
staging's exact numbers.)

Inspected directly in production `data/clank.db`:

```text
manufacturer counts: nothing=9, google=7 (unchanged), samsung=97 (unchanged)
devices: Phone (1)=30, (2)=20, (3)=30, (3a)=20, (3a) Lite=20, (3a) Pro=20,
  (4a)=20, (4a) Pro=30, (4b)=20  — matches staging exactly
evidence: 21 rows, all nothing.tech/us.nothing.tech/in.nothing.tech product URLs
rejected_candidates (nothing): 1 (CMF Phone 1) — not merged, not dropped silently
duplicate marketing_name across manufacturer: none
duplicate model_number across manufacturer: none
webhook_deliveries created by this run: 0 (total stayed at 5, all pre-existing
  2026-08-08 synthetic tests)
aliases/family: family_name is NULL for all 9 Nothing devices (Nothing's
  family-name inference was not part of this promotion's scope — pre-existing
  behavior, unchanged from staging, not a regression)
```

Devices were **discovered independently from the live source** — production's
own HTTP requests to `nothing.tech`/`us.nothing.tech`/`in.nothing.tech`
during this cycle, not copied from the staging DB (a separate SQLite file).

No rollback condition occurred: no marketing-text pollution, no accessories
accepted as phones, no duplicate devices, no cross-OEM identity merge, no
malformed model/name, no unexpected newsroom alert, no Samsung/Google
failure caused by Nothing.

## 6. Canary cycles (3 additional, `production_manual`, 4 total)

Run manually via the same reviewed path Google's canary used (a short
verification script invoking `build_wave1_production_collectors` +
`assert_db_matches_environment` + `run_oem_staging_cycle` — not a new
production code path, and the daemon's own 90-minute scheduled interval was
never shortened). All 3 identical:

```text
OEMCycleResult(nothing_products_sitemap: candidates=22 valid=21 rejected=1
  new=0 updated=0 resighted=21 baseline_complete_before=True
  baseline_just_completed=False)
```

After 4 total cycles (1 baseline + 3 resighting):

```text
devices:               nothing=9, google=7, samsung=97 (all unchanged since baseline)
evidence:               126 total (105 pre-Nothing + 21 nothing — no growth cycle-over-cycle)
confidence_ledger:      241 total
wave1_baseline_state:   nothing_products_sitemap run_count=4; google run_count=8 (its
                        own 45-min schedule kept firing throughout, unaffected)
duplicate marketing_name across manufacturer: none
webhook_deliveries:     5 (unchanged — zero new deliveries from any of the 4 cycles)
integrity_check:        ok (checked after every cycle)
```

Samsung and Google both continued on their own normal schedules throughout,
every run `status=success`, zero failures caused by Nothing's presence —
confirming the single-worker executor serializes safely across three
concurrent-capable collectors without starving any of them.

## 7. Discord

Zero newsroom deliveries from the baseline import (correct — backfill
suppression) and zero from the 3 resighting cycles (correct — resightings
are not "new," never reach eligibility checks). No production event was
manufactured to test Discord. Transport/eligibility logic remains covered by
`tests/wave1/test_discord_safety.py` (part of the canonical run below). No
webhook URL was ever printed.

## 8. Tests

```bash
PYTHONPATH=. python -m pytest -q
```

```text
139 passed, 0 failed, 0 skipped, 0 xfailed
```

(137 prior + 2 new: `test_nothing_enabled_alone_is_returned`,
`test_google_and_nothing_enabled_together_is_returned`; plus
`test_production_scope_is_google_only` renamed/updated to
`test_production_scope_is_google_and_nothing_only`, and the old
`test_config_typo_enabling_oneplus_does_not_reach_production` replaced by
`test_config_typo_enabling_oneplus_and_xiaomi_does_not_reach_production`,
which is a net +2 tests, not a straight addition of 4, since two prior tests
were updated in place rather than duplicated.) Includes Nothing validator
tests, pollution-cannot-recur regression, production-scope tests (Samsung's
and wave1's), schema-authority tests, Discord eligibility/transport tests.

## 9. Promotion verdict

```text
PROMOTED
```

Nothing is live in production: `wave1.nothing.enabled: true`,
`interval_minutes: 90`, discovering independently from
`nothing.tech`/`us.nothing.tech`/`in.nothing.tech`, baseline complete (9
devices), 3 additional stable cycles with 0 pollution, 0 unwarranted alerts,
0 Samsung impact, 0 Google impact, 0 cross-OEM collisions. Scheduled to
continue running every 90 minutes via the live daemon.

Conditions carried forward from `docs/wave1/PROMOTION_REPORT.md` (not
resolved by this canary, not blockers): the CMF schema decision remains
deferred (CMF Phone 1 stays correctly excluded, invisible to the catalogue,
not a data-safety issue); only 3 regions (uk/us/in) confirmed distinct — the
full storefront-region list is still unknown, expand deliberately later.

## 10. What stays unpromoted

- **OnePlus** — `PROMOTE_WITH_CONDITIONS`, staging only. Not in
  `WAVE1_PRODUCTION_SCOPE`. Candidate for a future session.
- **Xiaomi** — `KEEP_STAGING`, unchanged.

Rollback (documented, not needed): `wave1.nothing.enabled: false` in
production `config/config.yaml`, restart daemon. No data deleted — existing
Nothing devices/evidence remain, simply stop receiving new discoveries.

## Success state reached

```text
Production:  Samsung, Google, Nothing
Staging:     OnePlus
Held:        Xiaomi
Nothing verdict: PROMOTED
```
