# Wave 2 Qualification Report

Mission: qualify Motorola, Oppo, Vivo, Realme, Honor, ASUS/ROG as candidate
manufacturers for a future production canary. **No promotions happen in
this mission** — see Phase 19 proof below. Xiaomi untouched (KEEP_STAGING,
out of scope). Wave 1 production (Samsung, Google, Nothing, OnePlus)
untouched.

## Phase 0 — pre-mission health check

Confirmed before any Wave 2 work began: exactly one production daemon
(PID 4912, `smartphone-clank-prod`), DB integrity `ok`, schema at Alembic
HEAD (`0007_wave1_baseline_state`), all 4 production sources recently
succeeded with zero failures, canonical suite **150 passed, 0 failed, 0
skipped, 0 xfailed**.

## Phase 1 — alert-path integration proof

New file `tests/wave1/test_alert_lifecycle_e2e.py` (2 tests, offline,
mocked transport, temp SQLite) proves the full mocked lifecycle end to end
through the real pipeline with exact column-level assertions at every step:
baseline suppression -> WebhookDelivery-only, new device -> WebhookDelivery
+ exactly 1 Alert with a delivered message ID, resighting -> no duplicate
Alert/WebhookDelivery, and separately the failure branch (attempted,
not delivered, 0 Alert rows, retry does not duplicate intelligence).

Found and fixed a flaky-test bug in the process: `webhook_deliveries.id` is
a UUID, not sequential — `ORDER BY id` was sorting lexically, causing
intermittent row-order mismatches. Not a product bug; fixed by ordering on
`created_at`. New canonical baseline after this phase: **152 passed**.

## Phases 2-5 — contract, recon, source matrix

- `docs/wave2/WAVE2_QUALIFICATION_CONTRACT.md` — the six-dimension scoring
  framework (Discovery/Identity/Safety/Editorial/Regional-novelty/Cost),
  applied identically to all six OEMs.
- Per-OEM recon: `docs/wave2/{motorola,honor,oppo,vivo,realme,asus_rog}.md`.
  robots.txt + sitemap probing, 1-3 requests per source family, zero
  403/429/CAPTCHA encountered across all six OEMs.
- `docs/wave2/WAVE2_SOURCE_MATRIX.md` — consolidated table.

Headline finding: **ASUS publicly exited the smartphone business as of
early 2026** (chairman Jonney Shih, multiple outlets) — no new Zenfone or
ROG Phone models planned. This was not knowable from source-quality
inspection alone and caps ASUS's score regardless of how clean its sitemap
structure is.

## Phases 6-7 — validators + pollution regression

Six deterministic validators (`collectors/wave2/<oem>/model_validator.py`),
same contract as Wave 1 (`collectors/wave1/validator.py`), reusing the
shared `pre_filter` hostile-text heuristics. `tests/wave2/test_wave2_pollution_cannot_recur.py`
(5 tests) proves every validator rejects a hostile corpus (promo copy, nav
chrome, cookie banners, accessories, audio/wearables/tablets, and the
mission's named special cases: ASUS rejects PC hardware specifically, Vivo
never treats iQOO as a Vivo identity, Motorola rejects Lenovo PC products)
while still accepting genuine phone model names. New canonical baseline:
**157 passed**.

## Phases 8-9 — staging adapters

Built for the two OEMs recon supported as BUILD_NOW:
**Motorola** (`collectors/wave2/motorola/discovery.py`, regional sitemap,
SKU-grade identity) and **Honor** (`collectors/wave2/honor/discovery.py`,
global sitemap, path-isolated `/phones/`). Both use the existing Wave 1
`DiscoveryAdapter` contract and `run_oem_staging_cycle` bridge — no new
architecture. Extended `collectors/wave1/staging_pipeline.py::_validator_for`
and `models/schemas.py::Manufacturer` additively (new enum members, no DB
migration — `Device.manufacturer` is a plain string column) to admit the
two new OEMs into the existing pipeline. `config/config.staging.yaml`'s
manufacturer allowlist extended to include `motorola`/`honor`.

Oppo, Vivo, Realme, and ASUS did **not** receive adapters this mission —
Oppo/Vivo/Realme scored CONTINUE_STAGING/RESEARCH_MORE (recon-only
findings, not yet BUILD_NOW-grade evidence), and ASUS is REJECT. This is a
narrower build scope than the mission's original candidate pool of "up to
4 adapters" might have implied; documented explicitly here rather than
building throwaway adapters for sources recon flagged as needing more
work first.

## Phases 10-13 — staging baseline, repeatability, collision audit

One live fetch per adapter (124 raw Motorola candidates from 3 regional
sitemaps, 80 raw Honor candidates from the global sitemap — well within
the "1 index + a few detail requests" discipline). Fetched candidates
replayed through the real staging pipeline for baseline + 2 repeat cycles
(no additional live requests on repeat cycles, by design):

| OEM | Cycle | Valid | Rejected | New | Updated | Resighted | Alerts |
|---|---|---|---|---|---|---|---|
| Motorola | 1 (baseline) | 18 | 106 | 15 | 3 | 0 | 0 |
| Motorola | 2 (repeat) | 18 | 106 | 0 | 0 | 18 | 0 |
| Motorola | 3 (repeat) | 18 | 106 | 0 | 0 | 18 | 0 |
| Honor | 1 (baseline) | 22 | 58 | 22 | 0 | 0 | 0 |
| Honor | 2 (repeat) | 22 | 58 | 0 | 0 | 22 | 0 |
| Honor | 3 (repeat) | 22 | 58 | 0 | 0 | 22 | 0 |

Stable across repeats: identical valid/rejected counts, zero new devices
after baseline, zero evidence explosion, zero alerts (correct — baseline
imports are always backfill-suppressed). Cross-OEM collision audit (SQL
query across `devices.model_number` and `aliases.value` grouped by value,
filtered to >1 distinct manufacturer): **zero collisions** between
Motorola, Honor, and the three existing staging-proven Wave 1 OEMs
(Google/OnePlus/Nothing) sharing the same database.

Known validator gap, honestly reported rather than hidden: Motorola's raw
candidates included ~106 rejections per cycle, mostly `AMBIGUOUS` from a
still-imperfect slug-to-marketing-name normalizer (e.g. a family-prefix
duplication bug produces malformed strings like "Edge Edge 2026" for some
slug shapes) — these fail closed (never false-accepted) but undercount
real devices. Honor has a similar minor gap (X-series models like "Honor
X9d" aren't yet in the validator's grammar, also fails closed). Both are
staging-only findings; neither caused a false accept in the pollution
regression suite or the live baseline run.

## Phases 14-16 — editorial signal, novelty, polling recommendations

- **Motorola**: baseline included `razr-2026`, `moto-g-2026`,
  `moto-g-power-2026` — current-generation, CURRENT/RECENT classification.
  Recommend 2-4 polls/day on a handful of regions (US, GB, DE) rather than
  all 51 regional sitemaps every cycle — the sitemap is a static enumerable
  list, not a frequently-changing feed.
- **Honor**: baseline included `honor-magic8-pro`, `honor-magic-v6` —
  CURRENT/RECENT. Recommend 2-4 polls/day on `/global/` only; `/cn/` not
  evaluated, do not add without a dedicated stale-catalogue check first.
- **Oppo/Vivo/Realme**: not baselined this mission; polling
  recommendations deferred to their own follow-up recon (see Ranking doc).
- **ASUS**: no polling recommended — REJECT.

## Phase 17-18 — ranking and promotion readiness

See `docs/wave2/WAVE2_RANKING.md` for full scoring. Verdicts:

    Motorola   84  PROMOTE_WITH_CONDITIONS
    Honor      76  PROMOTE_WITH_CONDITIONS
    Oppo       66  CONTINUE_STAGING
    Vivo       63  RESEARCH_MORE
    Realme     61  RESEARCH_MORE
    ASUS/ROG   55  REJECT

**No promotions occur in this mission.** `PROMOTE_WITH_CONDITIONS` is a
recommendation for a future, separate canary mission — same as Wave 1's
process for Google/Nothing/OnePlus, each of which got its own dedicated
promotion mission after a WAVE1_REPORT.md verdict, not an automatic
promotion.

## Phase 19 — production invariance proof

Checked immediately after all Wave 2 staging work completed:

| Check | Result |
|---|---|
| Production manufacturer counts | Samsung 97, Google 7, Nothing 9, OnePlus 16 — **unchanged** from Phase 0 |
| Wave 2 rows in production `devices` | **0** |
| Production `alerts` count | 129 (pre-existing historical rows, unchanged) |
| Production `webhook_deliveries` count | 5 (pre-existing synthetic-test rows, unchanged) |
| Production schema | `0007_wave1_baseline_state` — unchanged, no migration needed this mission |
| Production daemon count | 1 (PID 4912, running from `smartphone-clank-prod`) |
| DB integrity | `ok` |
| `WAVE1_PRODUCTION_SCOPE` | `{"google", "nothing", "oneplus"}` — unchanged |

All Wave 2 work (staging adapters, live discovery, baseline runs, repeat
cycles) ran against temporary/staging SQLite databases created ad hoc for
this mission, never `smartphone-clank-prod`'s database.

## Phase 20 — final test count

Canonical suite (`PYTHONPATH=. python -m pytest -q`):

    157 passed, 0 failed, 0 skipped, 0 xfailed

(150 baseline at mission start + 2 alert-lifecycle tests (Phase 1) + 5
Wave 2 pollution-regression tests (Phase 6-7). No Wave 2 staging-run script
above is itself a pytest test — those were exploratory recon scripts,
consistent with Wave 1's own recon-vs-test distinction.)

## Phase 21 — documentation

This report, `WAVE2_QUALIFICATION_CONTRACT.md`, `WAVE2_SOURCE_MATRIX.md`,
`WAVE2_RANKING.md`, and six per-OEM recon docs are all new under
`docs/wave2/`. No Wave 1 report was overwritten. `HANDOFF.md` updated
separately with a pointer to this phase (see next commit).
