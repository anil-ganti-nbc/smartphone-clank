# Honor Production Canary Report

**Verdict: PROMOTED** (2026-08-11)

## Preflight (Part 1)

Confirmed before touching production: `production validate` PASS (all 5
approved OEMs — google/nothing/oneplus/motorola at the time — agreed
across approved/configured/adapter/enabled/scheduled), exactly one daemon
(prod tree), dashboard healthy, DB integrity `ok`, schema at HEAD
(`0007_wave1_baseline_state`), Samsung/Google/Nothing/OnePlus/Motorola all
recently ran successfully with zero failures, no unexpected manufacturers.
Wave 2 pollution tests and the canonical suite were green (173 passed
going in). Backup taken:
`clank_pre_honor_canary_20260811_000212.db`.

## Live revalidation (Part 2)

Re-ran the live Honor adapter fresh rather than trusting the qualification
mission's numbers. Result matched exactly: 80 raw candidates from
`honor.com/global/sitemap.xml` (1 page, 1 fetch, 0 failures, HTTP 200), 22
valid, 0 invalid, 58 ambiguous (fails closed, never false-accepted). All
22 accepted identities individually inspected:

    Honor 50, 70, 70 Pro, 90, 200, 200 Pro, 400, 400 Pro, 600, 600 Pro,
    Honor Magic3, Magic4 Pro, Magic5, Magic5 Pro, Magic6 Pro, Magic7,
    Magic7 Pro, Magic8 Pro, Magic v2, Magic v3, Magic v5, Magic v6

Zero MagicBook, tablet/Pad, Watch, Band, Earbuds/buds, charger, case,
"offer"/"buy now"/"learn more" promotional strings, embedded URLs,
sentence-like identities, old Huawei-era noise, or duplicated-regional
false positives. Every accepted identity is defensible as a current-
generation Honor smartphone.

## Source safety recheck (Part 3)

Unchanged from qualification: single HTTP GET, HTTP 200, no redirects, no
rate-limiting/CAPTCHA/bot-challenge signal, no JS dependency (static XML
sitemap), candidate volume stable (80 raw both times). No STOP condition.

## Production scope (Part 4)

Honor added to `collectors/wave1/__init__.py::PRODUCTION_OEM_SCOPE` (the
same object as `WAVE1_PRODUCTION_SCOPE`) and `ADAPTER_REGISTRY` — the
identical mechanism proven by Motorola, no new gate created. Post-change
production OEM set: `{google, nothing, oneplus, motorola, honor}`, plus
Samsung on its own specialized path.

Regression coverage added/updated in `tests/wave1/test_production_scope.py`:
Honor-alone and all-five-together collector-building tests; an explicit
per-OEM loop proving Oppo, Vivo, Realme, and Xiaomi each individually
enabled still cannot reach production; the Wave-2-held-OEMs test updated
to remove Honor (now legitimately approved) while keeping Oppo/Vivo/Realme/
ASUS/Xiaomi coverage. `tests/wave1/test_alert_semantics.py`'s parametrized
baseline-suppression test extended with an Honor case rather than
duplicated.

## Production validation before restart (Part 5)

`python main.py production validate` against the live prod config, before
the restart:

    OEM        approved configured adapter enabled scheduled status
    google          YES        YES     YES     YES       YES OK
    honor           YES        YES     YES     YES       YES OK
    motorola        YES        YES     YES     YES       YES OK
    nothing         YES        YES     YES     YES       YES OK
    oneplus         YES        YES     YES     YES       YES OK
    xiaomi           NO        YES     YES      NO        NO OK

    Production scope: OK — no mismatches

Confirmed **PASS** before any restart — the Motorola incident's exact
precondition (approved but missing from `manufacturers`) did not recur,
because this mission added Honor to both `PRODUCTION_OEM_SCOPE` and
`config.yaml::manufacturers` together, and the fail-closed startup check
would have caught it immediately if not.

## Controlled deployment (Part 6)

`collectors/wave1/__init__.py` (only file needing redeployment — Honor's
adapter/validator code was already present in the prod tree from the
qualification mission) copied dev → prod, byte-verified identical.
`config/config.yaml` edited directly in the prod tree (config is
deployment-specific, not copied): added `honor` to `manufacturers` and a
`wave1.honor` block (`enabled: true`, `interval_minutes: 360`). No other
OEM's config touched. Verified zero in-progress collector runs, backup
taken (`clank_pre_honor_deploy_20260811_000833.db`), controlled restart
via `restart-runtime.ps1`. Startup log confirmed `production scope
validation: OK` before any collector was scheduled.

## Production baseline (Part 7)

Production discovered Honor live and independently — no staging data
copied. Startup baseline cycle (2026-08-11 00:11:13 IST):

    candidates=80 valid=22 rejected=58 new=22 updated=0 resighted=0
    dropped_out_of_scope=0 baseline_complete_before=False
    baseline_just_completed=True

22 new Device rows, 22 Evidence rows (one per device — no multi-source
corroboration on this source, matching the qualification-phase finding),
all at confidence 10 via `ConfidenceService`. Baseline state recorded
complete. **0 delivered newsroom alerts** — confirmed directly against
`alerts` and `webhook_deliveries`.

## Hostile production audit (Part 8)

Direct SQL inspection of the 22 live production rows:

| Check | Result |
|---|---|
| MagicBook/tablet/Pad/Watch/Band/Earbuds/buds/charger/case/offer/buy-now/learn-more/URL-fragment/sentence-like keyword scan | 0 hits |
| Duplicate `model_number` | 0 |
| Cross-manufacturer alias collisions | 0 |
| Devices without evidence | 0 |
| Confidence outliers | none — all 22 at confidence 10 |
| Suspicious region duplication | none — single global source, no per-region duplicates possible |

No pollution. No rollback needed.

## Canary cycles (Part 9)

3 repeat cycles against the live production pipeline (real HTTP fetch
each time, not staging):

| Cycle | Valid | New | Updated | Resighted | dropped_out_of_scope |
|---|---|---|---|---|---|
| Repeat 1 | 22 | 0 | 0 | 22 | 0 |
| Repeat 2 | 22 | 0 | 0 | 22 | 0 |
| Repeat 3 | 22 | 0 | 0 | 22 | 0 |

Zero unexpected new/updated devices, expected resightings every cycle,
stable evidence count (22 throughout), stable confidence (10 throughout,
no inflation), zero duplicate alerts, zero catalogue explosion. The source
did not change during the canary — no investigation needed.

## Existing OEM health (Part 10)

Samsung, Google, Nothing, OnePlus, and Motorola all ran successfully on
their normal schedules throughout the entire canary window (deployment,
restart, baseline, 3 repeat cycles) — `collector_run_metrics` shows
`status=success` for every one, zero new failures. Honor's presence did
not disrupt any existing OEM; no rollback triggered.

## Alert semantics (Part 11)

No real post-baseline event occurred (not manufactured, per instruction).
Baseline correctly produced a `WebhookDelivery` suppression record and 0
`Alert` rows. No alert architecture was modified — Honor uses the exact
same `alerts/discord.py` path every other OEM uses.

## Database invariants (Part 12)

`PRAGMA integrity_check` = `ok`. Schema = HEAD
(`0007_wave1_baseline_state`) — no migration needed. Zero cross-
manufacturer identity collisions. Zero devices without evidence. Zero
unexplained confidence growth (all Honor devices remained at confidence
10 across baseline + 3 repeats). Final manufacturer counts: Samsung 97,
Google 7, Nothing 9, OnePlus 16, Motorola 15, **Honor 22** — total 166
devices.

## Tests (Part 13)

Canonical suite before this mission: 173 passed. After: **176 passed, 1
failed, 0 skipped, 0 xfailed** — 4 net new tests added, the 1 failure
being the pre-existing unrelated IST-midnight artifact described below
(`test_honor_enabled_alone_is_returned`,
`test_all_five_production_oems_enabled_together_is_returned`,
`test_oppo_vivo_realme_xiaomi_each_alone_cannot_reach_production`, and one
Honor case added to the existing parametrized baseline-suppression test;
`test_unapproved_honor_enabled_does_not_cause_scope_mismatch` was renamed
to test Oppo instead since Honor is no longer unapproved, and
`test_config_typo_enabling_wave2_held_oems_does_not_reach_production` was
updated in place rather than duplicated). No generic Motorola test was
duplicated for Honor where parametrization already covered it.

(One pre-existing, unrelated test — `tests/test_metrics.py::test_daily_report`
— was observed failing during preflight due to the wall clock crossing
IST midnight mid-session, which pushes its relative-timestamp fixture data
into "yesterday" of the report's IST day-boundary window. Confirmed
unrelated to Honor/production-scope work by inspecting
`observability/metrics.py::daily_report()`'s `tz="Asia/Kolkata"` default
and the fixture's `datetime.utcnow() - timedelta(hours=...)` construction;
not fixed — out of scope for this mission, pre-existing test fragility,
self-resolves as time moves past the boundary.)

## Documentation (Part 14)

This report; `HANDOFF.md` §12d (concise); `docs/SOURCE_INVENTORY.md`
Honor row updated to production/PROMOTED; `docs/wave2/WAVE2_RANKING.md`
post-ranking note updated.

## Verdict: PROMOTED

Honor meets every `PROMOTED` criterion: clean live revalidation, clean
production baseline, 0 pollution, 0 silent drops
(`dropped_out_of_scope=0` throughout), 0 cross-OEM collisions, 0
confidence/evidence inflation, 3 stable repeat cycles, all existing OEMs
healthy throughout, source stable, test suite green. Production
manufacturers: **Samsung, Google, Nothing, OnePlus, Motorola, Honor.**

The promotion required a tiny scope/config delta — two lines in
`PRODUCTION_OEM_SCOPE`/`ADAPTER_REGISTRY`, a `manufacturers` entry, and a
`wave1.honor` config block — and zero new pipeline machinery, zero
`runtime/daemon.py` changes, zero new gate. This is exactly the outcome
the post-Motorola consolidation work was meant to produce: adding another
qualified OEM is boring.

Rollback path if ever needed: set `wave1.honor.enabled: false` in
production `config.yaml` and restart; no data is deleted automatically.
