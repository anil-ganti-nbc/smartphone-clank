# Google — proposed production promotion delta

**NOT APPLIED.** Prepared for operator review only. Verdict: `PROMOTE_WITH_CONDITIONS`
(see `docs/wave1/PROMOTION_REPORT.md`).

## Config delta (`config/config.yaml`)

```yaml
wave1:
  google:
    enabled: true
    max_fetches_per_run: 20
    interval_minutes: 45   # see "Polling cadence" below
    validation_state: LIVE_VALIDATED
```

## Prerequisites before this can actually run in production

1. The staging→production bridge (`collectors/wave1/bridge.py` +
   `collectors/wave1/staging_pipeline.py`) currently only runs when
   `runtime.environment.assert_db_matches_environment(..., "staging")` has
   already passed. Enabling this config key alone does **not** make it run in
   production — `main.py run` (production path) never imports
   `collectors.wave1` at all today. A deliberate, separate code change is
   required to wire a production-safe equivalent path (out of scope for this
   report — flagging so nobody assumes flipping `enabled: true` here is
   sufficient).
2. `collectors/__init__.py::production_scope()` must be deliberately extended
   to include Google's source id — it is not in scope today by design, and a
   config flag alone cannot add it (this is the same protection that stopped
   the August 2026 incident from recurring).

## Source

- Discovery: `https://store.google.com/us/category/phones?hl=en-US`
- Region: US only at launch; expand per `docs/wave1/google_recon.md`'s ~40
  regional storefronts once single-region behavior is soaked in production.

## Polling cadence

30-60 min recommended. This source is the one that surfaced the Pixel 11
teaser ahead of a dedicated product page — err toward the shorter end (30-45
min) given its demonstrated news value, balanced against politeness (one
request per cycle, ~3MB page).

## Baseline state expectations

First production run will be a fresh baseline (no state carries over from
staging — `wave1_baseline_state` is staging-DB-local). Expect 0 newsroom
alerts for the first run's ~7 devices; expect real alert eligibility from the
second run onward for anything genuinely new.

## Evidence weight

`SourceType.SUPPORT_PAGE`, weight 10 (see `collectors/wave1/bridge.py`).
Conservative and consistent with Samsung's own new-page baseline weight — do
not raise without a deliberate, documented decision.

## Health baseline

Adapter classification: LIVE_VALIDATED. 3/3 clean live cycles in staging, 0
HTTP failures, 0 garbage. No live 403/blocking behavior observed for this
source (unlike Xiaomi).

## Discord behaviour

Standard `DiscordAlerter` eligibility rules apply once baseline completes
(`min_confidence_for_alert`, `significant_confidence_delta` from
`config/config.yaml`). No `staging_label` in production (that flag is
automatically off when `settings.environment != "staging"`).

## Rollback

```yaml
wave1:
  google:
    enabled: false
```

Disabling Google alone has no effect on OnePlus/Nothing — each OEM's
`build_wave1_collectors()` entry is independently gated. No data
deletion is performed by disabling; existing Google devices/evidence remain
in the database, simply stop receiving new discoveries.
