# OnePlus — proposed production promotion delta

**NOT APPLIED.** Prepared for operator review only. Verdict: `PROMOTE_WITH_CONDITIONS`
(see `docs/wave1/PROMOTION_REPORT.md`).

## Config delta (`config/config.yaml`)

```yaml
wave1:
  oneplus:
    enabled: true
    max_fetches_per_run: 20
    interval_minutes: 90   # see "Polling cadence" below
    validation_state: LIVE_VALIDATED
```

## Prerequisites before this can actually run in production

Same two prerequisites as Google (see `docs/wave1/promotion/google.md`) —
the staging→production bridge and `production_scope()` extension. Not
duplicated here; apply identically.

## Source

- Discovery: `https://www.oneplus.com/us/sitemap.xml`
- Region: US only at launch. Recon found 69 regional sitemap URLs in
  robots.txt; `/global/` is confirmed stale (do not add without re-verifying
  freshness) and `/in/` returned 403 in recon (untested since, retest before
  adding).

## Polling cadence

1-2 h recommended. Sitemap regenerates on deploy, not continuously — a
146-URL flat XML file is cheap but not worth polling faster than this without
evidence of higher volatility.

## Baseline state expectations

Fresh baseline on first production run, ~16 devices, 0 newsroom alerts for
that run.

## Evidence weight

`SourceType.SUPPORT_PAGE`, weight 10. Same rationale as Google.

## Health baseline

Adapter classification: LIVE_VALIDATED. 3/3 clean live cycles, 0 HTTP
failures. One nav-page slug ("OnePlus featuring") leaked through as
AMBIGUOUS (harmless — never became a Device) — worth tightening the
denylist in `collectors/wave1/oneplus/discovery.py` before promotion, not a
hard blocker.

## Discord behaviour

Standard rules, same as Google.

## Rollback

```yaml
wave1:
  oneplus:
    enabled: false
```

Independent of Google/Nothing.
