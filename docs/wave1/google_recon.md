# Google / Pixel — Source Reconnaissance

**Date:** 2026-08-10
**Method:** Polite public GETs only (WebFetch) + real browser session (rendered DOM, network log, robots.txt checks). No auth, no bypass, no brute force. Geekbench explicitly excluded per instructions.

## Summary

| Surface | HTTP | Type | JS required? | Role | Status |
|---|---|---|---|---|---|
| `store.google.com/sitemap.xml` | 200 | sitemap index (40 regional sitemaps) | No | enumeration | LIVE_VALIDATED |
| `store.google.com/sitemap/sitemap_us.xml` (and other region files) | 200 | urlset, `/us/product/{slug}` and `/us/category/{slug}` paths | No | MONITORING (of known slugs) | LIVE_VALIDATED |
| `store.google.com/category/phones?hl=en-XX` | 200 | server-rendered HTML | No (real content present without interaction) | DISCOVERY + MONITORING | LIVE_VALIDATED |
| `store.google.com/product/{slug}?hl=en-XX` | 200 | server-rendered HTML, Google "Wiz/boq" framework | No for text; internal data blob present but opaque | CONFIRMATION | LIVE_PARTIAL |
| `developers.google.com/android/ota` | 200 | TOS-walled table | Yes, and wall did not open even after a real trusted click in this session | CONFIRMATION (if unblocked) | BLOCKED |
| `developers.google.com/android/images` | 200 | TOS-walled table | Yes, same wall behavior | CONFIRMATION (if unblocked) | BLOCKED |
| `support.google.com/pixelphone/` + sitemap | 200 (page); no real sitemap.xml resolves | generic topic/answer CMS | No | none usable | REJECTED |
| `blog.google/products/pixel/rss/` | 200 | valid RSS 2.0 feed | No | CONFIRMATION / ANNOUNCEMENT | LIVE_VALIDATED (as a corroboration signal only) |
| `blog.google/rss/` | 200 | valid RSS 2.0 feed (all of Google, not Pixel-scoped) | No | none usable (too noisy) | REJECTED |
| `developers.google.com/android/new-releases` | 200 | redirects/serves generic Android dev landing page in this session, not a distinct changelog | — | none usable | UNSUPPORTED |

robots.txt checked for all three domains — none of the candidate paths above are disallowed by robots.txt. `store.google.com/robots.txt` explicitly allows `/category`, `/product`, `/accessories`, `/collection`, `/listing` for `User-agent: *` (only cart/checkout/pricing/search endpoints are disallowed). `support.google.com/robots.txt` disallows `/*/search`, `/*/apis`, `/*/api`. `developers.google.com/robots.txt` disallows only `/youtube/partner/` and points to its own sitemap.

## Candidate surfaces

### 1. `https://store.google.com/sitemap.xml`
- **Content type:** `application/xml`, HTTP 200.
- **Structure:** sitemap *index* (not a flat list) → 40 regional sitemaps, e.g. `sitemap_us.xml`, `sitemap_gb.xml`, `sitemap_in.xml`, `sitemap_jp.xml`, `sitemap_de.xml`, etc.
- **Auth:** none required.
- **Robots.txt:** allowed (sitemap referenced directly in robots.txt).
- **Pagination:** none needed — full index in one response.
- **Rate-limit signals:** none observed.
- **JS rendering:** not needed, plain XML.
- **Stability:** high — this is a standard SEO sitemap index, unlikely to change shape.
- **Role:** enumeration/routing layer only — points to the real per-region sitemaps. Not itself a source of model identifiers.

### 2. Regional sitemaps, e.g. `https://store.google.com/sitemap/sitemap_us.xml`
- **Content type:** `application/xml`, HTTP 200.
- **Structure:** `urlset` of `/us/product/{slug}` and `/us/category/{slug}` (and `/us/config/{slug}` for build-your-own configurator variants) plus accessory/case URLs.
- **Model identifiers exposed:** product **slugs** only, e.g. `pixel_10_pro`, `pixel_10_pro_fold`, `pixel_9a`, `bellroy_leather_case_pixel_7_pro`. These are marketing-name slugs, not formal model numbers (no `GA0xxxx`/FCC-ID style strings appear in the sitemap itself).
- **Regional identifiers:** one sitemap file per country/locale (`_us`, `_gb`, `_in`, `_de`, `_jp`, `_ca`, `_au`, ... ~40 total).
- **Last-modified hints:** not confirmed present per-URL in this pass (would need a follow-up fetch of a full regional file — the summarizing WebFetch pass only returned a partial/interpreted list, not raw XML, so `lastmod` presence should be re-verified before relying on it).
- **Role:** primarily **MONITORING** — it lists what Google currently sells, which is useful to detect a slug appearing/disappearing, but by the time a product has its own sitemap entry it is already a formally announced, listed product, so this is a weak DISCOVERY source (it will not show a device before Google publishes the product page).

### 3. `https://store.google.com/category/phones?hl=en-XX` (verified in browser, `en-IN` and `en-US` params tested; the server appears to geo-route by request origin regardless of the `hl` query param in this session — actual served locale should be re-confirmed with a controlled IP)
- **Content type:** HTML, HTTP 200. **Server-rendered** — full page text and anchor links were present in DOM immediately (no wait/interaction needed), unlike the `developers.google.com` download pages.
- **What it exposes:** live marketing names for the entire current lineup, plus **pre-release teasers**. During this recon session (2026-08-10) the page displayed:
  > "Google Pixel 11 series. Pre-order 12 August. ... Sign up — Be the first to know Google Store news – including Pixel 11 Series availability."
  This is a genuinely new, previously-unlisted device name (Pixel 11) surfacing on an official first-party page *before* it has its own dedicated `/product/{slug}` page — this is exactly the kind of "discover a device the system was never told about" signal the Samsung collector pattern is built around.
- **Product links found in DOM:** `a[href*="/product/"]` anchors resolved to concrete slugs: `pixel_10_pro`, `pixel_10_pro_fold`, `pixel_10`, `pixel_10a`, `pixel_9a`, `pixel_9_pro`, `pixel_9`, plus accessories (`pixel_watch_4`, `pixel_buds_pro_2`, etc.).
- **JSON-LD:** one `application/ld+json` block present, but it is `Organization` schema only (Google Store entity, social links) — **no `Product` schema**, so there is no structured JSON to parse for model identifiers; identifiers must come from the anchor-tag slugs and/or the visible marketing-name text (e.g. "Pixel 10 Pro and Pro XL").
- **Auth:** none.
- **Robots.txt:** `/category` explicitly allowed.
- **Rate-limit signals:** none observed in a handful of requests; no CAPTCHA or bot-check encountered.
- **Regional limitations:** the store exists per-country with different catalogs/pricing/availability (`/us/`, `/in/`, `/gb/`, etc.) — a full discovery sweep should hit at least a few major regions (US, UK, DE, IN, JP) since teaser copy or availability dates can differ by region and a device might be visible in one region's category page before another.
- **Stability:** page is marketing-controlled and redesigned periodically (row layout, comparison-table wording change with each generation), so a **text-content** scraper is fragile — anchor-tag slug extraction (`/product/{slug}`) is the more durable signal than parsing prose.
- **Classification:** **LIVE_VALIDATED** as a DISCOVERY source specifically for pre-release marketing-name teasers (e.g. spotting "Pixel 11" ahead of catalog listing), and LIVE_VALIDATED as a MONITORING source for current lineup slugs. It is *not* a source of formal model numbers.

### 4. `https://store.google.com/product/{slug}?hl=en-XX`, e.g. `pixel_10_pro`
- **Content type:** HTML, HTTP 200, server-rendered (marketing copy, storage tiers, EMI/price info all present in the initial DOM).
- **JSON-LD:** same `Organization`-only schema as the category page — no `Product`/`Offer` schema with SKU/GTIN present.
- **Internal data blob:** a `<script id="_ij">` tag (`window.IJ_values = [...]`) containing Google's internal Closure/Wiz bootstrap config — includes the build id (e.g. `boq_gstore-neo_20260730.03_p6`), locale, and the **product slug itself** (`pixel_10_pro`) echoed back, but this is routing/session config, not a product catalog payload. No further product JSON (price/SKU/model-number) was found embedded in page scripts in this pass.
- **Model identifiers exposed:** marketing name only ("Pixel 10 Pro", "Pro 6.3\"", "Pro XL 6.8\""); no formal Google model number (e.g. `GA0xxxx`-style) was found in the rendered text.
- **Requires a known slug:** yes — there is no on-page mechanism to enumerate slugs other than the category page's anchor list or the sitemap, so this endpoint alone is **not** a discovery source; it corroborates/confirms a slug already found elsewhere.
- **Auth:** none for viewing; "Sign in to get notified" CTA appeared instead of "Add to cart" for at least one region during this test, indicating regional stock/availability gating on the *purchase* flow, not the content itself.
- **Classification:** **LIVE_PARTIAL** — real content, useful for confirming a marketing name and basic specs tied to a slug, but not structured enough (no JSON-LD Product, no formal model number) to be a strong validator input on its own.

### 5. `https://developers.google.com/android/ota` (Full OTA Images for Nexus and Pixel Devices)
- **Content type:** HTML, HTTP 200.
- **Robots.txt:** allowed.
- **Structure:** the page ships **without** the actual device/build table in the DOM at all — confirmed by dumping `devsite-content` innerHTML: it contains only the intro paragraphs, terms-and-conditions text, and a single `<button class="devsite-acknowledgement-link" data-globally-unique-wall-id="nexus-ota-tos">Acknowledge</button>`. There is no `<table>` element anywhere in the page, not even hidden/templated.
- **Wall behavior:** clicking Acknowledge — tried both via synthetic `.click()` and via a real trusted `computer` left_click on the resolved element ref — did **not** reveal a table or change the DOM/page text in this session (page text and DOM length were byte-identical before/after both click attempts, across a fresh reload too). This means either (a) the wall requires additional state (cookies/session) not present in this sandboxed browser, (b) it performs an XHR to a backend that failed silently in this environment, or (c) Google has changed this page's behavior since it was last documented elsewhere. Root cause not determined in this pass.
- **No device codenames** (e.g. the commonly known "husky"/"shiba"/"akita"/"comet" style codenames referenced in the task brief) were actually observed by this reconnaissance — I could not verify them directly and did not fabricate confirmation. They should be treated as **unverified** until this wall can be gotten through.
- **Auth:** none required to view the page shell; the acknowledgment gate is the practical blocker.
- **Classification:** **BLOCKED**. Even though HTTP 200 and robots.txt-allowed, it does not currently expose parseable identifiers to an automated client in this environment. Worth a follow-up with a full non-sandboxed browser (real cookies/session, longer wait, checking for a background XHR call the wall may trigger) before writing it off permanently — but do not build a collector against it until someone confirms the table is reachable outside a human-interactive session.

### 6. `https://developers.google.com/android/images` (Factory Images for Nexus and Pixel Devices)
- Identical situation to #5: HTTP 200, robots.txt-allowed, intro text and warnings only ("Pixel 10, 10 Pro, 10 Pro XL, and 10 Pro Fold" mentioned only inside a May-2026 bootloader-update advisory sentence, not in a device listing), TOS-acknowledgment wall present, no table in DOM, wall did not open on click in this session.
- **Classification:** **BLOCKED**, same caveats as above.

### 7. `https://support.google.com/pixelphone/` and its "sitemap"
- **Content type:** HTML, HTTP 200 for the help-center landing page.
- There is **no real per-device sitemap.xml** at `support.google.com/pixelphone/sitemap.xml` — the fetch there resolved back to the generic help-center landing/navigation content, not a machine-readable XML urlset. Google's consumer Help Center (Zendesk-like CMS) organizes content by opaque numeric `topic/{id}` and `answer/{id}` identifiers (e.g. `/pixelphone/topic/7083311`, `/pixelphone/answer/12060041`), not by device model. None of the ~60 URLs enumerated in this pass referenced a specific Pixel model number or model-specific slug — everything is generic ("Pixel Fold", "Pixel phone") topic/answer content.
- This is structurally the **same shape of source** that produced the August 2026 garbage-row incident when a generic regex-over-page-text collector was pointed at Google/OnePlus/Nothing support pages: there is no reliable per-device URL to key discovery off of, and the prose content is marketing/help copy, not model identifiers.
- **Classification:** **REJECTED** for both discovery and monitoring. Support.google.com is not the Google/Pixel analogue of Samsung's `support_sitemap.xml`; Google's consumer support content is not organized per-device the way Samsung's is.

### 8. `https://blog.google/products/pixel/rss/`
- **Content type:** `application/rss+xml`, HTTP 200, valid RSS 2.0, channel title "Google Pixel", scoped to the Pixel product blog category.
- **Content:** post titles like "Pixel 10a: Everything you need, at a price you'll love" (`.../google-pixel-10a/`), "Get your first look at the new Pixel 10a" (`.../google-pixel-10a-first-look-video/`), monthly "Pixel Drop" recaps, and Pixel Care+/refurb posts.
- **What it's good for:** a first-party, low-noise **announcement/timeline signal** — new post appearing with a device name in the URL slug is a reasonable trigger to go look at the Store/OTA sources for that device. It is explicitly **not** a source to regex model identifiers out of the free-text titles (that is the exact mistake being replaced) — the safe signal is the **URL slug** (e.g. `google-pixel-10a`), not the prose title.
- **Auth:** none. **Robots.txt:** blog.google not checked directly in this pass but RSS feeds are conventionally unrestricted; no block encountered.
- **Pagination:** feed appears to return a fixed recent-items window (15 seen); would need date-based dedup for a poller.
- **Classification:** **CONFIRMATION / ANNOUNCEMENT** source only — corroborates that "something Pixel-related shipped" and hints at a slug, but never treat title prose as a model identifier.

### 9. `https://blog.google/rss/` (all of Google, unscoped)
- Valid feed, but content is >95% non-Pixel (Gemini, Maps, Wallet, company news). Too noisy to be worth filtering vs. the dedicated `products/pixel/rss/` feed above.
- **Classification:** REJECTED (redundant and noisier than #8).

### 10. `https://developers.google.com/android/new-releases`
- Navigating to this URL in-session rendered the generic `developers.google.com/android` product landing page (APIs, "What's new" widget cards for unrelated Play services features), not a distinct Pixel/AOSP release changelog with device/version data.
- **Classification:** UNSUPPORTED — either this path has been retired/redirected, or it requires a different exact path than assumed; not usable as found, needs a fresh URL lookup before revisiting, not worth further investigation this round.

## Recommended discovery source

**`https://store.google.com/category/phones?hl=en-XX`** (polled across a handful of regions: at minimum US, and ideally GB/DE/IN/JP for early-teaser variance) is the best available DISCOVERY surface. It is server-rendered, robots.txt-allowed, requires no JS execution wait or interaction, and demonstrably surfaced a not-yet-cataloged device name ("Pixel 11", pre-order teaser dated 12 August) during this very recon session. Discovery should key off of two independent signals scraped from this page: (a) `/product/{slug}` anchor hrefs appearing that were not previously known, and (b) a conservative, narrowly-scoped extraction of "Pixel <number><optional letter/suffix>" patterns from teaser/heading text *only* when adjacent to launch-intent language ("Pre-order", "Coming soon", "Sign up") — never a blanket regex over full page prose (that is the failure mode being replaced). Any hit here should be treated as a low-confidence candidate pending confirmation, not auto-published as a validated entity.

## Recommended monitoring source

**Regional `store.google.com/sitemap/sitemap_{region}.xml` files**, combined with periodic re-fetch of the `/product/{slug}` pages for slugs already known. Once a device has a sitemap entry and a live product page, this pair is a stable, low-noise way to track spec/price/availability changes and to detect the moment a "teaser" slug (found via the category page) graduates into a real cataloged product.

## Recommended confirmation source

**`store.google.com/product/{slug}` page content** (marketing name + storage/price text) for corroborating a candidate slug found via the category page or sitemap. Secondarily, **`blog.google/products/pixel/rss/`** post slugs as an independent first-party corroboration signal (if a `google-pixel-11` post appears, that strongly corroborates a Store-page teaser). Do **not** use OTA/factory-image pages for confirmation until the acknowledgment wall issue (see below) is resolved and their table content has actually been observed by a human or a properly-authenticated automated session.

## Rejected / dead-end sources (and why, so nobody repeats the research)

- **`support.google.com/pixelphone/*`** — no per-device sitemap or URL structure exists; content is organized by opaque topic/answer IDs, not device models. This is structurally the same trap that caused the August 2026 garbage-row incident (regex over generic support/marketing prose). Do not build a collector against Google consumer Help Center pages.
- **`blog.google/rss/` (unscoped)** — valid but overwhelmingly non-Pixel noise; superseded by the scoped `products/pixel/rss/` feed.
- **`developers.google.com/android/new-releases`** — did not resolve to a useful distinct page in this session; not worth pursuing without first re-confirming the correct URL.
- **Geekbench** — out of scope per explicit instruction; not investigated.

## Identifier format notes (for a future strict validator)

- **Pixel marketing names** observed in this recon follow the pattern: `Pixel <generation:int>[<a|Pro|Pro XL|Pro Fold|Fold>]`, e.g. `Pixel 9`, `Pixel 9a`, `Pixel 9 Pro`, `Pixel 10`, `Pixel 10a`, `Pixel 10 Pro`, `Pixel 10 Pro XL`, `Pixel 10 Pro Fold`, and the teased-but-uncataloged `Pixel 11` (series name only, no variant suffix yet observed as of 2026-08-10).
- Store product **URL slugs** are lowercase, underscore-separated, and roughly mirror the marketing name minus spaces/punctuation: `pixel_10_pro`, `pixel_10_pro_fold`, `pixel_10a`, `pixel_9a`. A strict validator should treat a slug as a *candidate*, not a confirmed model, until the corresponding product page 200s and its rendered `<h1>`/title text contains a matching "Pixel <N>..." string.
- No formal Google internal model-number scheme (e.g. an FCC-ID-style or `GxxxxN` token) was observed on any of the public-facing pages fetched in this pass — Google does not appear to expose that identifier tier on Store/marketing pages the way Samsung exposes `SM-XXXXX` codes on its support pages. If a strict numeric/alphanumeric model-number validator is required, the only candidate surfaces that might carry it are the OTA/factory-image pages (currently BLOCKED, see below) or FCC filings (out of scope for this recon, not investigated).
- Marketing-prose text must never be treated as a model identifier by itself — reject any extraction that isn't anchored to either (a) a `/product/{slug}` URL, or (b) a heading/title element, to avoid recreating the August 2026 "PIXEL 11 SERIES AND RECEIVE AN EXCLUSIVE OFFER..." class of false positive.

## Regional limitations

- Google Store is organized per-country (`store.google.com/{cc}/...`); catalog, pricing, and availability differ by region, and pre-order teaser timing may differ by region too. This recon observed the store auto-routing to an `en-IN` locale in one session regardless of the `hl=en-US` query parameter, which suggests locale selection may be driven by request origin/IP rather than purely by the query string — a production collector should not assume `?hl=` alone controls the served region and should verify the actual region served (e.g. by checking currency/price formatting or an explicit `/us/` path prefix) rather than trusting the request parameter.
- The regional sitemap index lists roughly 40 country sitemaps; a full discovery/monitoring sweep would need to decide how many regions are worth polling for cost/latency reasons versus how much earlier a device might surface in one region over another.

## Blocking issues / open questions

1. **OTA/factory-image acknowledgment wall (`developers.google.com/android/ota`, `/android/images`):** the device table is not present in the DOM before acknowledgment, and clicking Acknowledge (both synthetic and real trusted click via the browser tool) did not reveal it in this sandboxed session. Unresolved whether this is a session/cookie issue, a silently-failing background XHR, or a page behavior change. **Needs a follow-up session with full browser network-tab visibility (this session's `read_network_requests` showed no new XHR fired after the click, which is itself suspicious) before any collector work is attempted against these pages.**
2. **No formal Google model-number scheme found** on any public page investigated — if the system's validator design assumes a Samsung-style `SM-XXXXX` alphanumeric code, an equivalent for Pixel was not located in this pass and may not exist on first-party public pages at all (it may live only in FCC filings, teardown/APK strings, or the gated OTA/images tables above).
3. **Region-serving behavior of store.google.com is not fully understood** (see Regional limitations above) — needs a controlled test (e.g. fetching with explicit region path `/us/category/phones` vs. `/in/category/phones`) rather than relying on the `hl` query parameter, before building region-aware discovery logic.
4. **No `Product`/`Offer` JSON-LD or `__NEXT_DATA__`-style state blob was found** on either the category or product pages — Google's store frontend (`boq_gstore-neo`) appears to be a Closure/Wiz-based app that likely fetches product data via internal RPC calls not easily replicated by a simple GET; this recon did not attempt to reverse-engineer those RPC endpoints (out of scope for source recon; flagging as a possible richer-but-riskier future avenue, not recommended to pursue given it's an undocumented internal API).
