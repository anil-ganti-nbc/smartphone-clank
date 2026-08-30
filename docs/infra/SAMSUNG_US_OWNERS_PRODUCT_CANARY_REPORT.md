# Samsung US Owners Product — SOAK → CANARY Transition Report

Date: 2026-08-30. Scope: promote `samsung_us_owners_product` one stage, SOAK →
CANARY, per `docs/ENGINEERING_PRINCIPLES.md` Rule 7's lifecycle
(RESEARCH → LIVE VALIDATION → STAGING → BASELINE → REPEATABILITY → CANARY →
PRODUCTION, no shortcuts). This transition does NOT grant production
notification authority and does NOT add the source to
`alerts/source_maturity.py::PRODUCTION_SOURCES` — that is the separate,
future full-production promotion (Fleet Law 8).

## 0. Lifecycle evidence at transition time

| Rule-7 stage | Status | Evidence |
|---|---|---|
| RESEARCH / LIVE VALIDATION | done 2026-08-02 | `config/samsung_sources.yaml` seed paths validated live; `docs/samsung_live_validation.md` |
| STAGING | done 2026-08-25 | commits `a65a82f` (soak collector + maturity gate) and `10906e6` (MODEL_RE 11-char fix + staging runtime wiring + soak timer) |
| BASELINE | done 2026-08-26 03:48:13Z | first natural staging cycle created the 6-device corpus (`staging_scheduled`, status `success`) |
| REPEATABILITY | done 2026-08-30 12:32:55Z | 32 consecutive clean repeat cycles after baseline — see §1 |
| CANARY | entered 2026-08-30 | this transition |

No numeric cycle minimum is defined in repo policy; Wave-1/2 canaries
(Google/Nothing/OnePlus/Motorola/Honor/Oppo/Realme) each passed with a
baseline plus 3-4 stable repeat cycles. This soak ran ~8x longer than any
Wave-1/2 qualification.

## 1. Soak evidence record (staging DB `data/clank-staging.db`, verified live 2026-08-30)

- Soak start (first natural `staging_scheduled` cycle): **2026-08-26
  03:48:13Z**. Last cycle before promotion: **2026-08-30 12:32:55Z**.
- Natural scheduled cycles: **33 total, 33/33 `success`, 0 `failed`, 0
  partial/degraded/unexpected_zero** (plus 1 pre-soak controlled validation
  run on 2026-08-25 07:41Z, `deployment_pass2_controlled_validation`).
- Baseline cycle (run 1): 6 new devices, 0 updates. All 32 subsequent
  cycles: **0 new devices** (pure resight/update cycles, 6 updates each).
- Devices: exactly 6 Samsung, all full 11-character retail codes —
  SM-S928ULBEXAA, SM-S921ULBAXAA, SM-S926ULBAXAA, SM-F956UAKAXAA,
  SM-F741UAKAXAA, SM-A356ULVAXAA (the 11-char shape is itself a soak
  outcome: the pre-`10906e6` regex could not have seen any of them).
- Zero misfires, zero `job failed`, zero ERROR/Traceback lines in the
  systemd journal for the soak unit across the whole window.
- Notification suppression: every newsroom decision suppressed by source
  maturity — 6 `new_model` + 191 `support_page_change` `WebhookDelivery`
  rows, all `suppressed=1 / attempted=0 / delivered=0`; `alerts_sent=0` in
  all 34 runs; zero `Alert` rows.

## 2. Zero-new is health, not starvation (verified live 2026-08-30)

The zero-new trend was checked for the classic soak failure mode — a
collector silently parsing a stale cache — and passes:

- Every cycle performs real HTTP fetches: the journal shows the full
  per-page redirect chains (e.g. `owners/product/galaxy-a35-5g` → 301 →
  `support/mobile/phones/galaxy-a/galaxy-a35-5g/` → 302 →
  `support/mobile/phones/?modelCode=SM-A356ULVAXAA` → 200) and per-page
  parse lines, with ~10.5s wall time per cycle (7 pages paced by
  `min_delay_seconds=1.5` — a cache replay would be near-instant).
- Evidence content hashes differ cycle-to-cycle (live pages carry changing
  content), which is why each cycle records 6 refreshed evidence rows and
  6 `updated_devices` — the corpus is genuinely re-fetched and re-parsed.
- Live probe from the host at transition time (following redirects, same as
  the collector): `galaxy-s24-ultra` 200 + SM- codes, `galaxy-z-fold6` 200 +
  SM- codes, `galaxy-a35-5g` 200 + SM- codes, `galaxy-a55-5g` 200 but 0
  codes (Samsung now redirects that seed to a code-less generic support
  page — a real, observed source drift, recorded as the inventory's known
  limitation; it narrows coverage by one seed and does not affect
  correctness).
- Allowlisting/binding behaved: cross-page duplicates collapse; 0 rejected
  candidates, 0 cross-manufacturer collisions, 0 unexpected registry
  rejections across all cycles.

## 3. What changed in this transition (and what deliberately did not)

Changed:

1. `collectors/__init__.py`: `samsung_us_owners_product` moved out of
   `SOAK_SAMSUNG_SOURCE_IDS` (now empty) into the new
   `CANARY_SAMSUNG_SOURCE_IDS`, and added to `RUNNABLE_SAMSUNG_SOURCE_IDS`
   (it now has a real collector implementation, satisfying
   `production_scope()`'s documented LIVE_VALIDATED ∧ runnable rule).
   `build_collectors()` registers canary sources in the default (production)
   build with `maturity="canary"`.
2. `deploy/systemd/smartphone-clank-samsung_us_owners_product.timer` (new):
   production per-source timer (3h, matching `interval_minutes: 180`) →
   `smartphone-clank-source@.service` → production `config/config.yaml` +
   production DB. The retired
   `smartphone-clank-soak@samsung_us_owners_product.timer` (staging) is
   removed; the generic `smartphone-clank-soak@.service` template remains
   for future soak sources.
3. Tests updated to pin the canary contract (§4). Documentation:
   `docs/SOURCE_INVENTORY.md`, `deploy/systemd/README.md`, this report.

Deliberately NOT changed:

- `alerts/source_maturity.py`: the source remains absent from
  `PRODUCTION_SOURCES` → fail-closed soak classification → every newsroom
  send suppressed with a `WebhookDelivery` evidence row (6 new-model +
  ~6/cycle page-change decisions expected in production, all suppressed).
  **Canary has no notification authority; canary is not production.**
- `alerts/discord.py`, `pipeline.py`: no notification behavior invented;
  the existing double gate applies unchanged — (a) source-maturity
  suppression, (b) `min_confidence_for_alert: 20` vs. the SUPPORT_PAGE
  first-sighting confidence weight (10), so baseline new-device decisions
  are doubly ineligible.
- `config/config.yaml` / `config/samsung_sources.yaml`: no flag flips —
  the promotion record is the reviewed code change itself (Fleet Law 8:
  "promotion gates ... never a config-only flip").
- Production OEM sources' config, classification/novelty semantics, schema:
  untouched. No DB reset; staging DB and its soak evidence preserved.

## 4. Production baseline expectations (first canary cycles)

No state carries over from staging — the production DB has no rows for this
source, so the first production run is a fresh baseline:

- Expect ~6 new-device decisions (the 11-character retail codes are new to
  the production catalogue; existing production Samsung rows use shorter
  sitemap-derived codes, and the resolver keys on
  `(manufacturer, model_number)`, so these are legitimately distinct rows,
  not duplicates).
- Expect every one of those decisions to be **suppressed** (maturity gate),
  with `WebhookDelivery` evidence rows — never delivered, never `Alert`
  rows. This is the same suppression the soak observed 197 times in staging.
- Expect the subsequent cycles to be pure resights unless Samsung publishes
  a new model or changes a page.
- If this canary later earns full production (a future reviewed
  `alerts/source_maturity.py` edit), notification eligibility begins only
  then, under the standard `min_confidence_for_alert` gate.

## 5. Rollback

`systemctl disable --now smartphone-clank-samsung_us_owners_product.timer`
on the host (and re-enable the soak timer only via a reviewed revert of this
commit). Disabling schedules nothing and deletes no data; staging soak
evidence remains intact in `data/clank-staging.db`.
