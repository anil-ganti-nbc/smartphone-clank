# OnePlus Production Canary Report

Date: 2026-08-10. Scope: promote OnePlus (only) from Wave1 staging into
production, reusing the exact machinery proven by
`docs/wave1/GOOGLE_CANARY_REPORT.md` and `docs/wave1/NOTHING_CANARY_REPORT.md`.
Xiaomi untouched (`KEEP_STAGING`, its source oscillated 200/403 during
qualification).

OnePlus carries a stricter acceptance bar than Google/Nothing per the
mission's own instruction — the August 2026 contamination incident was
exactly this failure mode (marketing text mis-parsed as a device model). No
validator, regex, eligibility rule, or pollution-regression test was
weakened to make this promotion pass.

## 0. What changed (tiny, on top of proven machinery — no rebuild)

- `collectors/wave1/__init__.py::WAVE1_PRODUCTION_SCOPE` extended from
  `{"google", "nothing"}` to `{"google", "nothing", "oneplus"}` — the only
  functional code change.
- `runtime/daemon.py` needed **zero changes** — third consecutive OEM
  promoted without touching it, confirming the daemon's generic
  `build_wave1_production_collectors()` loop scales to N OEMs.
- The single-worker scheduler executor (serializing all collector jobs,
  originally added for Google's canary to avoid the `DiscordAlerter.backfill`
  race) was left in place, unmodified, per the mission's explicit
  instruction not to touch scheduler concurrency.

## 1. Preflight (all verified before any change)

```text
exactly one production daemon      PASS (PID 39596+21036, cmdline confirmed via Win32_Process)
runs from prod tree                PASS
production DB integrity            PASS (PRAGMA integrity_check = ok)
Alembic at HEAD                    PASS (alembic_version = 0007_wave1_baseline_state)
Samsung healthy                    PASS (0 non-success runs in collector_run_metrics)
Google healthy                     PASS (0 non-success runs, run_count=8 at preflight)
Nothing healthy                    PASS (0 non-success runs, run_count=4 at preflight)
OnePlus staging clean & idempotent PASS (16 devices, 16 evidence, run_count=3, re-verified fresh)
OnePlus validator tests            PASS (8/8, tests/wave1/test_validators.py)
August pollution-regression tests  PASS (4/4, tests/wave1/test_pollution_cannot_recur.py)
production Discord config          PASS (environment=production, webhook + maintenance
  understood, no secrets printed        webhook configured)
```

Fresh backup: `data/backups/clank_20260810_145816.db` (production tree).

## 2. Mandatory OnePlus identity audit (fresh, live, against the real source)

Ran the OnePlus adapter's `discover()` live against `oneplus.com/us/sitemap.xml`
and the OnePlus validator directly — not from the staging DB, from the
current live source, immediately before promoting:

```text
pages_requested=1 pages_fetched=1 http_failures=0
total candidates=17
```

**Accepted (16)** — every one a plausible OnePlus phone model, canonical
identity/source URL/validator result inspected individually for each:

```text
OnePlus 13, 13R, 12, 12R, Open, Nord 30-5G, 11, 10T, 10 Pro,
Nord 20-5G, Nord 200-5G, Nord 100, Nord 10-5G, 9 Pro, 9, 8T
```

Each accepted identity's `canonical_url` was a real `oneplus.com/us/<slug>`
product page (e.g. `https://www.oneplus.com/us/oneplus-13`,
`https://www.oneplus.com/us/n100`) — confirmed one evidence row per device
(single-region source, no multi-region corroboration here, unlike
Google/Nothing).

**Rejected (1)**: `"OnePlus featuring"` — a nav-page slug, `AMBIGUOUS`,
reason `unrecognized_oneplus_format`. Correctly excluded, never became a
Device. This is the same finding `docs/wave1/promotion/oneplus.md` flagged
during recon — confirmed still true, still correctly rejected, not a
regression.

**Explicit search of the accepted set — zero matches for**: marketing
sentences, offer/promotional text, navigation labels (beyond the one
correctly rejected), accessories, earbuds, watches, tablets,
chargers/cables/cases, malformed or implausibly long model names, duplicated
regional/store pages represented as separate devices (source is US-only,
single region — no duplication surface exists for this source).

**No STOP condition triggered.** Promotion proceeded.

## 3. Promotion

```text
dev change:  collectors/wave1/__init__.py (WAVE1_PRODUCTION_SCOPE += "oneplus")
             + 3 new / 2 updated regression tests in test_production_scope.py
tests:       140 passed, 0 failed (dev tree canonical suite)
deploy:      collectors/wave1/__init__.py copied to prod tree, diff-verified byte-identical
config:      wave1.oneplus.enabled=true, max_fetches_per_run=20,
             interval_minutes=90 added to prod config.yaml (Google's and
             Nothing's blocks untouched; Samsung's own config untouched)
restart:     no in-progress run confirmed -> clean stop (verified via
             collector_run_metrics + PRAGMA integrity_check) -> restarted via
             start-runtime.ps1 -> exactly one daemon confirmed (PID 43164)
```

### Xiaomi exclusion regression test

`tests/wave1/test_production_scope.py::test_config_typo_enabling_xiaomi_does_not_reach_production`:
with all three promoted OEMs' config enabled *and* `wave1.xiaomi.enabled: true`
simultaneously, only `["google", "nothing", "oneplus"]` come back from
`build_wave1_production_collectors()`. Xiaomi requires an explicit code
change to `WAVE1_PRODUCTION_SCOPE` to ever reach production — config alone
is never sufficient. Confirmed live in the daemon's own startup log too:
`Collector skipped: xiaomi_support (out_of_production_scope)`.

## 4. Production baseline (cycle 1, `production_scheduled`, startup job)

```text
OEMCycleResult(oneplus_regional_sitemap: candidates=17 valid=16 rejected=1
  new=16 updated=0 resighted=0 baseline_complete_before=False
  baseline_just_completed=True)
```

Identical shape to the fresh live identity audit run minutes earlier (same
17 candidates, same 16 accepted, same 1 rejected) — the live source did not
change between audit and promotion.

Inspected directly in production `data/clank.db`:

```text
manufacturer counts: oneplus=16, nothing=9 (unchanged), google=7 (unchanged),
  samsung=97 (unchanged)
devices: all 16 confidence=10 (single-evidence baseline, matches Google's
  pattern — this source has no multi-region corroboration)
evidence: 16 rows, all https://www.oneplus.com/us/<slug> product pages
rejected_candidates (oneplus): 1 ("OnePlus featuring") — not merged, not
  dropped silently
duplicate marketing_name across manufacturer: none
duplicate model_number across manufacturer: none
webhook_deliveries created by this run: 0 (total stayed at 5, all
  pre-existing 2026-08-08 synthetic tests — baseline did not spam the
  newsroom)
```

Devices were **discovered independently from the live source** — production's
own HTTP request to `oneplus.com/us/sitemap.xml` during this cycle, not
copied from the staging DB (a separate SQLite file).

No rollback condition occurred: no marketing text became a Device, no
non-phone product became a Device, no duplicate identities, no cross-OEM
collision, no malformed name, no unexpected newsroom alert, no Samsung/
Google/Nothing health regression caused by OnePlus.

## 5. Canary cycles (3 additional, `production_manual`, 4 total)

Run manually via the same reviewed path Google's and Nothing's canaries
used (`build_wave1_production_collectors` + `assert_db_matches_environment`
+ `run_oem_staging_cycle` — not a new production code path; the daemon's own
90-minute scheduled interval was never shortened). All 3 identical:

```text
OEMCycleResult(oneplus_regional_sitemap: candidates=17 valid=16 rejected=1
  new=0 updated=0 resighted=16 baseline_complete_before=True
  baseline_just_completed=False)
```

After 4 total cycles (1 baseline + 3 resighting):

```text
devices:               oneplus=16, nothing=9, google=7, samsung=97 (all unchanged since baseline)
evidence:               142 total (126 pre-OnePlus + 16 oneplus — no growth cycle-over-cycle)
confidence_ledger:      257 total
wave1_baseline_state:   oneplus_regional_sitemap run_count=4; google run_count=9,
                        nothing run_count=5 — both kept firing on their own
                        schedules throughout, unaffected
duplicate marketing_name across manufacturer: none
webhook_deliveries:     5 (unchanged — zero new deliveries from any of the 4 cycles)
non-success collector runs (any collector, all time): 0
integrity_check:        ok (checked after every cycle)
```

Samsung, Google, and Nothing all continued on their own normal schedules
throughout — every run `status=success`, zero failures caused by OnePlus's
presence, confirming the single-worker executor continues to serialize
safely across four concurrent-capable collectors without starving any of
them.

## 6. Discord

Zero newsroom deliveries from the baseline import (correct — backfill
suppression) and zero from the 3 resighting cycles (correct — resightings
are not "new," never reach eligibility checks). No production event was
manufactured to test Discord. Transport/eligibility logic remains covered by
`tests/wave1/test_discord_safety.py` (part of the canonical run below). No
webhook URL was ever printed.

## 7. Tests

```bash
PYTHONPATH=. python -m pytest -q
```

```text
140 passed, 0 failed, 0 skipped, 0 xfailed
```

August pollution-regression tests specifically, run in isolation to
demonstrate they are unchanged and still release-blocking:

```bash
PYTHONPATH=. python -m pytest -q tests/wave1/test_pollution_cannot_recur.py -v
```

```text
4 passed, 0 failed
```

(139 prior + net +1: `test_production_scope_is_google_and_nothing_only`
renamed/updated to `test_production_scope_is_google_nothing_oneplus_only`;
`test_config_typo_enabling_oneplus_and_xiaomi_does_not_reach_production`
replaced by `test_config_typo_enabling_xiaomi_does_not_reach_production`;
added `test_oneplus_enabled_alone_is_returned` and
`test_google_nothing_oneplus_enabled_together_is_returned` — net +1 test,
not +3, since two prior tests were updated in place.) Includes OnePlus
validator tests, pollution-cannot-recur regression, production-scope tests
(Samsung's and wave1's), schema-authority tests, Discord eligibility/
transport tests.

## 8. Verdict

```text
PROMOTED
```

OnePlus is live in production: `wave1.oneplus.enabled: true`,
`interval_minutes: 90`, discovering independently from
`www.oneplus.com/us/sitemap.xml`, baseline complete (16 devices), 3
additional stable cycles with 0 pollution, 0 unwarranted alerts, 0
Samsung/Google/Nothing impact, 0 cross-OEM collisions. Scheduled to continue
running every 90 minutes via the live daemon.

Conditions carried forward from `docs/wave1/PROMOTION_REPORT.md` (not
resolved by this canary, not blockers): only `/us/` region enabled — recon
found 69 regional sitemap URLs in robots.txt, `/global/` confirmed stale,
`/in/` returned 403 during recon (untested since); expand deliberately
later, not this phase.

## 9. Wave 1 production expansion — complete

```text
Production:  Samsung, Google, Nothing, OnePlus
Staging:     (none remaining at PROMOTE_WITH_CONDITIONS)
Held:        Xiaomi (KEEP_STAGING — source oscillated 200/403 during
             qualification, experimental adapter, not re-attempted this phase)
```

Per the mission's explicit stop condition: OnePlus passed, so this phase
stops here. Xiaomi was not touched. Wave 2 (which manufacturers come next)
is a separate, future decision — not started, not scoped, not implied by
this report.
