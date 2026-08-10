# Oppo Production Canary Report

**Verdict: PROMOTED** (2026-08-11)

## Recon update that unblocked promotion

Prior qualification (66, CONTINUE_STAGING) used `oppo.com/en/smartphones/`
— a curated category page, not a true sitemap. This mission decomposed
`oppo.com/sitemap.xml` (a 134+-entry regional sitemap index) and found
`oppo.com/en/sitemap.xml`: a true enumerable sitemap with clean
category-path isolation (`/en/smartphones/` vs `/en/accessories/`,
`/en/tablets/`, `/en/wearables/`, `/en/audio/`, `/en/routers/`). See
`docs/wave2/oppo.md` and `docs/wave2/BBK_SOURCE_COMPARISON.md`.

## Live qualification

99 raw candidates, 73 valid, 26 rejected (fail-closed AMBIGUOUS/INVALID —
letter-suffix A-series variants like A17k/A6t, Reno Z/T variants, a
"Find X3 Series" landing-page slug; zero false accepts). All 73 accepted
identities individually inspected — every one a genuine Oppo Find X/Find
N/Reno/A series phone, including current flagships (Find X9, X9 Pro, X9
Ultra). Zero pad/watch/earbud/router/charger/case/promo/navigation
pollution, zero cross-brand contamination.

A bug was found and fixed during adapter construction: the initial
slug-to-candidate parser silently produced zero candidates for the entire
Find X/Find N family (a token-splitting bug on the two-word
`find-x`/`find-n` family segments) — caught by manual inspection before
any staging or production run, not a silent-drop incident.

## Source safety

SAFE. 1 page requested, 1 fetched, 0 failures, HTTP 200, no
CAPTCHA/rate-limit/bot-challenge signal.

## Shared plumbing decision

No BBK abstraction built — see `docs/wave2/BBK_SOURCE_COMPARISON.md`.
Oppo's adapter/validator follow the identical `collectors/wave1/*`
contract every other OEM (Motorola, Honor, etc.) already uses.

## Staging qualification

Real pipeline, temp SQLite: baseline + 2 repeat cycles, 73 valid every
cycle, 0 drift, 0 cross-OEM collisions against existing Google/OnePlus/
Nothing/Motorola/Honor staging data, 0 alerts.

## Production scope

Added to `PRODUCTION_OEM_SCOPE`/`ADAPTER_REGISTRY`/`INTEGRATED_OEMS` —
the exact mechanism Motorola and Honor proved, zero new gates.
`python main.py production validate` showed clean agreement for Oppo
before the restart.

## Production baseline

99 candidates, 73 valid, 0 rejected-as-pollution, `dropped_out_of_scope=0`,
73 new devices, 73 evidence rows (1 per device, no multi-region
corroboration on this single-region source), all confidence 10, baseline
completed, **0 delivered newsroom alerts**.

## Hostile production audit

Direct SQL inspection of all 73 live rows: 0 pollution-keyword hits, 0
duplicate model numbers, 0 cross-manufacturer alias collisions, 0 devices
without evidence. No rollback needed.

## Canary cycles

3 repeat cycles against the live production pipeline: 73 valid / 0 new /
0 updated / 73 resighted / `dropped_out_of_scope=0` every time. Stable
evidence (73) and confidence (all 10) throughout.

## Existing OEM health

Samsung, Google, Nothing, OnePlus, Motorola, and Honor all ran
successfully on their normal schedules throughout deployment, restart,
baseline, and all 3 repeat cycles — zero new failures.

## Database invariants

`PRAGMA integrity_check` = `ok`. Schema unchanged (HEAD
`0007_wave1_baseline_state`). Final manufacturer counts: Samsung 97,
Google 7, Nothing 9, OnePlus 16, Motorola 15, Honor 22, **Oppo 73** —
total 239 devices.

## Verdict: PROMOTED

Clean live revalidation, clean production baseline, 0 pollution, 0 silent
drops, 0 cross-OEM collisions, 0 confidence/evidence inflation, 3 stable
repeat cycles, all six pre-existing OEMs healthy throughout, source
stable. Production manufacturers: **Samsung, Google, Nothing, OnePlus,
Motorola, Honor, Oppo.**

`wave1.oppo.enabled: true`, `interval_minutes: 360`, in production
`config.yaml`. Rollback path if needed: set `enabled: false` and restart;
no data deleted automatically.
