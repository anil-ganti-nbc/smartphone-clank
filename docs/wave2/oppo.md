# Oppo recon

## Sources probed

- `oppo.com/robots.txt` → single sitemap: `www.oppo.com/sitemap.xml`
  (not individually inspected for a phone-specific sub-sitemap — see
  known limitations below).
- `oppo.com/en/smartphones/` — category/index page, HTML.

## Identity structure

The `/en/smartphones/` page enumerates the full current lineup with clean,
deterministic per-model URLs:

    /en/smartphones/series-find-x/find-x9-ultra/
    /en/smartphones/series-find-n/find-n6/
    /en/smartphones/series-reno/reno16-pro/
    /en/smartphones/series-a/a6-pro-5g/

Path segments (`series-find-x`, `series-find-n`, `series-reno`, `series-a`)
give a reliable family classifier for free. ~80 model entries were visible
across Find X/Find N/Reno/A series, all with distinct slugs — no accessory,
earbud, or watch entries appeared on this page (Oppo separates those into
different top-level categories).

This is a monitoring/confirmation-grade source technically (a curated
current-lineup page, not an exhaustively enumerable sitemap) but it already
surfaced very recent flagship entries (Find X9 Ultra, Find N6, Reno16
series) — good novelty signal in practice even without formal DISCOVERY
status.

## Automation safety

SAFE. No CAPTCHA/bot-block encountered on the category page or robots.txt.

## Update (final pre-soak expansion mission, 2026-08-11): sitemap decomposed

`oppo.com/sitemap.xml` is a sitemap **index** of 134+ regional sitemaps.
`oppo.com/en/sitemap.xml` (the global English storefront) is a direct URL
list — a true enumerable sitemap, not a curated page — with clean category
isolation baked into the path:

    /en/smartphones/series-find-x/find-x8-pro/[specs/]
    /en/smartphones/series-reno/reno13-pro/[specs/]
    /en/smartphones/series-a/a5-pro-5g/[specs/]

vs. `/en/accessories/`, `/en/tablets/`, `/en/wearables/`, `/en/audio/`,
`/en/routers/` — all separate top-level path prefixes, zero overlap with
`/en/smartphones/`. ~150+ phone product URLs found (Find X/Find N/Reno/A
series, `/specs/` sub-pages deduplicated to parent), including
current-generation models (Find X8, Reno13, A5-series). This resolves the
original blocker entirely — the prior "curated category page" caveat no
longer applies once the true sitemap is used as the discovery source.

## Verdict: BUILD_NOW

Upgraded from BUILD_WITH_LIMITS. True enumerable sitemap, clean
category-path isolation from every non-phone product line, zero
automation friction, current-generation models present. See
`docs/wave2/OPPO_CANARY_REPORT.md` for qualification/canary results.
