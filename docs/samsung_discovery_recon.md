# Samsung US Discovery Reconnaissance — v0.3.1

**Date:** 2026-08-02  
**Method:** Polite public GETs only. No auth, no bypass, no brute force.

## Summary

| Surface | HTTP | Type | Exposes unknown product URLs? | Status |
|---------|------|------|-------------------------------|--------|
| `https://www.samsung.com/us/sitemap.xml` | 200 | sitemap index | via nested sitemaps | **LIVE_VALIDATED** |
| `https://www.samsung.com/us/support_sitemap.xml` | 200 | urlset (~836 locs) | **Yes** — 133+ phone product support pages | **LIVE_VALIDATED** |
| `https://www.samsung.com/us/smartphones/` | 200 | category HTML | marketing/buy links | LIVE_PARTIAL |
| `https://www.samsung.com/us/smartphones/all-smartphones/` | 200 | category HTML | limited static links | LIVE_PARTIAL |
| `https://www.samsung.com/us/support/owners/product/{slug}` | 200 | product HTML | requires known slug | monitoring only |
| robots.txt root | 200 | text | lists regional sitemaps | LIVE_VALIDATED |
| India/UK support hosts | 403 | blocked | no | BLOCKED |

## Primary discovery path (validated)

### Support sitemap

```
GET https://www.samsung.com/us/support_sitemap.xml
→ 200 application/xml ~300KB
→ lastmod present on index
```

**Phone product URL pattern discovered:**

```
https://www.samsung.com/us/support/mobile/phones/galaxy-s/galaxy-s25-ultra/
https://www.samsung.com/us/support/mobile/phones/galaxy-a/galaxy-a36-5g/
https://www.samsung.com/us/support/mobile/phones/galaxy-z/galaxy-z-fold8/
```

**Count:** 133 paths matching `/support/mobile/phones/{series}/{product}/`

**Live model extraction examples (2026-08-02):**

| URL (from sitemap, not seeded) | Extracted model |
|--------------------------------|-----------------|
| `.../galaxy-s/galaxy-s25-ultra/` | `SM-S938UAKAXAA` → canonical `SM-S938U` |
| `.../galaxy-a/galaxy-a36-5g/` | `SM-A366ULGAXAA` → canonical `SM-A366U` |

This is **true discovery**: the system learns product URLs from Samsung’s public sitemap without a pre-supplied slug list.

### Nested index

`us/sitemap.xml` points to:

- `b2c-sitemap.xml`
- `top_sitemap.xml`
- `support_sitemap.xml` ← primary for Clank
- `help_content_sitemap.xml`
- business sitemaps (not relevant)

## What is NOT discovery

- Hardcoded `seed_paths` under `/us/support/owners/product/` (v0.3 behaviour) = **monitoring of known pages**
- Marketing `/us/smartphones/galaxy-s26-ultra/buy/` links = useful for name hints, not model SKUs reliably
- Search endpoints (`/us/search/`) = disallowed / not used

## Safe to poll?

| Source | Safe? | Notes |
|--------|-------|-------|
| support_sitemap.xml | Yes | ~300KB, conditional GET friendly, update ~daily |
| Individual support product pages | Yes | rate-limited sequential fetch |
| Category JS search UIs | Low value | static HTML often empty of SM- tokens |

## Limitations

1. Sitemap lists **commercially published** support pages — unreleased unlisted devices will not appear.
2. Owners product URLs (`/support/owners/product/...`) are **not** in the support sitemap; different surface.
3. Some series pages are category hubs without model numbers.
4. Carrier suffixes appear in page body; validator strips to canonical regional form.
5. Sitemap may lag product launches by hours/days.

## Conclusion

Samsung US is **discovery-capable** via `support_sitemap.xml` for mobile phone support product pages.  
Previous slug-based collector remains valid for **monitoring** known owners pages, but is no longer the discovery mechanism.
