# Honor recon

## Sources probed

- `honor.com/robots.txt` (redirects from `hihonor.com`) → single sitemap:
  `honor.com/honor-all-sitemap.xml`.
- `honor-all-sitemap.xml` — sitemap index, one entry per locale
  (`/cn/sitemap.xml`, `/global/sitemap.xml`, `/in/sitemap.xml`,
  `/my/`, `/pk/`, `/ie/`, `/sg/`, ...). `cn` locale further splits into
  `knowledge-sitemap.xml`, `shop/sitemap.xml`, `m/sitemap.xml`.
- `honor.com/global/sitemap.xml` — **direct URL list**, not a further index.

## Identity structure

Every product category has its own path segment —
`/phones/`, `/laptops/`, `/wearables/`, `/tablets/`, `/audio/`,
`/routers/`, `/accessories/` — so phone-vs-non-phone filtering is a plain
path-prefix check, no content sniffing needed. Example entries:

    /global/phones/honor-magic-v6/
    /global/phones/honor-magic-v6/spec/
    /global/phones/honor-magic8-pro/
    /global/phones/honor-600-pro/
    /global/phones/honor-600-pro-molly/   (regional/carrier variant)

Identifier is the marketing-name slug (`honor-magic8-pro`), not a formal
model number — same tier as Wave 1's OnePlus/Nothing sources, not as strong
as Motorola's SKU-grade slugs. `/spec/` and `/tips/` sub-pages under each
model are CONFIRMATION surfaces, not separate devices — must be
deduplicated to the parent slug before treating as a new candidate.

Catalogue is current: `honor-magic8-pro`, `honor-magic-v6` (both current
generation, no obvious Huawei-era stale entries in the sample). The
Huawei-era-support-artefact risk the mission flagged wasn't observed in the
`/global/` locale sample — worth re-checking if `/cn/` is ever added, since
that locale is far larger and older.

## Automation safety

SAFE. robots.txt, sitemap index, and the `/global/` leaf sitemap all
returned 200 with no bot-defense friction.

## Verdict: BUILD_NOW

Second-best candidate after Motorola. Structured, phone-isolable, current,
low operational cost if scoped to `/global/` (English-language international
storefront) rather than all locale sitemaps.
