# Realme recon

## Sources probed

- `realme.com/robots.txt` → single sitemap: `realme.com/sitemap.xml`
  (`Disallow: /login`, `Disallow: /search` — neither affects product pages).
- `realme.com/sitemap.xml` — sitemap index, per-country leaf files
  (`sitemap-af-fr.xml`, `sitemap-bd.xml`, `sitemap-bg.xml`, `sitemap-bo.xml`,
  `sitemap-br.xml`, `sitemap-by.xml`, `sitemap-co.xml`, `sitemap-cr.xml`,
  `sitemap-cz.xml`, `sitemap-eg.xml`, ... — dozens of country codes visible
  in just the first page of the index).
- `realme.com/sitemap-uk.xml` — leaf sitemap, direct URL list (9 entries).

## Identity structure

    /eu/realme-16-5g
    /eu/realme-16-5g/specs
    /eu/realme-16-pro-5g
    /eu/realme-16-pro-5g/specs
    /eu/realme-16-pro-plus-5g
    /eu/realme-16-pro-plus-5g/specs

`/{cc}/{device-slug}` and `/{cc}/{device-slug}/specs` is a clean, consistent
pattern — the `/specs` page is a confirmation sub-page of the same device,
not a separate candidate. The sampled region (`eu`) shows only 3 devices,
all current-generation (realme 16 series) — small but genuinely fresh.

The mission's specific warning about Realme — "marketing text pollution,
long promotional product strings" — was **not observed** in this sitemap
sample; slugs here are clean model names, not promo copy. That risk is more
likely to show up on category/landing pages (not probed in this pass) than
in the sitemap itself. A validator must still fail closed against
promotional strings as a defensive measure regardless.

## Automation safety

SAFE. No bot-defense signals on robots.txt or either sitemap level probed.

## Operational cost — the main concern

The sitemap index fragments into a very large number of small per-country
files (dozens observed, likely 50+ total based on the index page alone).
Each country's leaf sitemap is small (9 entries for `uk`), meaning full
global coverage requires many low-yield requests. A handful of high-value
regions (EU, India, global/international if one exists) likely captures
nearly all real novelty without polling every country file every cycle.

## Update (final pre-soak expansion mission, 2026-08-11): India sitemap checked

`realme.com/sitemap-in.xml` (India — Realme's largest single market): 80
URL entries, all current-generation (realme 15/15T/15x/16/16 Pro/16 Pro
Plus/16T series, GT7, Narzo/P-series), `lastmod` July 2026. Far stronger
signal than the earlier 3-device EU sample. The promotional-text risk the
mission specifically flagged for Realme **was confirmed real** — but only
on the landing/category page (`realme.com/in/`: "Camera Powered by RICOH
GR", "India's First & Biggest 10001mAh Battery Smartphone", "Buy Now"/
"Learn More" CTAs, Buds Air8 Pro and other audio products mixed in) — not
in the sitemap slugs themselves, which remain clean model names
(`realme-16-5g`, not marketing copy). This confirms the sitemap is the
right discovery source (not the landing page), and that the validator
must still fail closed against promotional phrases as defense in depth
even though the sitemap-slug source doesn't currently produce them.

## Verdict: BUILD_NOW

Upgraded from RESEARCH_MORE. Clean per-device identity, no automation
friction, confirmed current-generation coverage via the India sitemap,
promotional-text risk understood and mitigated at the validator layer.
See `docs/wave2/REALME_CANARY_REPORT.md` for qualification/canary
results.
