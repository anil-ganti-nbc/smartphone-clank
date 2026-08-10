# Realme Production Canary Report

**Verdict: PROMOTED** (2026-08-11)

## Recon update that unblocked promotion

Prior qualification (61, RESEARCH_MORE) only sampled `realme.com/sitemap-eu.xml`
(3 devices). This mission checked `realme.com/sitemap-in.xml` (India,
Realme's largest single market): 80 entries, all current-generation
(15/15T/15x/16/16 Pro/16 Pro Plus/16T series, GT7, Narzo/P-series),
`lastmod` July 2026. The promotional-text risk the mission flagged for
Realme was confirmed real (`realme.com/in/` landing page: "Camera Powered
by RICOH GR", CTAs, audio products) but only on the landing page, never in
sitemap slugs — the sitemap remains the correct, clean discovery source.
See `docs/wave2/realme.md` and `docs/wave2/BBK_SOURCE_COMPARISON.md`.

## Live qualification

52 raw candidates (India + EU regions), 22 valid, 30 rejected (fail-closed
AMBIGUOUS/INVALID — unrecognized suffix variants like `14t`/`15t`/`15x`,
P-series models not yet in the validator's grammar, a GT7 special-edition
collab slug, "realme Phones"/"realme Band"/"realme Ui" landing/non-phone
pages; `pre_filter` caught "realme Watch" and "realme Buds Air Neo"
explicitly). All 22 accepted identities individually inspected — every
one a genuine current-generation Realme phone (numbered/C/GT/Narzo
series). Zero band/watch/buds/charger/case/promo pollution, zero
cross-brand contamination.

## Source safety

SAFE. 2 pages requested (India + EU sitemaps), 2 fetched, 0 failures,
HTTP 200, no CAPTCHA/rate-limit/bot-challenge signal.

## Shared plumbing decision

No BBK abstraction built — see `docs/wave2/BBK_SOURCE_COMPARISON.md`.
Realme's adapter/validator follow the identical `collectors/wave1/*`
contract every other OEM already uses.

## Staging qualification

Real pipeline, temp SQLite: baseline + 2 repeat cycles, 22 valid every
cycle, 0 drift, 0 cross-OEM collisions against existing staging data
(including Oppo, promoted the same mission), 0 alerts.

## Production scope

Added to `PRODUCTION_OEM_SCOPE`/`ADAPTER_REGISTRY`/`INTEGRATED_OEMS` —
the same mechanism every prior promotion used. `python main.py production
validate` showed clean agreement for Realme before the restart.

## Production baseline

52 candidates, 22 valid, 0 rejected-as-pollution, `dropped_out_of_scope=0`,
22 new devices, 22 evidence rows, all confidence 10, baseline completed,
**0 delivered newsroom alerts**.

## Hostile production audit

Direct SQL inspection of all 22 live rows: 0 pollution-keyword hits
(band/watch/buds/charger/case/promo/RICOH), 0 duplicate model numbers, 0
cross-manufacturer alias collisions, 0 devices without evidence. No
rollback needed.

## Canary cycles

3 repeat cycles against the live production pipeline: 22 valid / 0 new /
0 updated / 22 resighted / `dropped_out_of_scope=0` every time. Stable
evidence (22) and confidence (all 10) throughout.

## Existing OEM health

Samsung, Google, Nothing, OnePlus, Motorola, Honor, and Oppo all ran
successfully on their normal schedules throughout deployment, restart,
baseline, and all 3 repeat cycles — zero new failures.

## Database invariants

`PRAGMA integrity_check` = `ok`. Schema unchanged (HEAD
`0007_wave1_baseline_state`). Final manufacturer counts: Samsung 97,
Google 7, Nothing 9, OnePlus 16, Motorola 15, Honor 22, Oppo 73,
**Realme 22** — total 261 devices.

## Verdict: PROMOTED

Clean live revalidation, clean production baseline, 0 pollution, 0 silent
drops, 0 cross-OEM collisions, 0 confidence/evidence inflation, 3 stable
repeat cycles, all seven pre-existing OEMs healthy throughout, source
stable. Production manufacturers: **Samsung, Google, Nothing, OnePlus,
Motorola, Honor, Oppo, Realme** — 8 total.

`wave1.realme.enabled: true`, `interval_minutes: 360`, in production
`config.yaml`, scoped to India + EU regional sitemaps. Rollback path if
needed: set `enabled: false` and restart; no data deleted automatically.
