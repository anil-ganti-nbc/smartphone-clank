# Nothing — proposed production promotion delta

**NOT APPLIED.** Prepared for operator review only. Verdict: `PROMOTE_WITH_CONDITIONS`
(see `docs/wave1/PROMOTION_REPORT.md`).

## Config delta (`config/config.yaml`)

```yaml
wave1:
  nothing:
    enabled: true
    max_fetches_per_run: 20
    interval_minutes: 90   # see "Polling cadence" below
    validation_state: LIVE_VALIDATED
```

## Prerequisites before this can actually run in production

Same two prerequisites as Google (staging→production bridge,
`production_scope()` extension) — see `docs/wave1/promotion/google.md`.

Additionally: the CMF schema decision (`manufacturer=cmf` vs
`parent_brand=Nothing` vs something else — spec explicitly deferred this,
see `docs/wave1/nothing_recon.md` and `INTEGRATION_REPORT.md` §D) should
ideally be resolved before promotion, since CMF Phone 1 is a real,
currently-selling India-region product that this adapter can see but
currently routes to `RejectedCandidate` rather than the catalogue. Not a
hard blocker — the Nothing-branded-phone portion of this source works
cleanly without it.

## Source

- Discovery: `nothing.tech/sitemap/products/1.xml` + `us.nothing.tech` +
  `in.nothing.tech` region variants.
- Region: uk (default)/us/in confirmed distinct catalogues this session
  (CMF Phone 1 India-only is the clearest proof). Recon flagged that the
  full list of Nothing's storefront regions is unknown — only these 3 were
  spot-checked.

## Polling cadence

1-2 h recommended, matching OnePlus's reasoning (structured Shopify catalogue
sitemap, not continuously volatile).

## Baseline state expectations

Fresh baseline on first production run, ~9 devices (Nothing-branded only, CMF
deferred), 0 newsroom alerts for that run. Expect confidence values above the
single-evidence baseline (10) for devices confirmed live in multiple regions
— this is legitimate multi-source corroboration, not an anomaly (see
`INTEGRATION_REPORT.md` §F for the exact numbers observed in staging: 10/20/30
for 1/2/3-region confirmation respectively).

## Evidence weight

`SourceType.SUPPORT_PAGE`, weight 10 per region-URL. Same rationale as
Google/OnePlus.

## Health baseline

Adapter classification: LIVE_VALIDATED. 3/3 clean live cycles, 0 HTTP
failures, 0 AMBIGUOUS/INVALID from live data (cleanest of the three
integrated OEMs this session).

## Discord behaviour

Standard rules, same as Google/OnePlus.

## Rollback

```yaml
wave1:
  nothing:
    enabled: false
```

Independent of Google/OnePlus.
