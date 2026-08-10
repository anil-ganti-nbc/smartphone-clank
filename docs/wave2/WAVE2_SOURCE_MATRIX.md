# Wave 2 Source Matrix

Synthesized from `docs/wave2/{motorola,oppo,vivo,realme,honor,asus_rog}.md`.
Same format as `docs/wave1/SOURCE_MATRIX.md`. Roles: DISCOVERY / MONITORING /
CONFIRMATION / AVAILABILITY (a source may hold more than one).

| OEM | Source | Role | Region | Structured | Discovery | Automation safety | Notes |
|---|---|---|---|---|---|---|---|
| Motorola | `motorola.com/{cc}/{lang}/sitemap.xml` | Discovery + Monitoring | 51 regional sitemaps | Yes (XML urlset) | Yes — `/p/phones/{family}/{variant}/{sku}` fully enumerable, current-gen models present | SAFE | Best Wave 2 source; SKU-grade slug, not just marketing name |
| Motorola | `motorola.com/{cc}/{lang}/p/phones/*` | Confirmation | per-region | Partial (HTML) | No | SAFE | Individual product page, requires known slug |
| Honor | `honor.com/honor-all-sitemap.xml` | — | global index | Yes (sitemap index) | — | SAFE | Points to per-locale leaf sitemaps |
| Honor | `honor.com/global/sitemap.xml` | Discovery + Monitoring | international storefront | Yes (XML urlset) | Yes — `/phones/{slug}` path-isolated from laptops/wearables/tablets/audio | SAFE | Marketing-name slug only (no formal model number found) |
| Honor | `honor.com/{cc}/sitemap.xml` (per-locale, e.g. `/cn/`) | Monitoring (untested) | per-locale | Yes | Unknown | UNKNOWN | `/cn/` locale not sampled; mission flagged Huawei-era stale-catalogue risk here specifically |
| Oppo | `oppo.com/en/smartphones/` | Monitoring (curated) | global/en | Partial (HTML, clean per-model links) | Weak (curated current lineup, not exhaustive enumeration) | SAFE | ~80 models visible incl. very recent Find X9 Ultra, Find N6, Reno16 |
| Oppo | `oppo.com/sitemap.xml` | — (undecomposed) | unknown | Unknown | Unknown | UNKNOWN | Not yet checked for a phone-specific sub-sitemap; natural next step |
| Vivo | `vivo.com/sitemaps.xml` | — | 52 regional index | Yes (sitemap index) | — | SAFE | No `iqoo.com` reference anywhere in the index |
| Vivo | `vivo.com/uk/sitemap.xml` | Discovery + Monitoring | UK | Yes (XML urlset) | Weak in this sample — `/products/param/{model}` clean but sampled models skewed old (v21, x60pro) | SAFE | Recommend checking `/in/` (largest market) before BUILD_NOW |
| Realme | `realme.com/sitemap.xml` | — | dozens of per-country index | Yes (sitemap index) | — | SAFE | Heavily fragmented — operational-cost concern |
| Realme | `realme.com/sitemap-{cc}.xml` (sampled: `uk`→redirect, `eu` via retry) | Discovery + Monitoring | per-country | Yes (XML urlset) | Yes in `eu` sample — 3 current-gen `realme-16` models | SAFE | Small per-country yield; promotional-text pollution risk (mission's specific warning) not observed in sitemap slugs themselves, still guarded in validator |
| Honor/Vivo/Realme | (all three) | — | — | — | — | SAFE (all three) | Zero 403/429/CAPTCHA encountered across all probes this phase |
| ASUS/ROG | `rog.asus.com/sitemap.xml` | Discovery (moot) | global | Yes | Yes structurally | SAFE | `/phones/rog-phone-9/` etc., cleanly subdomain-isolated from PC hardware |
| ASUS/ROG | `asus.com/mobile-handhelds/phones/all-series/` | Discovery (moot) | global | Partial (HTML) | Yes structurally | SAFE | `/mobile-handhelds/phones/` path-isolated from laptops/motherboards/GPUs |
| ASUS/ROG | (business context) | — | — | — | — | — | **ASUS publicly exited the smartphone business as of early 2026** — no new Zenfone/ROG Phone models planned (chairman Jonney Shih, multiple outlets). Novelty potential ≈ 0 regardless of source quality. |

## Per-OEM discovery source selection (candidates, not commitments — see Phase 18)

- **Motorola:** `motorola.com/{cc}/{lang}/sitemap.xml`, scoped to a handful of
  major regions (US, GB, DE, or similar) rather than all 51, extracting
  `/p/phones/` entries.
- **Honor:** `honor.com/global/sitemap.xml`, extracting `/phones/{slug}`
  entries, deduplicating `/spec/` and `/tips/` sub-pages to their parent
  slug.
- **Oppo:** `oppo.com/en/smartphones/` category page (curated,
  monitoring-grade) until `oppo.com/sitemap.xml` is decomposed for a
  phone-specific leaf sitemap.
- **Vivo:** `vivo.com/{cc}/sitemap.xml`, extracting `/products/param/{model}`
  entries, deduplicating `/products/picture/{model}` to the same identity.
  Recommend confirming freshness against `/in/` before committing.
- **Realme:** `realme.com/sitemap-{cc}.xml` for a small set of high-value
  regions, extracting `/{cc}/{device-slug}` and deduplicating `/specs`
  sub-pages.
- **ASUS/ROG:** not selected — see REJECT verdict in `asus_rog.md`.

## Cross-OEM pattern

Motorola stands out from every other Wave 2 (and every Wave 1) OEM by
exposing a genuine SKU-grade identifier in its sitemap URL, not just a
marketing-name slug. Honor, Oppo, Vivo, and Realme all follow the Wave 1
pattern (marketing-name slug as the primary deterministic identifier;
formal model numbers not found in any first-party structured surface
probed this phase).
