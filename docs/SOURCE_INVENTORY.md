# Source Inventory

Authoritative answer to "what exactly does Smartphone Intel Clank monitor?"
— per `docs/ENGINEERING_PRINCIPLES.md` Rule 19. One row per source. Update
this file whenever a source's state changes; do not require a reader to
cross-reference configuration, Python, and recon documents to answer this
question.

## Production

| OEM | Source | Region | Role | State | Last live validation | Cadence | Production? | Known limitation |
|---|---|---|---|---|---|---|---|---|
| Samsung | `samsungmobilepress.com` / support sitemap (`collectors/samsung/sitemap_collector.py`) | US | DISCOVERY + MONITORING | LIVE_VALIDATED | 2026-08-10 | 180 min | **YES** | Specialized collector, pre-dates Wave 1 shared path — see `docs/wave2/POST_WAVE2_COMPLEXITY_AUDIT.md` |
| Google | `store.google.com/{region}/category/phones` | US (+ expandable) | DISCOVERY | LIVE_VALIDATED | 2026-08-10 | 45 min | **YES** | Slug-based marketing name only, no formal model number |
| Nothing | `nothing.tech/sitemap/products/1.xml` (+ region variants) | UK/US/IN | DISCOVERY | LIVE_VALIDATED | 2026-08-10 | 90 min | **YES** | Mixed with accessories/apparel in the same sitemap — denylist-filtered |
| OnePlus | `oneplus.com/{region}/sitemap.xml` | US | DISCOVERY (weak monitoring) | LIVE_VALIDATED | 2026-08-10 | 90 min | **YES** | No CPH codes exposed; slug-only discovery |
| Motorola | `motorola.com/{cc}/{lang}/sitemap.xml` | US, GB, DE | DISCOVERY | LIVE_VALIDATED, **PRODUCTION** | 2026-08-10 (canary revalidation) | 360 min (4 polls/day) | **YES — PROMOTED 2026-08-10**, see `docs/wave2/MOTOROLA_CANARY_REPORT.md` | Slug-to-marketing-name normalizer has known edge-case gaps (fails closed to AMBIGUOUS, never false-accepts) |
| Honor | `honor.com/global/sitemap.xml` | Global (int'l storefront) | DISCOVERY | LIVE_VALIDATED, **PRODUCTION** | 2026-08-11 (canary revalidation) | 360 min (4 polls/day) | **YES — PROMOTED 2026-08-11**, see `docs/wave2/HONOR_CANARY_REPORT.md` | `/cn/` locale (much larger, older) not evaluated; X-series naming grammar incomplete in validator |
| Oppo | `oppo.com/en/sitemap.xml` | Global/EN | DISCOVERY | LIVE_VALIDATED, **PRODUCTION** | 2026-08-11 (canary revalidation) | 360 min (4 polls/day) | **YES — PROMOTED 2026-08-11**, see `docs/wave2/OPPO_CANARY_REPORT.md` | Letter-suffix A-series/Reno variants (A17k, Reno7 Z) undercounted via fail-closed AMBIGUOUS |
| Realme | `realme.com/sitemap-{in,eu}.xml` | India + EU | DISCOVERY | LIVE_VALIDATED, **PRODUCTION** | 2026-08-11 (canary revalidation) | 360 min (4 polls/day) | **YES — PROMOTED 2026-08-11**, see `docs/wave2/REALME_CANARY_REPORT.md` | P-series and some suffix variants (14t/15t/15x) undercounted via fail-closed AMBIGUOUS; promo-text risk confirmed on landing pages only, not sitemap |

## Soak

Sources implemented and validated against live surfaces but holding NO
production promotion record. Excluded from production scheduling by
`collectors.SOAK_SAMSUNG_SOURCE_IDS` / `RUNNABLE_SAMSUNG_SOURCE_IDS`;
runnable only via staging one-shot targets
(`runtime.run_once.build_staging_targets`). Notification authority is
suppressed by policy regardless of environment (`alerts/source_maturity.py`,
fail-closed): every suppressed newsroom decision leaves a
`WebhookDelivery` evidence row.

| OEM | Source | Region | Role | State | Last live validation | Cadence | Production? | Known limitation |
|---|---|---|---|---|---|---|---|---|
| Samsung | `samsung.com/us/support/owners/product/<slug>` (`collectors/samsung_owners.py`) | US | DISCOVERY (pre-announcement support surface) | LIVE_VALIDATED, **SOAK** | 2026-08-02 (seed paths, registry) | 180 min (staging) | NO — soak, promotion requires explicit record | Seed-path based discovery; new-model slugs must be added to `samsung_sources.yaml` seeds |

## Research / held

| OEM | Source | Region | Role | State | Last live validation | Cadence | Production? | Known limitation |
|---|---|---|---|---|---|---|---|---|
| Vivo | `vivo.com/{cc}/sitemap.xml` | UK/IN/EN/AU checked | DISCOVERY (structurally) | LIVE_VALIDATED, RESEARCH_ONLY | 2026-08-11 | N/A | NO — `RESEARCH_MORE` | Confirmed structural gap: of 4 regional sitemaps checked, only UK exposes a product catalogue, and it's stale (no X200/X300/current flagship anywhere). iQOO confirmed architecturally separate (not merged); validator exists, no adapter built |
| Xiaomi | `mi.com/global/sitemap/` (HTML list, no XML sitemap) | Global | DISCOVERY + MONITORING | LIVE_PARTIAL, KEEP_STAGING | 2026-08 (Wave 1 phase) | N/A | NO — deliberately held | Source oscillates HTTP 200/403; adapter/validator both exist and are exercised in `tests/wave1/`, never promoted |
| ASUS/ROG | `rog.asus.com/sitemap.xml`, `asus.com/mobile-handhelds/phones/` | Global | DISCOVERY (structurally) | LIVE_VALIDATED, RESEARCH_ONLY | 2026-08-10 | N/A | NO — `REJECT` | ASUS publicly exited the smartphone business as of early 2026; source quality is fine, business context makes it moot — see `docs/wave2/asus_rog.md` |

## Capability matrix (production sources)

Per `docs/ENGINEERING_PRINCIPLES.md` Rule 5/Part G — a healthy source is
not automatically a capable one. `YES` requires live-observed evidence
during recon/canary; `PARTIAL` means structurally possible but not yet
observed; `UNKNOWN` means never tested.

| OEM | Unknown device | Regional availability | Support preparation | New variant | Availability change | Meaningful page change |
|---|---|---|---|---|---|---|
| Samsung | YES (support sitemap surfaces new SKUs pre-announcement historically) | PARTIAL | YES (support-page-first is the core signal) | YES | UNKNOWN | YES |
| Google | YES (live "Pixel 11" teaser observed during Wave 1 recon) | PARTIAL (per-country sitemaps exist, not all polled) | NO (support surface blocked) | PARTIAL | UNKNOWN | PARTIAL |
| Nothing | YES (region-exclusive CMF Phone 1 surfaced via India sitemap) | YES (India-exclusive device confirmed) | NO | PARTIAL | UNKNOWN | PARTIAL |
| OnePlus | PARTIAL (sitemap-only, no pre-release teaser mechanism observed) | PARTIAL (69 regional sitemaps exist, 1 polled) | NO (support surface blocked) | PARTIAL | UNKNOWN | PARTIAL |
| Motorola | PARTIAL (baseline only — no post-baseline event observed yet during canary) | PARTIAL (51 regional sitemaps exist, 3 polled) | UNKNOWN | PARTIAL (SKU-grade identity makes this the most promising OEM for this signal) | UNKNOWN | UNKNOWN |
| Honor | PARTIAL (baseline only — no post-baseline event observed yet during canary) | UNKNOWN (single global sitemap polled, no per-region variant observed) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| Oppo | PARTIAL (baseline only — no post-baseline event observed yet during canary) | UNKNOWN (single global sitemap polled) | UNKNOWN | PARTIAL (family/series-classified identity, good structural fit for this signal) | UNKNOWN | UNKNOWN |
| Realme | PARTIAL (baseline only — no post-baseline event observed yet during canary) | PARTIAL (India + EU polled, same devices appear in both — regional dedup working, no region-exclusive device observed yet) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

This table should be re-scored, not assumed static, as each source
accumulates more operational history — a `YES` earned once during a canary
is evidence, not a permanent guarantee (Rule 6: no silent zero applies to
capability regression too).
