# Wave 1 Promotion Report

Companion to `docs/wave1/INTEGRATION_REPORT.md`. This document has the exact
per-OEM numbers and the independent promotion verdicts. **No collector was
enabled in production as a result of this report** — verdicts are engineering
recommendations for the operator to act on.

**Update 2026-08-10 (production canary phase)**: Google's verdict below was
acted on — see `docs/wave1/GOOGLE_CANARY_REPORT.md` for the full canary,
verification, and the **PROMOTED** result.

**Update 2026-08-10 (second canary phase, same day)**: Nothing's verdict was
also acted on, reusing the exact machinery Google's canary proved — see
`docs/wave1/NOTHING_CANARY_REPORT.md` for the full canary and the
**PROMOTED** result.

**Update 2026-08-10 (third canary phase, same day)**: OnePlus's verdict was
also acted on, reusing the same machinery a third time — see
`docs/wave1/ONEPLUS_CANARY_REPORT.md` for the full canary and the
**PROMOTED** result. Wave 1 production expansion is now complete: Samsung,
Google, Nothing, and OnePlus are all in production. Xiaomi remains
`KEEP_STAGING`, deliberately excluded and untouched.

## Google

```text
Discovery source:            store.google.com/us/category/phones
Source role:                 discovery + monitoring
Region(s):                   us (only — see limitations)
Baseline criterion:          single full enumeration (source is fetched whole every run)
Baseline completed:          yes, cycle 1
Devices/candidates accepted: 7 (Pixel 9, Pixel 9a, Pixel 10, Pixel 10 Pro,
                              Pixel 10 Pro Fold, Pixel 10a, Pixel 11)
Candidates rejected:         0
Evidence rows:                7 (1 per device)
Repeat cycles:                3 (live, real source)
Resightings:                  7 per repeat cycle (cycles 2 and 3), 0 new/updated
Duplicate evidence:           0
Confidence anomalies:         none — flat 10 across all 7 (single support-page-tier evidence each)
Restart test:                 pass (fixture-controlled, tests/wave1/test_integration.py)
Failure tests:                 pass (403/429/500/timeout via fixture; live source stayed 200 across all 3 real cycles this session)
Staging Discord:              demonstrated (docs/wave1/sample_staging_alert.txt, using this exact device shape)
Production Discord attempts:  0 (test_discord_safety.py, instrumented transport)
Hostile DB audit:             clean — 0 suspicious words, 0 duplicates, 0 evidence-less devices
Source health:                LIVE_VALIDATED source, adapter LIVE_VALIDATED, 3/3 clean runs
Recommended polling:          30-60 min. Rationale: store category pages are marketing-controlled
                              and low-volatility day-to-day, but this is exactly the source that
                              surfaced the Pixel 11 teaser ahead of any dedicated product page —
                              news value justifies a shorter interval than a typical static catalogue page.
Promotion verdict:            PROMOTE_WITH_CONDITIONS
```

**Conditions**: (1) build the staging→production resolver/evidence bridge
does not yet exist as a *production* code path — today's integration is
staging-only by construction (`runtime/environment.py` guard). Promoting
means deliberately enabling this same adapter+bridge+baseline machinery
against production, which is a distinct operator decision from "engineering
recommends it." (2) Expand beyond `/us/` region before treating catalogue
coverage as complete (recon documented ~40 regional storefronts). (3) The
OTA/factory-image acknowledgment-wall block (recon) remains unresolved —
does not block this promotion tier (discovery doesn't depend on it) but
should be revisited before relying on OTA data for anything.

## OnePlus

```text
Discovery source:            oneplus.com/us/sitemap.xml
Source role:                 discovery + weak monitoring
Region(s):                   us (only — see limitations)
Baseline criterion:          single full enumeration
Baseline completed:          yes, cycle 1
Devices/candidates accepted: 16 (OnePlus 13/13R/12/12R/Open/11/10T/9/8T,
                              Nord 100/10-5G/20-5G/30-5G/200-5G, ...)
Candidates rejected:         1 ("OnePlus featuring" — nav-page slug noise, correctly AMBIGUOUS not VALID)
Evidence rows:                16
Repeat cycles:                3 (live, real source)
Resightings:                  16 per repeat cycle, 0 new/updated
Duplicate evidence:           0
Confidence anomalies:         none — flat 10 across all 16
Restart test:                 pass
Failure tests:                 pass (fixture); live source returned 200 all 3 real cycles
Staging Discord:              covered by the same code path as Google/Nothing (test_discord_safety.py is source-agnostic)
Production Discord attempts:  0
Hostile DB audit:             clean
Source health:                LIVE_VALIDATED source, adapter LIVE_VALIDATED, 3/3 clean runs
Recommended polling:          1-2 h. Rationale: sitemap regenerates on deploy, not continuously;
                              146-URL flat file is cheap to poll but not news-volatile day to day.
Promotion verdict:            PROMOTE_WITH_CONDITIONS
```

**Conditions**: (1) same staging→production bridge gap as Google. (2) No
first-party source was found anywhere (recon) that exposes OnePlus's `CPH####`
internal model codes — this adapter is marketing-name-slug-only by design;
if CPH-level identity is ever a hard requirement, that's separate unsolved
work, not a blocker for marketing-name-level discovery. (3) Widen the
non-product-path denylist in `collectors/wave1/oneplus/discovery.py` — one
nav-page slug leaked through as AMBIGUOUS (harmless, but noisy) this session.
(4) `/global/sitemap.xml` is confirmed stale since ~2023 — never add it as a
fallback source without re-verifying freshness first.

## Nothing

```text
Discovery source:            nothing.tech + us./in. regional products sitemaps
Source role:                 discovery + weak monitoring
Region(s):                   uk (default), us, in
Baseline criterion:          single full enumeration (all 3 regions, per run)
Baseline completed:          yes, cycle 1
Devices/candidates accepted: 9 (Phone (1)/(2)/(3)/(3a)/(3a) Lite/(3a) Pro/(4a)/(4a) Pro/(4b))
                              — includes CMF Phone 1, which was correctly
                              routed to RejectedCandidate (deferred manufacturer
                              schema decision) rather than merged into "nothing"
Candidates rejected:         1 (CMF Phone 1, deferred per spec instruction — not a defect)
Evidence rows:                21 (multi-region corroboration: several devices
                              confirmed live in 2-3 of the 3 regions polled,
                              each region contributing independent evidence)
Repeat cycles:                3 (live, real source)
Resightings:                  21 per repeat cycle, 0 new/updated
Duplicate evidence:           0 (same device+region+URL never double-counted)
Confidence anomalies:         none — 10/20/30 exactly matching 1/2/3-region corroboration, no outliers
Restart test:                 pass
Failure tests:                 pass (fixture); live source returned 200 all 3 real cycles
Staging Discord:              covered (source-agnostic code path)
Production Discord attempts:  0
Hostile DB audit:             clean — cleanest of the three (0 AMBIGUOUS, 0 INVALID from live data)
Source health:                LIVE_VALIDATED source, adapter LIVE_VALIDATED, 3/3 clean runs
Recommended polling:          1-2 h. Rationale: same reasoning as OnePlus — structured catalogue,
                              not continuously volatile.
Promotion verdict:            PROMOTE_WITH_CONDITIONS
```

**Conditions**: (1) same staging→production bridge gap. (2) CMF schema
decision (`manufacturer=cmf` vs `parent_brand=Nothing` vs something else)
must be made before CMF candidates can ever become real Device rows — until
then they correctly stay in `RejectedCandidate` forever, which is safe but
means CMF Phone 1 (a real, live, India-region product) is invisible to the
catalogue. Not a blocker for promoting the Nothing-branded-phone portion of
this source. (3) `support.nothing.tech` (Zendesk) stayed 403-blocked in
recon; not used, not a blocker.

## Xiaomi

```text
Status: KEEP_STAGING (unchanged from Wave 1)
```

Not integrated into the shared pipeline this phase, per explicit operator
instruction. Its adapter (`collectors/wave1/xiaomi/discovery.py`) and
validator remain exercised via `tests/wave1/test_validators.py` and
`tests/wave1/test_pollution_cannot_recur.py` only. Live confirmation this
session that KEEP_STAGING remains the right call: `mi.com/global/sitemap/`
returned HTTP 403 on this session's second live run and HTTP 200 on the
third — the exact 200⇄403 instability pattern that justified quarantine in
the first place, observed again independently. No workaround was attempted.

## Rollback design (spec section 49)

Each OEM's production enablement is a single, independent config change —
see `docs/wave1/promotion/{google,oneplus,nothing}.md` for the exact deltas.
To disable one OEM without touching the others:

```yaml
# config/config.yaml (production) — disabling Google only
wave1:
  google:
    enabled: false   # oneplus/nothing untouched
```

No global "kill all Wave 1 collectors" switch is required or provided — each
`collectors.wave1.ADAPTER_REGISTRY` entry is independently gated by its own
`wave1.<oem>.enabled` config key (mirrors the existing per-collector
`enabled:` pattern in `config/config.yaml` used for every other collector).
To quarantine bad rows by provenance if a parser regression ever escapes to
production: `SELECT * FROM devices WHERE manufacturer = '<oem>' AND id IN
(SELECT device_id FROM evidence WHERE source = '<source_id>')` — inspect
before deleting; no destructive auto-cleanup is implemented or recommended
(spec section 49 explicitly prohibits building one).

## Final verdicts

| OEM | Verdict |
|---|---|
| Google | **PROMOTED** (2026-08-10 — see `docs/wave1/GOOGLE_CANARY_REPORT.md`) |
| Nothing | **PROMOTED** (2026-08-10 — see `docs/wave1/NOTHING_CANARY_REPORT.md`) |
| OnePlus | **PROMOTED** (2026-08-10 — see `docs/wave1/ONEPLUS_CANARY_REPORT.md`) |
| Xiaomi | KEEP_STAGING (held — source oscillated 200/403 during qualification) |

**Wave 1 production expansion is complete.** All four qualified OEMs
(Samsung + Google + Nothing + OnePlus) are live in production. Xiaomi is the
only OEM not promoted, by deliberate operator decision — its source's
qualification instability (HTTP 200/403 oscillation) is a source-quality
problem, not something Wave 1's architecture attempted to work around. Which
manufacturers belong in a future Wave 2 is a separate, not-yet-scoped
decision.
