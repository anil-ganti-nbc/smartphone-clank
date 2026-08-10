# OnePlus — Source Reconnaissance

Date: 2026-08-10
Scope: research only, no code written. All URLs below were actually fetched (via WebFetch) during this session; status codes and content descriptions reflect real observed responses, not assumptions. Geekbench was excluded per instructions and was not investigated.

## Candidate surfaces

### 1. `robots.txt` — https://www.oneplus.com/robots.txt
- Region: global (root domain)
- Content type: text/plain
- HTTP status observed: 200
- Auth: none
- Robots.txt considerations: N/A (this *is* the robots file). It disallows `/api/`, `/checkout/`, `/order/`, `/account/sign-in?*`, `/user/`, `/support/index/`, `/academy`, `/starwars` for all user agents, and blocks several known scraper tools (HTTrack, Xenu, Python-urllib) by name. Sitemaps and ordinary product/support pages are **not** disallowed.
- Pagination: N/A
- Rate-limit signals: none observed on this request
- JS dependency: none — plain static text file
- What it exposes: a list of **69 regional `Sitemap:` entries**, one per country/locale (e.g. `/us/`, `/in/`, `/global/`, `/de/`, `/au/`, `/cn/`, `/hk/`, `/global/`, etc.), plus the root `/sitemap.xml`.
- Model identifiers / marketing names: none directly; it's a pointer to sitemaps.
- Release-state hints: none
- Last-modified hints: none
- Stability assessment: **very stable** — robots.txt format is simple and this is the authoritative map of every regional storefront's sitemap URL.
- Classification: **LIVE_VALIDATED** — reliable, fetchable, and directly useful as the entry point that enumerates every regional sitemap to crawl. Not itself a discovery source of devices, but the correct starting point for one.
- Role: **DISCOVERY** (index of discovery sources)

### 2. Root sitemap — https://www.oneplus.com/sitemap.xml
- Region: global/default
- Content type: expected application/xml
- HTTP status observed: **403 Forbidden** (confirmed on two separate attempts)
- Auth: none required in theory, but requests are being blocked — likely bot/WAF detection specifically on the root path (regional variants under the same domain returned 200 for the same fetcher/user-agent in the same session)
- JS dependency: N/A, never got a body
- Stability assessment: **unstable/blocked** for this specific URL, even though sibling regional sitemaps on the identical domain succeeded.
- Classification: **BLOCKED**
- Role: N/A (unusable)

### 3. Regional sitemap — https://www.oneplus.com/us/sitemap.xml
- Region: United States
- Content type: application/xml, `<urlset>` (flat list, not a sitemap index)
- HTTP status observed: 200
- Auth: none
- Robots.txt: not disallowed
- Pagination: none — single file, **146 total `<url>` entries**
- Rate-limit signals: none observed
- JS dependency: none — pure static XML, no rendering needed
- What it exposes: Product-page URL slugs directly at `/us/{slug}`, including current flagship/mid-range lineup: `oneplus-13`, `oneplus-13r`, `oneplus-12`, `oneplus-12r`, `oneplus-open`, `oneplus-n30-5g`, `oneplus-11` and bare `11`, `10t`, `10-pro`, `9-pro`, `9`, `8t`, plus Nord/N-series (`n20-5g`, `n200-5g`, `n100`, `n10-5g`). Also `/us/store/phone` (category page). No CPH model codes appear in the sitemap itself — only marketing-name slugs.
- Marketing names exposed: yes, via URL slug (inconsistent format — sometimes `oneplus-13`, sometimes bare `11`/`10t`/`9`, i.e. naming convention changed over product generations).
- Regional identifiers: implicit via the `/us/` path prefix; no explicit region code field.
- Release-state hints: none explicit, but presence/absence of a slug reasonably tracks with the device having a live US storefront page.
- Last-modified hints: **every single entry shares the identical `lastmod` timestamp** (`2025-06-20T05:16:38+01:00` as observed) — this is almost certainly a whole-sitemap regeneration timestamp from the site build/deploy, not a genuine per-page last-modified signal. Do not treat individual lastmod values as trustworthy freshness signals; treat the presence of a new slug as the real signal.
- Stability assessment: **good** — small (146 URLs), flat, static XML, current lineup present (OnePlus 13/13R/12/12R/Open all listed), well within instruction-following crawl budget.
- Classification: **LIVE_VALIDATED**
- Role: **DISCOVERY** (finds new device slugs before the system is told about them) and weak **MONITORING** (new slug appearing = new device signal, though lastmod is not trustworthy for staleness detection)

### 4. Regional sitemap — https://www.oneplus.com/global/sitemap.xml
- Region: "Global" storefront (distinct from country-specific stores)
- Content type: application/xml, `<urlset>`
- HTTP status observed: 200
- JS dependency: none
- What it exposes: product slugs like `/global/10-pro`, `/global/10t`, `/global/9-pro`, `/global/11`, `/global/9`, `/global/8t`, `/global/8-pro`, `/global/8`, Nord/N-series, plus `/global/support/softwareupgrade` and `/global/oxygenos12` marketing pages.
- Last-modified hints: dates range up to **2023-05-06** at the latest observed (`n10-5g`) — nothing more recent.
- **Critical finding: this sitemap is stale/abandoned.** It contains no entries for OnePlus 12, 12R, 13, 13R, or Open — devices released well before this recon date (2026-08-10). The "Global" storefront variant appears to have stopped being maintained/regenerated sometime after OnePlus 11's launch (~2023), even though the URLs still resolve.
- Stability assessment: **unstable for discovery purposes** — technically live (200 OK) but functionally dead as a source of new devices; would silently miss every device since 2023.
- Classification: **UNSTABLE** (live but stale — a trap if used as primary discovery source; would falsely appear healthy while missing all new releases)
- Role: none recommended (superseded by country sitemaps like `/us/`)

### 5. OnePlus support pages (rendered) — https://www.oneplus.com/us/support, /us/support/softwareupdate, /us/support/softwareupgrade/details?code=5, /global/support/softwareupgrade
- Region: US and Global variants tested
- Content type: text/html
- HTTP status observed: 200 for `/us/support/softwareupgrade/details?code=5` and `/global/support/softwareupgrade`; **404** for `/us/support/softwareupdate` (wrong path — correct path is `softwareupgrade`, not `softwareupdate`)
- Auth: none required to load the shell
- JS dependency: **heavy** — confirmed Vue.js template shells. Raw HTML contains unrendered mustache placeholders such as `{{item.phoneName}}`, `{{item.versionNo}}`, `{{getFormatTime(item.versionReleaseTime)}}`, `{{item.versionSign}}` (MD5), `{{errMsg}}`, `{{user.signedIn}}`. A plain HTTP fetch retrieves the app shell only — **no actual device names, CPH codes, or OxygenOS version numbers are present** until client-side JS executes and calls a backend API.
- The likely backend API lives under `/api/...`, which **robots.txt explicitly disallows** — this is a real blocking consideration even for a compliant, non-crawling fetch-on-demand collector design.
- Stability assessment: **not usable via plain HTTP fetch**. Would require a headless-browser render step, which is a materially different (and heavier/more fragile) architecture than the Samsung sitemap→fetch→parse pattern, and even then would be reading against a disallowed-by-robots API path.
- Classification: **BLOCKED** (for a plain-fetch collector; would be UNSUPPORTED/out-of-pattern even if a JS renderer were added, given the robots.txt disallow on the underlying API)
- Role: none recommended

### 6. Product marketing pages — https://www.oneplus.com/us/13, https://www.oneplus.com/global/11/specs
- Content type: text/html
- HTTP status: 200
- JS dependency: mixed — `/us/13` (main product page) renders mostly as static marketing prose with some interactive JS widgets (color picker, toggles); `/global/11/specs` (specs subpage) is a full Vue template shell with unrendered `{{...}}` placeholders and **no usable spec table or model code in raw HTML**.
- What it exposes: no JSON-LD (`application/ld+json`) product schema found on either page. No CPH model codes found anywhere in visible text, meta tags, or scripts on `/us/13`.
- Stability assessment: unreliable as identifier source — this is exactly the kind of free-form marketing prose page that produced the prior OnePlus collector's garbage extractions (e.g. "ONEPLUSSHOP"-style false positives). A hostile-to-prose validator must **not** attempt to regex CPH codes or model identifiers out of these pages.
- Classification: **REJECTED** for identifier extraction (usable only as weak corroboration of "this slug is a real product," which the sitemap already tells you)
- Role: none recommended as a primary source; at most a secondary confirmation that a discovered slug is a genuine product page (HTTP 200 + product-shaped content) rather than the identifier source itself.

### 7. `downloads.oneplus.com` (found via web search, e.g. `https://downloads.oneplus.com/devices/oneplus-one/`)
- HTTP status observed: **DNS resolution failure** (`ENOTFOUND downloads.oneplus.com`) — the subdomain does not resolve at all.
- Stability assessment: **dead domain**, decommissioned. Old links to it circulate in search results and old forum posts but the host itself is gone.
- Classification: **REJECTED** (dead end — do not build anything expecting this subdomain to exist)
- Role: none

### 8. Country support redirect chain — https://www.oneplus.com/in/support → https://www.oneplus.in/support → https://service.oneplus.com/in
- Observed a two-hop 301 redirect chain: `oneplus.com/in/support` → `oneplus.in/support` → `service.oneplus.com/in` (final host).
- Content type: text/html
- HTTP status: 200 at final destination
- What it exposes: raw HTML is a near-empty stub (`<title>Support - OnePlus (India)</title>` plus a generic heading) — no device list, no CPH codes, no JSON. Almost certainly another JS-rendered SPA shell that needs client-side execution to populate.
- Stability assessment: unusable via plain fetch; also demonstrates that OnePlus support properties for at least one major region (India) live on an entirely separate `service.oneplus.com` host, so "support.oneplus.com/{region}" URL patterns cannot be assumed uniform across regions.
- Classification: **BLOCKED**
- Role: none recommended

### 9. `community.oneplus.com` forum (circle pages and rollout-announcement threads)
- Examples tried: `/circle/1227621534836195329` (OnePlus 11 Series circle), `/thread/1964330002061197316` ("OxygenOS 16: Device list and rollout" thread, found via web search)
- Content type: text/html
- HTTP status: 200
- JS dependency: **confirmed SPA shell** — raw fetch of the circle page returned only `<title>OnePlus Community</title>` and generic chrome (account controls, TRUSTe badge, footer links) with no thread/device content; real content is injected client-side.
- What it would expose if rendered: community/staff-authored prose posts that mention device names and CPH numbers inline in free text (confirmed via web search snippet: *"[CLOSED] My device is CPH 2611 AND I got the update for glob..."* — this is exactly the unstructured-prose shape that produced the prior collector's garbage output).
- Auth: browsing appears unauthenticated, but content requires JS execution to appear at all.
- Stability assessment: even if a JS-capable fetch were added, the payload is human-written forum prose, not structured data — the highest-risk source for regex-over-text false positives. Directly analogous to the OnePlus support-page mistake this recon is meant to prevent.
- Classification: **REJECTED** for identifier discovery/extraction. Possibly a low-confidence **MONITORING** signal for humans (a new "OxygenOS N: Device list and rollout" thread title reliably correlates with a real rollout event) but not something a strict automated validator should parse for model identifiers.
- Role: **MONITORING** only, and only as a "something happened, check other sources" signal — never DISCOVERY or CONFIRMATION.

## Recommended discovery source

**Country-specific regional sitemaps under `oneplus.com/{region}/sitemap.xml`, starting with `https://www.oneplus.com/us/sitemap.xml`** (LIVE_VALIDATED, 200 OK, static XML, 146 URLs, current lineup through OnePlus 13/13R/12/12R/Open present at recon time).

Recommended pattern, mirroring the Samsung gold standard: fetch `robots.txt` → enumerate the 69 regional `Sitemap:` URLs → fetch each regional sitemap (flat `<urlset>`, not an index) → filter `<loc>` entries to top-level product slugs under the region prefix (excluding known non-product paths: `/store/`, `/support/`, `/blog/`, `/legal/`, `/press/`, `/customer/`, `/brand`, `/sustainability`, `/trade-in`, `/rcc/`, `/redcoins-center`, `/affiliate-program`, `/accessibility`) → each surviving slug is a discovery candidate.

**Important caveat vs. Samsung**: the sitemap exposes only the **marketing-name slug** (e.g. `oneplus-13`, `11`, `10t`), not a CPH model code. OnePlus's structural discovery surface and its identifier-bearing surface are two different things — unlike Samsung where the support page itself yields the model identifier. A validator built for OnePlus must treat the marketing-name slug as the primary discovered identifier and *not* attempt to force a CPH-style code out of pages that don't expose one cleanly (see Identifier format notes below).

Multi-region crawl is advisable since sitemaps vary wildly in freshness (see `/global/` finding below) — `/us/` should be treated as the trustworthy baseline, with other country sitemaps cross-checked opportunistically but never assumed current without verification.

## Recommended monitoring source

Re-fetch `https://www.oneplus.com/us/sitemap.xml` (and optionally 2-3 other confirmed-live regional sitemaps, e.g. `/in/`, `/de/`, `/au/` — **not independently verified as live in this session**, `/in/sitemap.xml` returned 403 on both attempts here and should be re-tested) on a periodic cadence and diff the slug list against previously known slugs. Because the shared `lastmod` timestamp is not a trustworthy per-page signal (see finding #3), **new-slug-appearing** is the only reliable monitoring signal from this source, not lastmod deltas.

## Recommended confirmation source

None of the candidates investigated qualify as a clean CONFIRMATION source in the Samsung sense (a second independent structured field that corroborates the discovered identifier). The strongest available option is weak: fetching the product marketing page at the discovered slug (`https://www.oneplus.com/us/{slug}`) and confirming it returns HTTP 200 with product-shaped static content (not a 404/redirect-to-search) — this confirms the slug is a real, live product page, but it does **not** yield or corroborate a CPH model code, since none of the tested product/specs pages exposed one in static HTML. This should be treated as a placeholder confirmation step, not a validated pattern, and flagged for further recon (e.g. checking certification-body sources like regional wireless/telecom regulators, which is out of scope for this pass) if CPH-level confirmation is actually required by the system.

## Rejected / dead-end sources (and why, so nobody repeats the research)

- **`https://www.oneplus.com/sitemap.xml` (root/default)** — consistently returns 403 even though sibling regional sitemaps on the same domain return 200. Do not use; use a specific regional sitemap instead.
- **`https://downloads.oneplus.com/...`** — the subdomain no longer resolves (DNS NXDOMAIN). Old links exist in search results/forum posts; the service is gone.
- **`https://www.oneplus.com/{region}/support/softwareupdate`** — wrong path, returns 404. The correct segment is `softwareupgrade`, not `softwareupdate`.
- **`/support/softwareupgrade` pages (any region)** — real content requires JS execution against an underlying API that lives under `/api/`, which `robots.txt` explicitly disallows. Not usable via plain HTTP fetch, and not clean to pursue even with a headless renderer given the robots directive.
- **`community.oneplus.com`** — SPA shell requiring JS execution, and even when rendered the payload is human-written prose (forum posts), the exact failure mode (regex-over-prose false positives) that this recon exists to avoid repeating.
- **`service.oneplus.com/{region}`** (support landing, reached via a 301→301 redirect chain from `oneplus.com/{region}/support`) — stub HTML, no device data, apparently another JS shell.
- **Product/specs marketing pages** (e.g. `/us/13`, `/global/11/specs`) — no JSON-LD, no CPH codes in static HTML; specs subpages are pure Vue template shells. Do not attempt identifier extraction from these.
- **`/global/sitemap.xml`** — not dead (200 OK) but functionally abandoned; last real update ~May 2023, missing every device since OnePlus 11. Would silently under-report if used as the primary or only sitemap. Keep it out of the primary discovery rotation, or if included, never let its absence-of-new-slugs be treated as "no new devices exist."

## Identifier format notes

Confirmed via secondary/corroborating sources (community forum snippet quoting a user's own device, plus published device-model reference articles) — **not independently confirmed against a first-party structured OnePlus page in this session**, since no tested OnePlus URL exposed a CPH code in static, parseable form:

- Canonical format: **`CPH` + 4 digits**, e.g. `CPH2649`, `CPH2653`, `CPH2655`, `CPH2447`, `CPH2611`, `CPH2745`.
- **CPH codes are region-specific, not device-specific** — the same marketing device gets a different CPH number per region. Observed example (OnePlus 13): `CPH2649` (India), `CPH2653` (EU/Global), `CPH2655` (North America). Observed example (OnePlus 15, per secondary source): `CPH2745` (India), `CPH2747` (Global). A validator must not assume a 1:1 mapping between marketing name and CPH code — expect a small set (typically 2-4) of valid CPH codes per marketing device.
- **China-market variants use a different prefix entirely**: `PLK` (e.g. `PLK110` for OnePlus 15 in China), not `CPH`. Some region/carrier variants have also been referenced with an `SPH` prefix (e.g. `SPH2647` alongside `CPH2645`/`CPH2647` for the 13R). A strict validator targeting global/US/India markets can reasonably require `^CPH\d{4}$`, but should not hard-fail on `PLK`/`SPH` if China or carrier-variant coverage is ever in scope — treat those as a separate recognized prefix set rather than silently rejecting or silently accepting arbitrary prefixes.
- What is **NOT** a model number (the class of false positive the prior collector produced): free-form marketing/brand strings and promotional sentences scraped from page prose, e.g. "ONEPLUSSHOP", full sentences like feature-toggle copy, section headings, or JS variable/placeholder names (`errMsg`, `phoneName`, `searchData.welcome`) that leak into text extraction when a page is actually an unrendered JS template. A hostile validator should: (a) require the exact `^CPH\d{4}$` (or explicitly-allowlisted alternate-prefix) shape with no surrounding word characters, (b) never accept a match pulled from a `<script>`/template-placeholder context, (c) never accept multi-word or sentence-length matches, and (d) prefer identifiers sourced from URL path segments or sitemap `<loc>` values over anything extracted from rendered/prose page body text — since, per this recon, OnePlus's actual structured surface (the sitemap) yields marketing-name slugs, not CPH codes, the practical implication is that CPH-code extraction should probably not be attempted from any of the sources investigated here at all; slug-based discovery is the safe path.

## Regional limitations

- 69 regional sitemap variants exist per `robots.txt`; only `/us/`, `/global/`, and (partially, via error) `/in/` were actually tested in this session.
- `/us/sitemap.xml`: confirmed live and current.
- `/global/sitemap.xml`: confirmed live but stale since ~2023 — do not treat as authoritative for current lineup.
- `/in/sitemap.xml`: returned 403 on both attempts in this session — inconclusive; needs retest, possibly transient bot-detection rather than a permanent block (root `/sitemap.xml` showed the same 403 pattern while `/us/` and `/global/` succeeded, so 403s on specific paths do not necessarily mean the whole region is blocked forever).
- India-specific support infrastructure lives on a different host chain (`oneplus.com/in` → `oneplus.in` → `service.oneplus.com/in`) rather than a uniform `oneplus.com/{region}/support` pattern — do not assume URL-pattern uniformity across regions when extending beyond `/us/`.
- China (`/cn/`) was not tested at all in this session; given the CPH→PLK prefix change noted above, China should be treated as architecturally different and investigated separately if ever in scope.

## Blocking issues / open questions

1. Why does `oneplus.com/sitemap.xml` (root) 403 while `oneplus.com/us/sitemap.xml` and `oneplus.com/global/sitemap.xml` return 200 on the same domain, same session? Not resolved in this recon — could be WAF path-specific rule, could be transient. Worth a retest with a different fetch tool/user-agent before ruling the root path out permanently, though it isn't needed since regional sitemaps work directly.
2. `/in/sitemap.xml` 403 — unresolved, needs retest; India coverage is currently a gap.
3. No first-party static/structured source that exposes CPH model codes was found anywhere in this session. If the system's data model actually requires CPH-level identifiers (not just marketing-name slugs), that is an open architecture question — none of the investigated official sources deliver it without JS execution against a robots-disallowed API, or without falling back to prose (forum posts, third-party device-database articles) that carries the same false-positive risk this recon exists to avoid. Recommend scoping OnePlus discovery to marketing-name-slug identifiers only, and treating CPH-code enrichment as a separate, not-yet-solved problem rather than forcing a weak source into service.
4. Whether a JS-capable render step (headless browser) is architecturally acceptable for this system was not addressed by the task scope — this recon assumed a Samsung-pattern plain-HTTP-fetch collector, per the "hostile toward free-form page text" and structured-source framing in the brief. If headless rendering is later deemed acceptable, the `/support/softwareupgrade` endpoints (which clearly have a real backend API driving them, per the Vue binding names) would be worth revisiting — but note the underlying API path is under `/api/`, which is `robots.txt`-disallowed, raising a policy question independent of the technical feasibility.
