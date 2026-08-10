# Nothing — Source Reconnaissance

Date: 2026-08-10
Scope: brand "Nothing" phones only (not CMF as a standalone brand, not Nothing OS software). Geekbench excluded per standing policy — not investigated.

All fetches below were done live via WebFetch/WebSearch on 2026-08-10. nothing.tech is a Shopify storefront with region subdomains (nothing.tech / us.nothing.tech / in.nothing.tech / etc., geo-redirected). `cmf.tech` is not a separate storefront — it 301-redirects to `nothing.tech`.

## Candidate surfaces

### 1. `https://nothing.tech/sitemap.xml` (sitemap index)
- URL/endpoint: `https://nothing.tech/sitemap.xml` (mirrored per region, e.g. `https://us.nothing.tech/sitemap.xml`, confirmed same structure)
- Region: global default (redirects to region based on geo-IP; content differs per region — see CMF notes below)
- Content type: XML sitemap index (Shopify-generated)
- HTTP status observed: 200
- Auth: none
- robots.txt: explicitly referenced (`Sitemap: https://nothing.tech/sitemap.xml`), not disallowed
- Pagination: index references paginated sub-sitemaps (`/sitemap/products/1.xml`, `/sitemap/collections/1.xml`, `/sitemap/pages/1.xml`); only "1" observed so far — low product count means no page 2 yet, but code should treat as paginated
- Rate-limit signals: none observed; robots.txt sets 10s crawl-delay for AhrefsBot/MJ12bot only, none for default UA
- JS dependency: none — pure XML, static fetch
- Last-modified hints: sub-sitemap entries carry `<lastmod>`; index-level static pages showed `lastmod = 2026-08-10T08:33:39Z` (i.e., updates same-day, looks live)
- Stability: LIVE_VALIDATED
- Role: DISCOVERY (points at the products sitemap which is the actual discovery feed)

### 2. `https://nothing.tech/sitemap/products/1.xml` (products sitemap)
- URL/endpoint: as above; region variants exist under each region subdomain
- Content type: XML, one `<url>` per Shopify product (87 entries observed on UK/default region)
- HTTP status: 200
- Auth: none
- robots.txt: not disallowed (no `/products` disallow rule found; only `/collections/*sort_by*` type disallows for filtered/sorted views)
- Pagination: single page currently (`/1.xml`); code must not hardcode "1" — check sitemap index for further pages as catalog grows
- JS dependency: none
- Model identifiers exposed: Shopify product handles/slugs only, e.g. `phone-1`, `phone-2`, `phone-2a-the100-drops-edition-london`, `phone-3`, `phone-3a`, `phone-3a-pro`, `phone-3a-lite`, `phone-4a`, `phone-4a-pro`, `phone-4b`. No internal FCC-style codes (A063/A065/A142) in the sitemap itself — those only appear in regulatory filings/teardown sources, not on nothing.tech.
- **Critical noise**: the same sitemap mixes in phone *accessories* under phone-shaped slugs: `phone-1-case`, `phone-1-screen-protector`, `phone-2-case`, `phone-2-case-screen-protector`, `phone-2-screen-protector`, `phone-3-drop` (a drop/launch page, not confirmed a device), `spigen-case-phone-3-*`, `spigen-screen-protector-*-phone-3*`, etc. Also totally unrelated `copy-of-accidental-damage-*` (warranty SKUs) and apparel (`nothing-hoodie`, `nothing-tracksuit-*`), audio (`ear-*`, `headphone-*`), CMF audio/watch/power SKUs, and Teenage Engineering collab bags. A naive "contains phone" regex would catch cases/protectors/drops as false devices.
- Release-state hints: none directly (no "coming soon"/"available" flag in the sitemap; would need the product page itself)
- Stability: LIVE_VALIDATED — but requires a real product-detail allowlist/denylist step, not just sitemap presence
- Role: DISCOVERY (best raw discovery source: catches new product slugs before/at launch, since it's the canonical Shopify catalog) — must be paired with product-page fetch + strict slug filtering (see Identifier format notes)

### 3. `https://nothing.tech/products/{slug}` (individual product pages)
- URL/endpoint pattern: `https://nothing.tech/products/phone-3`, `/products/phone-4a`, etc. (also `?Colour=...&Capacity=...` variant query params — not separate devices)
- Content type: HTML (Shopify product page)
- HTTP status: 200 for real slugs (e.g. `phone-3`), 404 for non-existent (e.g. `cmf-phone-1` on the UK/default store — confirms region-gating, see below)
- Auth: none
- JS dependency: page render used client-rendered Shopify theme; WebFetch's markdown conversion still surfaced title/price/images without needing JS execution, but a `__NEXT_DATA__`-style single JSON blob was **not confirmed** — this store does not appear to be Next.js (no such tag found; it's Shopify Online Store, likely Liquid + Shopify's own hydration, not Next.js). Standard Shopify product JSON (`/products/{slug}.json`) was not tested but is a strong bet worth validating in implementation (Shopify stores conventionally expose `.json` on every product URL).
- Model identifiers exposed: marketing name only in `<title>` (e.g. "Phone (3) | Phones | Nothing | UK"), price, color/storage variants. No internal hardware codes on-page.
- Marketing names confirmed live: "Phone (3)" — parenthesized style is how Nothing brands it in page titles, distinct from the URL slug style `phone-3`.
- Regional identifiers: same slug, different price/currency/availability per region subdomain (`nothing.tech` = UK, `us.nothing.tech` = US, `in.nothing.tech` = India, etc.)
- Stability: LIVE_VALIDATED
- Role: CONFIRMATION (validate a slug found via sitemap actually resolves to a real phone product page, extract canonical marketing name + price/region for evidence)

### 4. `https://nothing.tech/collections/phones` (curated phones collection)
- URL/endpoint: `https://nothing.tech/collections/phones`
- Content type: HTML, Shopify collection page
- HTTP status: 200
- Auth: none
- robots.txt: not disallowed (only filtered/sorted variants of collections are disallowed, e.g. `?sort_by=`)
- JS dependency: none apparent for the base listing (WebFetch got a clean list without executing JS)
- Model identifiers exposed: only phones — confirmed **zero accessories** appeared on this page (19 entries observed, all `phone-*` variants: Phone (4a) Pro, Phone (4a), Phone (4b), Phone (3), Phone (3a) Lite, Phone (3a) Pro, Phone (3a) — counting color/storage variants as duplicates of the same product)
- Stability: LIVE_VALIDATED
- Role: CONFIRMATION / MONITORING (this is manually curated by Nothing's merchandising, so it is NOT a discovery source for brand-new unlisted devices — a device could exist in the products sitemap before it's added to this curated collection, or a discontinued device could be pulled from this collection while still resolving at its URL. Best used to cross-check "is this currently a sold phone" and catch pulled-from-sale state changes.)

### 5. `https://nothing.tech/sitemap/collections/1.xml`
- Content type: XML, lists 8 collection URLs: `/collections/products`, `/collections/gmc`, `/collections/phones`, `/collections/accessories`, `/collections/watches`, `/collections/audio`, `/collections/shop-all`, `/collections/cmf`
- HTTP status: 200
- Stability: LIVE_VALIDATED
- Role: MONITORING (confirms `/collections/phones` and `/collections/cmf` exist as stable canonical category endpoints; `lastmod` per collection could be used as a lightweight "something changed" signal, e.g. accessories collection had an older lastmod than phones/watches/audio, suggesting per-collection change tracking is meaningful)

### 6. `https://nothing.tech/robots.txt`
- Content type: text/plain
- HTTP status: 200
- Findings: standard Shopify robots.txt. Disallows admin/cart/checkout/order paths, filtered/sorted collection query variants, and `/policies/`. Does **not** disallow `/products`, `/collections` (base), or `/sitemap`. Named-bot crawl-delays exist (AhrefsBot, MJ12bot: 10s; Pinterest: 1s) but none apply to a generic collector UA — still, a polite crawl delay is advisable.
- Stability: LIVE_VALIDATED
- Role: supports DISCOVERY/CONFIRMATION (governance input, not a data source itself)

### 7. `https://nothing.tech/` (homepage)
- Content type: HTML
- HTTP status: 200 (redirected to region default when fetched from a non-UK vantage — observed redirect to `in.nothing.tech` on one fetch, `us.nothing.tech` sitemap also independently confirmed reachable — geo-IP based region redirect confirmed real)
- Model identifiers exposed: current flagship lineup only (Phone (4a) Pro, Phone (4a), Phone (4b), Phone (3) were visible in nav/hero at fetch time) plus audio/CMF accessories in the same nav — phones and accessories share navigation but are visually/structurally separated into distinct nav groups
- `__NEXT_DATA__`: **not found**. No evidence this storefront is Next.js — it is a Shopify theme. (Original task hypothesis of Next.js embedded JSON should be dropped for the storefront; it may still be worth checking `support.nothing.tech` separately, but that surface was blocked — see below.)
- Stability: LIVE_PARTIAL (works, but content is homepage-curated marketing subset, not exhaustive)
- Role: not a good discovery/confirmation source — background context only

### 8. `https://support.nothing.tech/hc/en-us` (Zendesk help center)
- Content type: would be HTML (Zendesk)
- HTTP status observed: **403 Forbidden**
- Auth: unclear whether this is bot-blocking (Zendesk/Cloudflare) or a genuine access restriction — WebFetch could not get past it
- Stability: BLOCKED
- Role: would have been MONITORING/CONFIRMATION (per-device support categories, e.g. search results reference `support.nothing.tech/hc/en-us/categories/7455115681041-Troubleshooting` and a regional FAQ category `.../38494776961169-FAQ-India`) if accessible — categories appear to be topic-based (Troubleshooting, FAQ) rather than cleanly per-device, so even if unblocked this may not directly enumerate device slugs. Flag as open question — worth a real browser-based check outside this recon (not done here since WebFetch was blocked and Geekbench-style anti-bot fights are explicitly out of scope for effort).

### 9. `https://nothing.tech/pages/support-centre` (India variant: `in.nothing.tech/pages/support-centre`)
- Content type: HTML, Shopify page
- HTTP status: 200
- Findings: This is a support **hub/landing page**, not a device index. It links out to category collections (`/collections/phones`, `/collections/audio`, `/collections/watches`, `/collections/cmf`) and to the external Zendesk help center, plus `/pages/support-product-help`, `/pages/support-software-download`, `/pages/service-center`. It does **not** enumerate individual phone models directly.
- Stability: LIVE_PARTIAL
- Role: navigational only — routes to collections (already covered above) and the blocked Zendesk instance

### 10. `https://nothing.tech/pages/support-software-download`
- Content type: HTML
- HTTP status: 200
- Findings: This is **not** a firmware/OTA build repository. It only links to the "Nothing X" companion app on the Apple App Store / Google Play and the CMF Watch app. No build numbers, no firmware changelog, no device-specific download list found.
- Stability: LIVE_PARTIAL (page loads fine, but contains none of the OTA/firmware data the original task hypothesized)
- Role: REJECTED for firmware/OTA monitoring purposes — not useful as a device or version signal

### 11. `https://nothing.tech/pages/product-data-information`
- Content type: HTML, EU Data Act compliance notice
- HTTP status: 200
- Findings: Confirms Nothing's official device taxonomy in prose: "Nothing smartphones", "CMF by Nothing smartphones", "Nothing earbuds", "CMF by Nothing earbuds", "CMF by Nothing watches" — i.e. Nothing's own legal copy treats "CMF by Nothing" as a labeled sub-line across phones/earbuds/watches, always with "by Nothing" attached, never as a fully separate unqualified brand name. No model numbers or FCC-style codes present.
- Stability: LIVE_VALIDATED (as a source of official brand-language, not device data)
- Role: informational only — CMF relationship evidence (see dedicated section below)

### 12. `https://cmf.tech`
- HTTP status: 301 Moved Permanently → `https://nothing.tech/`
- Findings: CMF does **not** have an independent storefront anymore; the domain forwards straight into the main Nothing Shopify store. All CMF SKUs (buds, watches, power accessories, clips) live under `nothing.tech/products/cmf-*` and `nothing.tech/collections/cmf`.
- Stability: LIVE_VALIDATED (as a redirect fact)
- Role: REJECTED as an independent source — fold into candidate #2/#4 above; do not build a separate CMF collector pointed at cmf.tech

### 13. `nothing.community` (Discourse-style forum, `/t/{tag}` and `/d/{id}-{slug}` URLs)
- URL examples found via search: `nothing.community/t/phone-3`, `nothing.community/t/phone-3a`, `nothing.community/t/phone-3a-pro`, and discussion threads like `nothing.community/d/58487-nothing-phone-3-nothing-os-b41-260603-1221-changelog`
- Content type: HTML forum (looks Discourse-based from URL shape)
- HTTP status: `/about` returned 404 in this recon — could not confirm official ownership/affiliation directly. Search results show these threads titled as official-looking Nothing OS changelog posts (e.g. "Nothing Phone (3) - Nothing OS B4.1-260603-1221 Changelog"), which strongly suggests Nothing staff or an authorized channel posts here, but this recon could **not directly verify** the forum is first-party Nothing-operated (vs. a heavily-Nothing-endorsed but separately run community site).
- JS dependency: unknown/unconfirmed (not fully fetched)
- Model identifiers exposed: tag-per-device (`phone-3`, `phone-3a`, `phone-3a-pro`) matching the same slug convention as the store, plus explicit Nothing OS build-number strings in thread titles (e.g. `B4.1-260603-1221`) — this is the closest thing found to real firmware/OTA version data, but it's forum content, not a structured feed.
- Stability: PROMISING but UNVERIFIED — affiliation and structure need a follow-up check before relying on it
- Role: would be MONITORING (firmware/OS build tracking) if confirmed official; do **not** use as a DISCOVERY or CONFIRMATION source given the unresolved first-party question

### 14. Region subdomains generally (`us.nothing.tech`, `in.nothing.tech`, presumably others e.g. `nothing.tech` default = UK)
- Findings: Same Shopify sitemap/collections/products architecture per region, confirmed structurally identical for `us.nothing.tech/sitemap.xml`. Catalog **contents differ by region** — confirmed directly: `nothing.tech/products/cmf-phone-1` → 404, `in.nothing.tech/products/cmf-phone-1` → 200 (CMF Phone 1 sold in India, not UK/US storefront; India listing itself links out to Flipkart for actual purchase rather than direct checkout).
- Role: DISCOVERY/CONFIRMATION, but multi-region crawling is necessary — a single-region sitemap crawl (e.g. UK only) will systematically miss region-exclusive devices like CMF Phone 1.

## Recommended discovery source

**`https://nothing.tech/sitemap/products/1.xml`** (and region-equivalent sitemaps, e.g. `us.nothing.tech`, `in.nothing.tech`), reached via `https://nothing.tech/sitemap.xml` as the index/entry point. This is the closest analogue to the Samsung support-sitemap pattern: an official, structured, low-noise (relative to full-text scraping), machine-parseable feed that lists every product slug Nothing has ever published, including brand-new ones as soon as they're live on the store. It requires a slug-filtering step (see Identifier notes) and should be crawled per-region to catch region-exclusive devices (e.g. CMF Phone 1 in India).

## Recommended monitoring source

**`https://nothing.tech/sitemap/collections/1.xml` + `/collections/phones` and `/collections/cmf`** for tracking "currently for sale" state changes (additions/removals from curated collections, `lastmod` deltas), combined with re-fetching known `/products/{slug}` pages periodically to catch price/availability/variant changes. `nothing.community` OS changelog threads are a promising secondary monitoring signal for firmware/OS build tracking specifically, but affiliation is unverified (see above) — treat as tentative, not gold-standard, until confirmed official.

## Recommended confirmation source

**`https://nothing.tech/products/{slug}`** individual product pages (per region). A slug discovered via the products sitemap should be confirmed by fetching its product page and checking: (a) HTTP 200, (b) page title contains a "Phone (" or "CMF Phone" pattern rather than an accessory/apparel term, (c) presence of price + color/storage variant selectors (a genuine device product page) rather than a single-variant accessory SKU layout.

## Rejected / dead-end sources (and why)

- **`cmf.tech`** — REJECTED. 301-redirects into `nothing.tech`; not an independent source, would create duplicate/aliased data if crawled separately.
- **`nothing.tech/pages/support-software-download`** — REJECTED for firmware/OTA purposes. Only links to app-store listings for companion apps, no build/version/device data.
- **`support.nothing.tech/hc/en-us`** — BLOCKED. Returned HTTP 403 to WebFetch; unclear if this is bot-detection or general access policy. Not investigated further per effort constraints (this is not the Geekbench anti-bot situation, but it does need a real browser-based recheck before anyone builds against it — flagged as open question, not rejected outright).
- **Geekbench** — out of scope per standing instruction; not investigated.
- **Homepage (`nothing.tech/`)** — not rejected outright but downgraded to background-context only: it's a curated marketing subset (misses older/discontinued models) and mixes phones with accessories in the same nav without a clean structural separation for automated parsing.

## Identifier format notes

Real, confirmed Nothing marketing names (from live page titles / collection listings, UK+global store, 2026-08-10):
- Phone (1), Phone (2) [not currently listed for sale but slug exists in sitemap: `phone-1`, `phone-2`]
- Phone (2a) — inferred from `phone-2a-the100-drops-edition-london` slug (a special edition variant); base "Phone (2a)" slug was not independently seen in the current sitemap snapshot (may have been retired from the live sitemap post-lifecycle — the sitemap reflects *current* catalog, not full history)
- Phone (3), Phone (3a), Phone (3a) Pro, Phone (3a) Lite
- Phone (4a), Phone (4a) Pro, Phone (4b)
- CMF Phone 1 (India-region storefront only, confirmed live; sold via Flipkart link-out rather than direct Shopify checkout)

Internal hardware codes (A063/A065/A142-style) were **not found anywhere on nothing.tech** in this recon — those identifiers, if needed, will have to come from a different source (regulatory filings, teardown/leak sites) and are out of scope here.

What must NOT be accepted as a device from these sources:
- Bare slug pattern matches containing "phone" that are actually accessories: `phone-1-case`, `phone-1-screen-protector`, `phone-2-case`, `phone-2-case-screen-protector`, `phone-2-screen-protector`, and all `spigen-*-phone-*` case/screen-protector SKUs.
- `phone-3-drop` and `phone-3-upgrade` / `phone-3-upgrade` static page — these are promotional/trade-in campaign pages, not device identifiers.
- `cmf-phone-1-case` — an accessory, easily confusable with an actual "CMF Phone 1" entry; the real device slug is `cmf-phone-1` (region-gated), the accessory is `cmf-phone-1-case`.
- Generic bare "Phone" with no parenthesized number/suffix — not a valid identifier on its own; Nothing's naming always includes a number and optional letter suffix (2a, 3a, 3a Pro, 3a Lite, 4a, 4a Pro, 4b).
- Any Nothing-brand non-phone product sharing sitemap space: `ear-*`, `headphone-*`, `cmf-buds-*`, `cmf-watch-*`, `cmf-power-*`, `cmf-clip-pro`, `cmf-neckband-pro`, `cmf-headphone-pro*`, apparel (`nothing-hoodie`, `nothing-tracksuit-*`, `nothing-overall`, etc.), Teenage Engineering collab bags, gift cards, and warranty/damage-protection SKUs (`accidental-damage-*`).

## CMF relationship observations (descriptive only, no schema decision made)

- `cmf.tech` redirects (301) into `nothing.tech` — CMF has no independently hosted storefront today.
- All CMF products (phones, buds, watches, power accessories) are sold as Shopify products under the same `nothing.tech` domain and site-wide sitemap, using a `cmf-` slug prefix (e.g. `cmf-phone-1`, `cmf-buds-2-plus`, `cmf-watch-3-pro`).
- There is a dedicated `/collections/cmf` collection page that aggregates all CMF-branded SKUs together, separate from `/collections/phones` (which, per direct observation, contains zero CMF-prefixed slugs — CMF Phone 1 did not appear in `/collections/phones` on the region checked).
- Nothing's own legal/compliance copy (`/pages/product-data-information`) consistently refers to the sub-line as "**CMF by Nothing**" (phones, earbuds, watches), always keeping "by Nothing" attached — this is Nothing's own official phrasing for the relationship, not a third-party label.
- CMF Phone 1 is region-gated: absent (404) from the UK/default `nothing.tech` storefront, present (200) on `in.nothing.tech`, and even there the "buy" action routes out to Flipkart rather than a native Shopify checkout — suggesting CMF Phone 1 in India is fulfilled through a third-party retail partner rather than Nothing's own direct-to-consumer checkout flow used for mainline Phone (x) devices.
- No CMF Phone 2 (or later) was found anywhere in this recon (not on nothing.tech, not on in.nothing.tech, not in search results scoped to this task) — could not confirm whether a CMF Phone 2 exists/existed; treat as unconfirmed rather than absent.

These are observations only — whether the system should model CMF as `manufacturer=CMF, parent_brand=Nothing`, as a Nothing sub-line, or some other structure is explicitly left to a separate schema decision.

## Regional limitations

- nothing.tech geo-redirects by IP to region-specific subdomains (confirmed: default/UK, `us.nothing.tech`, `in.nothing.tech`); each region subdomain runs its own independent Shopify sitemap/product/collection set.
- Catalog contents differ meaningfully by region — CMF Phone 1 is the clearest confirmed example (India-only availability). A single-region crawl will under-discover; a multi-region crawl strategy is needed to match the "genuine public first-party source" discovery bar for region-exclusive devices.
- Currency/price/availability naturally differ by region and should not be treated as conflicting evidence — same device, region-local presentation.
- Not all regions were checked in this recon (only default/UK, US, India were touched); a full rollout should enumerate Nothing's actual list of storefront regions before committing to a fixed set.

## Blocking issues / open questions

1. **`support.nothing.tech` (Zendesk) returned HTTP 403** to WebFetch. Unclear if this is a general bot-block (Cloudflare/Zendesk edge protection) or something else. Needs a real-browser check before any decision to use or exclude it; not resolved in this recon.
2. **`nothing.community` official affiliation is unconfirmed.** `/about` 404'd during this recon. Search results (thread titles, structure) strongly suggest official Nothing OS changelog content is posted there, but direct verification of Nothing Technology Limited's ownership/operation of that domain was not completed. Do not treat as first-party until confirmed.
3. **No Next.js `__NEXT_DATA__` found.** The original task hypothesis that nothing.tech is Next.js-based was not confirmed — the storefront presents as a standard Shopify theme. Worth double-checking with a JS-executing browser fetch (this recon used non-JS WebFetch) before fully ruling out a hydration-JSON shortcut, but no evidence of it was found.
4. **Shopify `.json` product endpoint (`/products/{slug}.json`) was not tested.** Shopify conventionally exposes a structured JSON representation of every product at this suffix; if it works here it would be a cleaner CONFIRMATION source than parsing HTML. Recommended as a fast follow-up check before implementation.
5. **Full region list unknown.** Only 3 regions were spot-checked (default/UK, US, India). A complete inventory of Nothing's storefront regions (likely surfaced via a region/country selector on the site, not fetched in this recon) is needed to size the multi-region crawl properly.
6. **Historical/discontinued slugs**: Phone (2a) base slug wasn't found in the current sitemap (only a special-edition variant was); this suggests the sitemap reflects live catalog only and older discontinued devices may silently disappear from it over time. If historical completeness matters, the sitemap alone is insufficient and a supplementary confirmed-device registry (manually seeded or via secondary sources) may be needed — flagged, not solved, here.
