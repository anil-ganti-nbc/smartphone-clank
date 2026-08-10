# Xiaomi / Redmi / POCO — Source Reconnaissance

Date: 2026-08-10
Method: Live HTTP probing (curl with a real browser User-Agent, following redirects, inspecting response bodies) plus WebFetch/WebSearch for corroboration. All URLs below were actually fetched during this session — status codes and body observations are real, not assumed. Requests made from a US/India-routed network path (exact geo-IP not controlled); Xiaomi's CDN (Akamai/Tengine) served `xm_geo=IN` cookies during this session, so results may reflect an India-biased edge even when a "global" path was requested.

Geekbench was excluded per instructions and was not investigated.

## Candidate surfaces

### 1. `https://www.mi.com/robots.txt`
- Region: global root (redirects region-specific traffic elsewhere; this path itself is served directly)
- Content type: text/plain
- HTTP status: 200
- Auth: none
- robots.txt: simple, short — `Disallow: /*/cart`, `/*/site/`, `/*/user/`, `/*/misc/`, `/*/search_`, `/*/search/`. No `Sitemap:` directive present at all (last-modified header on the file itself is stale: Jan 2022).
- Pagination/rate-limit signals: none observed at this path
- JS dependency: none (static text file)
- Model identifiers exposed: none (it's a robots file)
- Stability: LIVE_VALIDATED as a robots policy reference, but it provides no sitemap pointer, so it doesn't function as a discovery entry point the way Samsung's did.
- Classification: **MONITORING** (policy check only) — not useful for discovery.

### 2. `https://www.mi.com/global/robots.txt` and `https://www.mi.com/global/sitemap.xml` (and other guessed sitemap paths)
- Region: global
- HTTP status: 302 → redirects to `https://www.mi.com/global/errors/404` (confirmed via `curl -D -`). Same result for `/global/sitemapindex.xml`, `/sitemap_index.xml`, `/sitemapindex.xml`, `/sitemap-index.xml`, `/global/sitemap-product.xml` — all 302 to the same 404 error page.
- Content type: text/html (error page)
- Conclusion: there is no discoverable machine-readable XML sitemap at any of the conventional paths under the `/global/` locale. Unlike Samsung, Xiaomi does not appear to expose a public XML product/support sitemap at guessable URLs.
- Classification: **REJECTED** for discovery — no XML sitemap found despite systematic path guessing.

### 3. `https://www.mi.com/global/sitemap/` (HTML sitemap, trailing slash, no `.xml`)
- Region: global
- Content type: text/html
- HTTP status: 200
- Auth: none required
- Body size: ~228 KB, real content (not a JS shell)
- What it exposes: a large, hand-curated-looking HTML page enumerating essentially all live Xiaomi/Redmi/POCO product URLs, e.g. `https://www.mi.com/global/product/redmi-note-14-pro-plus-5g/`, `https://www.mi.com/global/product/poco-pad-x1/`, `https://www.mi.com/global/product/redmi-buds-6-pro/`, plus accessories, smart home, and non-phone categories all mixed together.
- Identifiers exposed: URL slugs only (marketing-name-derived, e.g. `redmi-note-14-pro-plus-5g`) — no internal model codes (M-codes) or codenames visible in this page's links.
- Pagination: none — appears to be a single flat page.
- Rate-limit signals: none observed on a handful of requests.
- JS dependency: none for the link list itself (present in static HTML).
- Last-modified hints: none in-page; HTTP headers didn't include Last-Modified for this endpoint.
- Stability: worked consistently across repeated fetches this session.
- Classification: **PROMISING** for DISCOVERY (best XML-sitemap substitute found), and usable as a seed list for CONFIRMATION (a product slug appearing here confirms mi.com currently sells/lists that device). Caveat: mixes phones with non-phone products (chargers, mice, humidifiers, air conditioners) — any collector must filter to `/product/` slugs that are actually phones, which is non-trivial from the URL alone (needs a category check or page-content check).

### 4. `https://www.mi.com/global/product-list/`
- Region: global
- HTTP status: 200
- Not deeply inspected beyond status; likely a JS-driven catalogue/filter UI parallel to the sitemap page. Treated as a secondary confirmation of the same product universe already covered by candidate 3.
- Classification: **LIVE_PARTIAL** — confirmed reachable, content structure not fully characterized this session.

### 5. `https://www.mi.com/global/phone/` (phone category landing page)
- Region: global
- HTTP status: **403 Forbidden**, served by `AkamaiGHost` (Akamai edge, not origin) — this is Xiaomi's CDN/WAF, not a generic 404.
- Auth: none offered; this looks like bot/automation blocking, not an auth wall.
- Classification: **BLOCKED**. Per instructions, not attempting to work around this.

### 6. `https://www.mi.com/global/support/`, `https://www.mi.com/global/miui/download/`
- HTTP status: 403 (support/) and 302 (miui/download/, redirects — target not resolved to a stable 200 this session)
- `/global/support/` returned 403 via Akamai on the WebFetch tool call (same signature as candidate 5).
- Classification: **BLOCKED** (support/) and **UNSTABLE** (miui/download redirect target not confirmed).

### 7. `https://www.mi.com/in/support/`
- Region: India
- HTTP status: **inconsistent** — one fetch returned 200 with a real 111 KB HTML body (title "Xiaomi India", links to `/in/support/my-device/`, `/in/support/warranty/`, `/in/service/support/laptop-drivers.html`, etc.), a later fetch of the same URL (same UA) returned 403 via `AkamaiGHost`. This flip-flopping between 200 and 403 on identical requests is a hallmark of adaptive bot-detection (request-rate or fingerprint-based), not a stable content endpoint.
- Content when reachable: a support portal index (categories, policy links) not a device catalogue — no model numbers or device list visible in the top-level page.
- Classification: **UNSTABLE / BLOCKED** (treat as blocked for automated collection purposes — a collector that gets 200 today and 403 tomorrow on the same request is not a reliable discovery source per the incident lesson).

### 8. `https://www.mi.com/global/poco/` (POCO storefront section)
- Region: global
- HTTP status: 200
- Content type: text/html, ~266 KB real body
- Title: "Xiaomi POCO, POCO Store - Xiaomi GLOBAL"
- What it exposes: POCO is **not** a separate top-level domain in the current global storefront — it lives at `mi.com/global/poco/` alongside Xiaomi/Redmi. Product links found: `/global/product/poco-f8-pro/`, `/global/product/poco-f8-ultra/`, `/global/product/poco-m8-pro-5g/`, `/global/product/poco-x8-pro-max/`, `/global/product/poco-x8-pro/`.
- Social links on the page point to distinct POCO-branded accounts (`facebook.com/POCOGlobalOfficial`, `instagram.com/poco.global`, `youtube.com/@POCOGlobal`, `x.com/POCOglobal`) — POCO maintains its own brand identity/marketing presence even though the storefront is unified under `mi.com`.
- Classification: **LIVE_VALIDATED** as a CONFIRMATION source (same site/pattern as candidate 3, subset filtered to POCO) and usable for DISCOVERY of new POCO products the same way.

### 9. `https://poco.com/`
- HTTP status: connection failure (TLS SNI/cert mismatch — `SEC_E_WRONG_PRINCIPAL`). This domain does not serve the POCO brand's certificate; not a usable endpoint.
- Classification: **REJECTED** — wrong/unrelated domain.

### 10. `https://www.pocoglobal.com/`
- HTTP status: 302 → redirects to `hugedomains.com/domain_profile.cfm?d=pocoglobal.com`
- This is an expired/parked domain listed for sale on HugeDomains. Not affiliated with Xiaomi/POCO.
- Classification: **REJECTED** — dead/squatted domain, do not use.

### 11. `https://www.pocophone.com/`
- Connection failed (HTTP 000 / no response in the time allotted). Historically POCO's older marketing domain; appears unreachable/decommissioned now. Not further pursued.
- Classification: **REJECTED** — unreachable.

### 12. `https://www.poco.net/`
- HTTP status: 301 redirect observed; target not resolved to a stable Xiaomi-owned endpoint this session. Not pursued further given candidate 8 (`mi.com/global/poco/`) already provides a confirmed, live, first-party POCO surface.
- Classification: **UNSUPPORTED** (not investigated to conclusion — deprioritized once the official POCO surface was found at mi.com).

### 13. `https://www.mi.com/global/service/support/declaration.html`
- HTTP status: 301 → redirects to `https://www.mi.com/global/support/terms/declaration/` (a "Declaration of Conformity" / regulatory-compliance page). This is the kind of official page that, on some OEM sites, lists regulatory model numbers. Redirect target was not fetched to completion this session (deprioritized after the store/product pages showed no model-number leakage — see identifier notes below); flagged as an open question for a follow-up pass.
- Classification: **UNSUPPORTED** (not fully investigated — worth a dedicated follow-up, see Open Questions).

### 14. Individual product pages, e.g. `https://www.mi.com/global/product/redmi-note-14-pro-plus-5g/` and its `/specs/` subpage
- HTTP status: 200, large real bodies (158–284 KB)
- Searched exhaustively (regex for `M[0-9]{4,7}[A-Z0-9]{1,8}` model-number pattern, `"model"` JSON keys, `codename` strings) — **zero regulatory model codes or codenames found** on either the marketing page or the specs subpage. These pages expose only marketing names ("Redmi Note 14 Pro+ 5G"), no internal `M20xxJxxSY`-style identifiers.
- Classification: **LIVE_PARTIAL** for CONFIRMATION of marketing-name existence/pricing/specs, but **REJECTED** as a source of the internal model identifier needed for entity identity — this is exactly the trap the incident warned about (a collector must not accept the URL slug or marketing string as "the model number").

### 15. `xiaomifirmwareupdater.com` (formerly a well-known community firmware tracker)
- HTTP status: 200 for the root, but body is a domain-parking/for-sale page ("This website is for sale! — xiaomifirmwareupdater Resources and Information"), and sub-paths like `/miui/` and `/api/devices.json` returned non-standard 439/441 statuses (parking-page redirect infrastructure, not real content).
- Conclusion: this domain has **lapsed and is now squatted/parked**. It is not usable, and it is not first-party Xiaomi either way.
- Classification: **REJECTED** — dead domain, do not use despite name recognition.

### 16. `github.com/XiaomiFirmwareUpdater` (org) and `github.com/XiaomiFirmwareUpdater/xiaomi_devices` (repo)
- HTTP status: 200
- Content: the actual XiaomiFirmwareUpdater project has moved its presence to GitHub (org still active). The `xiaomi_devices` repo README states: "This repo contains codenames and names in English/Chinese of all Xiaomi devices. Auto updated always." Related repos (`miui-downloads`, `mi-firmware-updater`, `xiaomifirmwareupdater.github.io` with `data/devices/*.yml`) contain codename ↔ device-name ↔ firmware mappings (e.g. sample data referenced "atom" = Redmi 10X 5G China, "begonia" = Redmi Note 8 Pro China style entries).
- Important: **this is a community/enthusiast project, not an official Xiaomi source.** It is auto-scraped from Xiaomi's own OTA infrastructure by third parties and is not authoritative in the "genuine public first-party source" sense the Samsung gold-standard requires.
- Classification: **PROMISING but explicitly NOT first-party** — flagged as a possible *secondary corroboration/enrichment* source (codename↔model↔name cross-reference) but must not be treated as a DISCOVERY or CONFIRMATION source per the "genuine first-party" bar. If used at all, it should be MONITORING/enrichment only, with explicit provenance labeling distinguishing it from OEM-official evidence.

### 17. `mirom.ezbox.idv.tw` (Taiwan-hosted community MIUI/HyperOS ROM mirror with its own sitemap.xml)
- HTTP status: 200, real XML sitemap returned, e.g. `https://mirom.ezbox.idv.tw/phone/chagall/roms-eea-stable/`, `roms-global-stable/`, `roms-id-stable/`, `roms-in-stable/` — codename-keyed (`chagall`) with per-region ROM channel pages.
- This is a **third-party mirror**, not an official Xiaomi domain. Same caveat as #16: useful structurally (shows how codename+region+channel are organized) but not first-party.
- Classification: **REJECTED for DISCOVERY/CONFIRMATION** (not first-party); **noted for reference only** as an example of how the codename/region/channel structure looks in practice.

## Recommended discovery source

`https://www.mi.com/global/sitemap/` (candidate 3), narrowed to `/global/product/<slug>/` links, cross-checked against `https://www.mi.com/global/poco/` (candidate 8) for the POCO sub-brand specifically. This is the only first-party, consistently-200, real-content surface found that enumerates live products including ones the system wasn't already told about. It is **not** an XML sitemap (no such thing was found despite systematic probing), so any collector built on it needs an HTML-link-extraction step rather than an XML parser, and needs a phone-vs-accessory filter since the page mixes categories. Given the incident history, extraction should be limited to structural link discovery (the `/product/<slug>/` URL pattern) — not regex-over-marketing-text for model numbers, since candidate 14 showed those pages carry no reliable model-code text at all.

## Recommended monitoring source

Same as discovery — `https://www.mi.com/global/sitemap/` / `https://www.mi.com/global/poco/` — re-fetched periodically to detect new product slugs appearing. No official RSS/API/XML feed was found. `mi.com/robots.txt` should also be periodically re-checked in case a `Sitemap:` directive is ever added.

## Recommended confirmation source

The individual product page for a given slug (e.g. `https://www.mi.com/global/product/<slug>/` and its `/specs/` subpage) confirms the marketing name, region availability, and spec claims exist and are live — but explicitly **cannot** confirm an internal model/regulatory identifier, since none was found on these pages. If a genuine model-number confirmation source is required, the redirect target of candidate 13 (`https://www.mi.com/global/support/terms/declaration/`) is the most promising untested lead and should be the first thing checked in a follow-up pass before falling back to community sources.

## Rejected / dead-end sources (and why)

- `mi.com/global/sitemap.xml` and every other guessed XML sitemap path — all 302 to a 404 error page; no XML sitemap exists at conventional locations.
- `mi.com/global/phone/`, `mi.com/global/support/` — 403 Akamai block (BLOCKED, not worked around per instructions).
- `poco.com` — TLS/SNI failure, wrong domain.
- `pocoglobal.com` — expired domain parked on HugeDomains.
- `pocophone.com` — unreachable.
- `xiaomifirmwareupdater.com` — domain lapsed, now a parking page; the real project lives on GitHub instead (and even there it's third-party, not first-party).
- Product/specs pages as an identifier source — confirmed to expose zero model codes/codenames after direct inspection; do not build a regex-over-page-text collector against these pages, which is exactly the class of mistake from the August 2026 incident.
- The generic-regex-over-`mi.com/support/`-page-text approach already in the repo — not re-validated positively by anything found here; the support pages that were reachable (`mi.com/in/support/`) are a policy/portal index with no device list, and the ones with plausible device content (`/global/support/`, `/global/phone/`) are blocked (403). No evidence surfaced that this generic collector pattern would work any better for Xiaomi than it did for the other OEMs in the incident.

## Identifier format notes

- Xiaomi/Redmi/POCO regulatory **model numbers** follow the pattern `M` + 4 digits (often a year-ish prefix) + letters, e.g. `M2007J3SY` (per the task's own example, corresponding to codename "cmi" / marketing name "Redmi K30 Pro"). This session did **not** find any first-party mi.com page exposing this format live — it is documented here from the task brief and general knowledge, not verified against a live official page today. Any collector must not treat unverified example identifiers as validated; this needs live confirmation in a follow-up pass (see declaration.html lead above).
- **Codenames** (internal project names like "chagall", "cmi") are lowercase single words, used throughout MIUI/HyperOS build strings, ROM filenames, and firmware update infrastructure. They were only observed in third-party sources (mirom.ezbox.idv.tw, XiaomiFirmwareUpdater GitHub repos) during this session, not on any first-party mi.com page.
- **Marketing names** (e.g. "Redmi Note 14 Pro+ 5G", "POCO X8 Pro Max") are the only identifier type confirmed present on first-party mi.com pages, always as URL slugs and page titles/copy — never accompanied by the internal model code on the same page.
- **What must NOT be accepted as a model identifier**: URL slugs (`redmi-note-14-pro-plus-5g`) are marketing-name-derived strings, not regulatory model numbers, and must not be persisted as if they were a device's canonical model ID. Similarly, no string matching generic patterns pulled from marketing copy (e.g. via regex over page text) should be trusted as a model number without cross-validation against a structured field — this is precisely the August 2026 incident failure mode, and nothing found in this recon changes that risk assessment for Xiaomi.

## Brand relationship observations

- **Xiaomi and Redmi** are not separated by domain: `mi.com/global/product/redmi-*` sits directly alongside Xiaomi-branded products in the same sitemap and same URL namespace. Redmi does not appear to have (or need) a distinct storefront domain in the "global" region observed.
- **POCO** occupies its own URL section (`mi.com/global/poco/`) with its own landing page, title ("Xiaomi POCO, POCO Store - Xiaomi GLOBAL"), and — notably — its own distinct social-media identity (separate Facebook/Instagram/YouTube/X accounts branded "POCO Global", not "Xiaomi"). This suggests POCO is treated as a semi-autonomous sub-brand: unified checkout/storefront infrastructure under `mi.com`, but independent brand marketing. This matches the task's instruction to not collapse Xiaomi/Redmi/POCO into one manufacturer — POCO in particular reads as its own brand riding on shared Xiaomi commerce infrastructure.
- No evidence was found this session of a genuinely separate POCO domain still being live and first-party (poco.com, pocoglobal.com, pocophone.com were all dead/wrong/squatted) — the only confirmed-live official POCO web presence is the `mi.com/global/poco/` path.

## Regional limitations

- All requests in this session resolved through an edge that set `xm_geo=IN` cookies even on `/global/` paths, meaning "global" content may already carry an India-region bias; true China-region (`mi.com` root without `/global/` or `/in/`, or `c.mi.com`) content was not meaningfully accessible — `c.mi.com/global/miuidownload/index` returned 403, and no China-specific storefront path was successfully fetched.
- `mi.com/in/support/` showed non-deterministic 200/403 behavior on identical requests within the same session — this strongly suggests region-specific (India) bot/WAF policies are stricter or more adaptively enforced than the `/global/` storefront pages, and any India-specific collector would need to be built assuming intermittent blocking, not treated as reliably scriptable.
- No EEA-specific domain or path was identified as distinct from `/global/` during this session; the `/global/support/policy/digital-service-act/` link (seen in the POCO page's footer) suggests EEA/DSA compliance content exists but was not fetched or characterized.
- Because China-region access could not be validated, any codename-to-model mapping sourced from Chinese-market-first launches (which is common for Xiaomi/Redmi — China launch often precedes global) cannot be confirmed as complete from this vantage point; this recon should be treated as Global/India-observable only.

## Blocking issues / open questions

- No official XML sitemap was found anywhere on `mi.com` despite systematic path guessing — this is a fundamentally different discovery shape than the Samsung gold-standard pattern (official support sitemap XML), and any Xiaomi collector needs a different discovery mechanism (HTML link-scraping of `mi.com/global/sitemap/`, filtered to `/product/` phone slugs).
- `mi.com/global/phone/` and `mi.com/global/support/` are actively blocked (403, Akamai) for this session's request pattern — flagged as BLOCKED per instructions, not bypassed. It is unknown whether a lower request rate, different UA, or session/cookie warm-up would change this; that investigation was intentionally not pursued (would edge toward bypassing bot detection).
- The redirect target `https://www.mi.com/global/support/terms/declaration/` (candidate 13) was not fetched to completion this session — it is the single most promising untested lead for finding genuine regulatory model numbers on a first-party page, and should be the first follow-up action.
- It remains unconfirmed whether any first-party mi.com page ever exposes the `M2007J3SY`-style model number directly (as opposed to only being visible in-device, on regulatory labels, or via retailer/carrier filings) — this is a real open question, not an assumption to build a collector on.
- The existing repo's generic regex-over-`mi.com/support/`-page-text collector pattern (same class as the incident) was not positively validated by anything found here, and given that reachable support pages carry no device list and unreachable ones are blocked, there is no evidence this pattern is salvageable for Xiaomi either.
