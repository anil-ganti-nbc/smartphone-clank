# Motorola Production Canary Report

**Verdict: PROMOTED** (2026-08-10)

## Pre-canary revalidation (§21)

Re-ran the live Motorola adapter fresh rather than trusting the earlier
qualification-mission numbers. Result matched exactly: 124 raw candidates
from 3 regional sitemaps (US/GB/DE), 18 valid, 0 invalid, 106 ambiguous
(fails closed, never false-accepted). Every one of the 18 accepted
identities was individually inspected — all Razr or Moto G variants, zero
Lenovo/ThinkPad/tablet/watch/accessory/charger/case/promo/navigation/
malformed strings, zero cross-manufacturer alias collisions. Source safety
recheck: 3/3 pages fetched, HTTP 200, zero failures — unchanged from the
qualification phase.

## A production bug found and fixed during this canary

The first production baseline attempt (2026-08-10 17:30 IST) **silently
dropped every Motorola discovery**: production `config.yaml`'s top-level
`manufacturers:` allowlist (read by `pipeline.py::process_discoveries()`)
had not been extended to include `motorola`, even though
`WAVE1_PRODUCTION_SCOPE` had. The adapter fetched and validated 18
candidates correctly, but `process_discoveries()` silently `continue`d past
all of them — and worse, the baseline-completion gate (evaluated *before*
the manufacturer filter) still marked `motorola_regional_sitemap`'s
baseline as complete. Left uncorrected, the next scheduled run would have
treated the same 18 devices as "genuinely new since baseline" and fired 18
real newsroom alerts for devices Clank had never actually recorded — a
direct instance of the "no silent zero" failure mode
`docs/ENGINEERING_PRINCIPLES.md` Rule 6 exists to catch.

Fix: stopped the daemon (no risk to other OEMs — verified no in-progress
run first), added `motorola` to `manufacturers:` in both
`smartphone-clank-prod/config/config.yaml` and the dev tree's equivalent,
deleted the one incorrect `wave1_baseline_state` row (verified zero
Device/Evidence rows existed for Motorola before deleting — this was a
correction of an inconsistent flag, not a loss of real data), and
restarted. The corrected baseline run produced exactly the expected
result. This is now documented here and should inform future OEM
promotions: the manufacturer allowlist and the production-scope allowlist
are two independent gates (by design, per Rule 7) and **both** must be
extended together — a checklist gap, not an architecture gap.

## Baseline (§25)

Production discovered Motorola live and independently — no staging data
was copied. Corrected baseline run (2026-08-10 17:35 IST):

    candidates=124 valid=18 rejected=106 new=15 updated=3 resighted=0
    baseline_complete_before=False baseline_just_completed=True

15 new Device rows, 18 Evidence rows (3 candidates merged as additional
evidence onto an already-created device within the same run — multi-region
corroboration, e.g. Razr Fold and Razr Gen 5 each seen on 2 of the 3
regional sitemaps), confidence via `ConfidenceService` (values 10-30,
higher only where multi-region evidence genuinely merged). Baseline state
recorded complete. **0 delivered newsroom alerts** — confirmed directly
against `alerts` table, matching `webhook_deliveries` showing the
suppression decision.

## Hostile production audit (§26)

Direct SQL inspection of the live production rows post-baseline:

| Check | Result |
|---|---|
| Lenovo/ThinkPad/ThinkBook/IdeaPad/Yoga/Legion/tablet/watch/buds/charger/case keyword scan | 0 hits |
| Duplicate `model_number` | 0 |
| Cross-manufacturer alias collisions | 0 |
| Devices without evidence | 0 |
| Confidence outliers | none — range 10-30, all explainable by evidence count |
| Longest names | `MOTO G POWER 2025`/`2026` (17 chars) — normal |

No pollution. No rollback needed.

## Canary cycles (§27)

3 repeat cycles run against the live production pipeline (not staging),
each triggering a real HTTP fetch against the same three regional
sitemaps:

| Cycle | Valid | New | Updated | Resighted | Evidence total | Alerts total |
|---|---|---|---|---|---|---|
| Repeat 1 | 18 | 0 | 0 | 18 | 18 | 0 |
| Repeat 2 | 18 | 0 | 0 | 18 | 18 | 0 |
| Repeat 3 | 18 | 0 | 0 | 18 | 18 | 0 |

Zero new devices, zero evidence explosion, zero confidence inflation
(values identical to post-baseline), zero duplicate alerts, zero catalogue
explosion, zero malformed identities across all 3 repeats. DB integrity
`ok` after all cycles.

## Failure isolation (§28)

Not attacked deliberately (per instruction — fixture/mock testing is
sufficient and already exists: `tests/wave1/test_failure_semantics.py`,
per-OEM try/except isolation in `runtime/daemon.py::make_wave1_job()` and
`collectors/wave1/__init__.py::run_wave1_once()`). Directly observed as a
side effect of this canary: Samsung, Google, Nothing, and OnePlus all ran
successfully on their normal schedules throughout the entire canary window
(config fix, DB correction, restart, baseline, 3 repeat cycles) — see
`collector_run_metrics` timestamps, all `status=success`, zero new
failures. Motorola's presence did not disrupt any existing OEM.

## Alert semantics (§29)

No real post-baseline event occurred during the canary (not manufactured,
per instruction). Baseline correctly produced a `WebhookDelivery`
suppression record and 0 `Alert` rows. The offline mocked E2E lifecycle
tests (`tests/wave1/test_alert_lifecycle_e2e.py`, added in the Wave 2
qualification mission) remain the authoritative proof that a real
post-baseline Motorola event would be delivered and recorded correctly —
not re-derived here.

## Production invariance (other OEMs)

| Check | Before canary | After canary |
|---|---|---|
| Samsung | 97 devices | 97 devices — unchanged |
| Google | 7 devices | 7 devices — unchanged |
| Nothing | 9 devices | 9 devices — unchanged |
| OnePlus | 16 devices | 16 devices — unchanged |
| DB integrity | ok | ok |
| Daemon count | 1 | 1 |

Backup taken before any change:
`smartphone-clank-prod/data/backups/clank_pre_motorola_canary_20260810_225319.db`.

## Verdict: PROMOTED

Motorola meets every `PROMOTED` criterion: clean live baseline, clean
hostile audit, 3 stable repeat cycles, no garbage, no evidence inflation,
no confidence inflation, no alert errors, no effect on existing OEMs,
source health normal. `WAVE1_PRODUCTION_SCOPE` now includes `motorola`.
Production manufacturers: **Samsung, Google, Nothing, OnePlus, Motorola.**
Interval set to 360 minutes (4 polls/day) per the qualification report's
polling recommendation — not shortened.

Rollback path if ever needed: set `wave1.motorola.enabled: false` in
production `config.yaml` and restart; no data is deleted automatically.
