# Wave 1 Report — Multi-OEM Expansion

Date: 2026-08-10. Scope: Google, OnePlus, Nothing, Xiaomi discovery adapters,
built and hostile-audited against real live sources, entirely in a new
isolated staging environment. No production data touched (verified below).

## What was actually built this session

- **Staging environment**: `--environment staging`, `config/config.staging.yaml`,
  `data/clank-staging.db`, hard path-pattern guards in `runtime/environment.py`
  (`assert_db_matches_environment`, `assert_safe_to_destroy`) that fail closed
  in both directions — a staging run cannot open a production-shaped DB path
  and vice versa. `main.py reset-staging` refuses anything that isn't a
  staging path. Staging Discord only ever reads `STAGING_DISCORD_WEBHOOK_URL`,
  never the production webhook env vars.
- **Samsung golden-state baseline**: `docs/wave1/SAMSUNG_GOLDEN_STATE.md` —
  97 devices, 100% Samsung, 98 evidence rows, 0 rejected candidates, captured
  and backed up (`data/backups/clank_pre_wave1_20260810_140158.db`) before any
  Wave 1 change.
- **Canonical test baseline**: `PYTHONPATH=. python -m pytest -q` → fixed one
  stale pre-existing test (renamed API import, no behavior change), now
  **93 passed, 0 failed, 0 skipped, 0 xfailed** (81 pre-existing + 12 new Wave 1 tests).
- **Source reconnaissance**: `docs/wave1/{google,oneplus,nothing,xiaomi}_recon.md`,
  every candidate URL actually fetched live and classified, synthesized into
  `docs/wave1/SOURCE_MATRIX.md`.
- **`DiscoveryAdapter`/`DiscoveryResult` contract** (`collectors/wave1/adapter.py`)
  — deliberately a different type from `models.schemas.Discovery`, so a Wave 1
  candidate cannot be accidentally wired into the production
  resolver/evidence/confidence pipeline without an explicit new bridge.
- **Strict OEM validators** (`collectors/wave1/{google,oneplus,nothing,xiaomi}/model_validator.py`),
  VALID/INVALID/AMBIGUOUS with recorded rejection reasons, "reject over false-accept."
- **Negative fixture corpus** (`fixtures/wave1/`) reconstructed from the
  August 2026 incident report's quoted examples (`"PIXEL 11 SERIES AND
  RECEIVE AN EXCLUSIVE OFFER..."`, `"ONEPLUSSHOP"`), plus synthetic marketing
  pages that were verified to make the *actual old* `collectors/generic_support.py`
  regex extract that exact class of garbage.
- **`test_v038_pollution_cannot_recur`** (`tests/wave1/test_pollution_cannot_recur.py`,
  release-blocking, permanent): replays the old regex against the fixture
  pages and the incident-derived corpus, and asserts every OEM validator
  rejects all of it while still correctly accepting the genuine model names
  embedded in the same pages.
- **Four live discovery adapters** (`collectors/wave1/{oem}/discovery.py`),
  each fetching a real official source and extracting candidates structurally
  (sitemap `<loc>`/anchor slugs, or launch-intent-anchored teaser text) —
  never blanket regex-over-page-prose.

## Live results (this session, real HTTP, staging-only, zero DB writes)

| OEM | Source fetched | Fetched OK | Candidates | VALID | AMBIGUOUS | INVALID (garbage) |
|---|---|---|---|---|---|---|
| Google | `store.google.com/us/category/phones` | 1/1 | 7 | **7** | 0 | 0 |
| OnePlus | `oneplus.com/us/sitemap.xml` | 1/1 | 17 | 16 | 1 | 0 |
| Nothing | `nothing.tech` + `us.`/`in.` regional products sitemaps | 3/3 | 22 | **22** | 0 | 0 |
| Xiaomi | `mi.com/global/sitemap/` | 1/1 (intermittently 403 — see below) | 24 | 21 | 3 | 0 |

**Zero INVALID (garbage) candidates across all four OEMs, across repeated runs.**
The 1 OnePlus and 3 Xiaomi AMBIGUOUS candidates are safe-by-design gaps in
validator grammar coverage (an unfiltered nav-page slug, and Xiaomi's newer
"Redmi A-series" naming which the current validator doesn't yet recognize) —
never false accepts. Repeat-run idempotency confirmed (identical candidate
sets across two consecutive live fetches per OEM).

Google's adapter reproduced the exact live finding from recon: the "Pixel 11"
pre-order teaser, a genuinely uncatalogued device, discovered from
`store.google.com/us/category/phones` teaser text anchored to launch-intent
language ("Be the first to know... Pixel 11 Series").

Xiaomi's source returned HTTP 403 (Akamai) on one run and 200 on the very
next run of this session — live confirmation of the recon's "adaptive/unstable
bot detection" finding. This is real operational evidence the source is not
yet reliable enough for unattended scheduling.

Production `data/clank.db` device count verified unchanged (97, 100% Samsung)
before and after every adapter run in this session; staging `data/clank-staging.db`
has 0 devices, because **no adapter output was wired into
entity_resolution/evidence/confidence in this session** — see Scope boundary below.

## Scope boundary — what was NOT done this session

Wave 1 adapters + validators are proven correct at the candidate layer (real
live discovery, strict rejection, idempotent, zero garbage). They are **not**
wired into the shared resolver/evidence/confidence pipeline that Samsung uses
— that bridge (`DiscoveryResult` + `ValidationOutcome` → `models.schemas.Discovery`
→ existing pipeline, staging-scoped) is real remaining work, not yet built.
Consequently:
- No staging `Device`/`Evidence`/`confidence_ledger` rows exist yet for any
  Wave 1 OEM — `test_v038_pollution_cannot_recur` proves the validator layer
  rejects the incident's garbage shapes; it does not yet prove the DB-layer
  assertion (0 devices/evidence/confidence/alerts) end-to-end, because that
  layer doesn't exist yet for Wave 1. The test file documents this explicitly
  and must be extended once the bridge is built, not weakened.
- No staging dashboard view or analyst review queue was added (spec sections
  39–40) — out of scope for this pass given the above is the harder
  prerequisite.
- Baseline-epoch persistence (spec 22–23) has no concrete implementation yet
  — there's no staging DB write path to attach it to.
- OTA/firmware monitoring sources (Google factory-images/OTA acknowledgment
  wall, Nothing community changelog affiliation) remain unresolved per recon
  and were not pursued further (both correctly flagged BLOCKED/UNVERIFIED
  rather than worked around).

## Promotion recommendations

None of the four are recommended for **production** enablement yet — that
requires the resolver/evidence bridge above and a longer staging soak (spec
section 37's full checklist), neither of which exists yet. Recommendations
below are about staging-readiness and discovery-source quality, which is what
this session could actually prove.

| OEM | Discovery source | Live status | Recommendation |
|---|---|---|---|
| **Google** | `store.google.com/category/phones` | LIVE_VALIDATED | **PROMOTE_WITH_CONDITIONS** — strongest of the four; real pre-release discovery demonstrated twice (recon + this session, same "Pixel 11" teaser). Condition: build the resolver/evidence bridge and run a multi-day staging soak before any production consideration; also expand region coverage beyond `/us/` per recon. |
| **OnePlus** | `oneplus.com/{region}/sitemap.xml` | LIVE_VALIDATED | **PROMOTE_WITH_CONDITIONS** — clean, stable, structured, zero garbage. Condition: same bridge/soak requirement; also widen the non-product-path denylist (minor noise observed, e.g. one nav-page slug) and decide whether CPH-code enrichment is required before considering this "done" for entity identity purposes (currently marketing-name-slug only, matches recon's honest assessment that no first-party CPH source exists). |
| **Nothing** | `nothing.tech/sitemap/products/1.xml` (+regions) | LIVE_VALIDATED | **PROMOTE_WITH_CONDITIONS** — cleanest result of all four (100% VALID, zero AMBIGUOUS, correctly caught the region-exclusive CMF Phone 1 in India). Condition: same bridge/soak requirement; resolve the CMF `manufacturer` vs `parent_brand` schema question (deliberately left open per spec section 16) before it starts writing real rows. |
| **Xiaomi** | `mi.com/global/sitemap/` (HTML, no XML sitemap exists) | PROMISING, adapter EXPERIMENTAL | **KEEP_STAGING** — weakest source of the four by construction (recon found no XML sitemap and no page anywhere exposing a real model number), and this session directly observed intermittent 403 blocking on the same source within one run. Do not schedule unattended. Worth periodically re-checking `mi.com/global/support/terms/declaration/` (recon's flagged untested lead) and treat as an ongoing research item rather than a near-term production candidate. |

**Geekbench**: not used, not investigated, per standing instruction — this
decision was not revisited.

## Regression status

`PYTHONPATH=. python -m pytest -q` → **93 passed, 0 failed, 0 skipped, 0 xfailed**
(Samsung's own tests, `test_production_scope.py`, and `test_v038_scope.py` all
still pass unmodified — Wave 1 added tests, it did not touch Samsung's shared
core logic). Samsung golden-state numbers (97 devices, 100% Samsung, 98
evidence) verified unchanged after every Wave 1 adapter run this session.

## Recommended next session

1. Build the staging-only bridge: `ValidationOutcome(VALID)` → `models.schemas.Discovery`
   → existing `entity_resolution`/evidence/confidence pipeline, scoped so it can
   only ever target a staging `session_factory` (reuse `runtime/environment.py`'s
   guard at the bridge's construction point, not just at CLI startup).
2. Re-run `test_v038_pollution_cannot_recur` with a real staging-DB assertion
   (0 devices/evidence/confidence/alerts for the negative corpus) once that
   bridge exists — required before any OEM can be re-classified out of
   `PROMOTE_WITH_CONDITIONS`.
3. Multi-day staging soak per OEM, watching for idempotency drift, false
   positives from the AMBIGUOUS-shaped naming gaps identified above (OnePlus
   "9/10 Pro" is now covered; Xiaomi "Redmi A-series" and OnePlus's
   nav-page-slug noise are not), and Xiaomi's intermittent 403 pattern.
4. Widen region coverage (Google beyond `/us/`, OnePlus beyond `/us/`,
   Xiaomi/Nothing already multi-region) once the single-region path is stable.
