# Wave 1 Source Matrix

Synthesized from `docs/wave1/{google,oneplus,nothing,xiaomi}_recon.md`. Full
recon detail (every candidate URL, HTTP status, robots.txt notes, blocking
issues) lives in those four files — this is the summary used to pick what
gets implemented.

| OEM | Source | Role | Region | Structured | Discovery | Live status | Notes |
|---|---|---|---|---|---|---|---|
| Google | `store.google.com/category/phones` | Discovery + Monitoring | per-country (~40) | Partial (anchor `/product/{slug}` links; no JSON-LD Product schema) | Yes — surfaced an uncatalogued "Pixel 11" pre-order teaser live during recon | LIVE_VALIDATED | Best signal; identifier extraction must anchor to launch-intent language + `/product/{slug}` hrefs, never blanket text regex |
| Google | `store.google.com/sitemap/sitemap_{region}.xml` | Monitoring | per-country (~40) | Yes (XML urlset) | Weak (already-listed products only) | LIVE_VALIDATED | Slugs only, no formal model number |
| Google | `store.google.com/product/{slug}` | Confirmation | per-country | Partial (HTML only, no Product JSON-LD) | No | LIVE_PARTIAL | Requires slug known in advance |
| Google | `blog.google/products/pixel/rss/` | Confirmation | global | Yes (RSS) | No | LIVE_VALIDATED | URL slug only signal, never post-title prose |
| Google | `developers.google.com/android/{ota,images}` | Confirmation (if unblocked) | global | Would be, if reachable | No | BLOCKED | TOS-acknowledgment wall did not open in an automated session |
| Google | `support.google.com/pixelphone/` | — | global | No (topic/answer CMS) | No | REJECTED | Same shape as the incident's failure mode; no per-device URLs |
| OnePlus | `oneplus.com/{region}/sitemap.xml` (start: `/us/`) | Discovery + weak Monitoring | per-country (69 listed in robots.txt) | Yes (XML urlset, flat) | Yes — marketing-name slugs, current lineup confirmed present | LIVE_VALIDATED | No CPH codes in sitemap; slug-only discovery |
| OnePlus | `oneplus.com/global/sitemap.xml` | — | "Global" storefront | Yes | No | UNSTABLE | Live but stale since ~2023 — would silently miss everything since OnePlus 11 |
| OnePlus | `oneplus.com/sitemap.xml` (root) | — | — | — | — | BLOCKED | 403 on every attempt; use regional sitemaps instead |
| OnePlus | `oneplus.com/{region}/support/*` | — | per-country | No (Vue SPA shell) | No | BLOCKED | Real data needs JS + a `/api/` path robots.txt disallows |
| OnePlus | `community.oneplus.com` | Monitoring (weak) | global | No (SPA + human prose) | No | REJECTED | Same false-positive risk as the incident |
| Nothing | `nothing.tech/sitemap/products/1.xml` (+ region variants) | Discovery | per-region (UK/US/IN confirmed distinct) | Yes (XML urlset, Shopify) | Yes — full product catalogue including region-exclusive CMF Phone 1 (India) | LIVE_VALIDATED | Mixed with accessories/apparel; needs strict slug filtering (see fixtures) |
| Nothing | `nothing.tech/collections/phones` + `/collections/cmf` | Monitoring | per-region | Partial (HTML) | No (curated, not exhaustive) | LIVE_VALIDATED | Good "still for sale" signal, not a discovery source |
| Nothing | `nothing.tech/products/{slug}` | Confirmation | per-region | Partial (HTML) | No | LIVE_VALIDATED | Confirms slug resolves to a real phone product page |
| Nothing | `support.nothing.tech` (Zendesk) | — | global | — | — | BLOCKED | 403 to plain fetch; unresolved whether bot-block or policy |
| Nothing | `nothing.community` forum | Monitoring (tentative) | global | No | No | PROMISING/UNVERIFIED | Official affiliation not confirmed — do not treat as first-party yet |
| Nothing | `cmf.tech` | — | — | — | — | REJECTED | 301-redirects into nothing.tech; not independent |
| Xiaomi | `mi.com/global/sitemap/` (HTML, not XML) | Discovery + Monitoring | global (India-biased edge observed) | Partial (HTML link list, no XML sitemap exists) | Yes — enumerates live Xiaomi/Redmi/POCO product slugs | PROMISING | No XML sitemap found anywhere on mi.com despite systematic probing; needs phone-vs-accessory filtering, no model-number text on any page found |
| Xiaomi | `mi.com/global/poco/` | Confirmation (POCO) | global | Partial (HTML) | Yes (POCO subset) | LIVE_VALIDATED | POCO has distinct brand identity but shares mi.com storefront infra |
| Xiaomi | `mi.com/global/product/{slug}/` | Confirmation | global | Partial (HTML) | No | LIVE_PARTIAL | Zero model-number/codename text found on any product/specs page tested |
| Xiaomi | `mi.com/global/support/terms/declaration/` | Confirmation (untested) | global | Unknown | Unknown | UNSUPPORTED | Most promising untested lead for real regulatory model numbers — first follow-up before any further Xiaomi work |
| Xiaomi | `mi.com/global/phone/`, `mi.com/global/support/` | — | global | — | — | BLOCKED | 403 Akamai |
| Xiaomi | `mi.com/in/support/` | — | India | — | — | BLOCKED (flip-flopping 200/403) | Adaptive bot detection; not a reliable discovery source |
| Xiaomi | `github.com/XiaomiFirmwareUpdater/*`, `mirom.ezbox.idv.tw` | Monitoring/enrichment only | global | Yes, but third-party | No | PROMISING but NOT first-party | Never DISCOVERY/CONFIRMATION source per spec — explicit "prefer first-party" rule |
| All | Geekbench | — | — | — | — | REJECTED (permanent, out of scope) | Excluded by standing instruction, not investigated |

## Per-OEM discovery source selection

- **Google:** `store.google.com/category/phones`, polled across at least US + a
  few other major regions, extracting `/product/{slug}` anchors and
  launch-intent-anchored "Pixel N" teaser text only (never blanket prose regex).
- **OnePlus:** `oneplus.com/{region}/sitemap.xml`, starting with `/us/`
  (confirmed live/current), extracting product-path slugs.
- **Nothing:** `nothing.tech/sitemap/products/1.xml` (+ region variants),
  extracting slugs, filtered against the accessory/apparel/audio denylist
  documented in `docs/wave1/nothing_recon.md`.
- **Xiaomi:** `mi.com/global/sitemap/` (HTML page, not XML), extracting
  `/product/{slug}/` links filtered to Redmi/POCO/Xiaomi phone-shaped slugs;
  weakest of the four sources (PROMISING, not LIVE_VALIDATED) since no XML
  sitemap exists and no page carries a real model-number field.

## Cross-OEM pattern that differs from Samsung

Every Wave 1 OEM's structured surface yields a **marketing-name slug**, not a
formal model number the way Samsung's support sitemap yields `SM-XXXXX`
codes. None of the four recons found a first-party page exposing OnePlus's
`CPH####`, Xiaomi's `M#######`-style codes, or Nothing's internal hardware
codes in parseable form. Wave 1 validators (`collectors/wave1/*/model_validator.py`)
therefore accept marketing-name identifiers as the primary VALID shape for all
four OEMs, and treat internal/regulatory codes as a separate, not-yet-solved
enrichment problem rather than forcing a weak/blocked source into service.
