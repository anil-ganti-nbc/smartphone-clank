# Motorola recon

## Sources probed

- `motorola.com/robots.txt` → 51 regional sitemap URLs, one per
  country/language pair (`/{cc}/{lang}/sitemap.xml`, e.g. `/us/en/`, `/gb/en/`,
  `/de/de/`). All 200, no bot friction encountered.
- `motorola.com/us/en/sitemap.xml` — **direct URL list** (not a nested index),
  flat and enumerable in one request per region.

## Identity structure

Product URLs follow `/us/en/p/phones/{family}/{variant}/{sku-slug}`, e.g.:

    /us/en/p/phones/razr/razr-2026/pmipmjl44m7
    /us/en/p/phones/moto-g/moto-g-power-2026/pmipmjb42mv
    /us/en/p/phones/xt2309-3/pmipmfq34m3

The `/p/phones/` path segment cleanly isolates phone product pages from
`/family/tablet`, `/family/wearables`, and other non-phone family landing
pages in the same sitemap. The trailing SKU-like slug (`pmipmjl44m7`,
`xt2309-3`) is a deterministic, low-collision identifier — closer to Samsung's
SM-code pattern than to the marketing-name-slug-only sources Wave 1 had to
settle for.

The sitemap is current: it includes `razr-2026`, `moto-g-2026`,
`moto-g-power-2026` — this-generation products, not a stale catalogue.

## Automation safety

SAFE. Plain HTTP GET on robots.txt and sitemap XML returned 200 with no
bot-defense signals across every regional sitemap probed. 51 regional
sitemaps is a real operational cost if all are polled every cycle, but a
handful (US, GB/EU, one APAC) likely cover the great majority of new-model
announcements without needing all 51 on a tight schedule.

## Verdict: BUILD_NOW

Best Wave 2 candidate. True discovery surface (structured, enumerable,
phone-isolable, current), SKU-grade identity, zero automation friction
observed. Lenovo ownership was checked for shared infrastructure — none
found; motorola.com is self-contained and does not expose or require any
Lenovo PC/laptop surface.
