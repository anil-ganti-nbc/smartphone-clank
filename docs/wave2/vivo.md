# Vivo recon

## Sources probed

- `vivo.com/en/robots.txt` → single sitemap: `vivo.com/sitemaps.xml`.
- `vivo.com/sitemaps.xml` — sitemap index, 52 regional entries
  (`/tr/`, `/de/`, `/fr/`, `/uk/`, `/eu/`, `/au/`, `/bh/en/`, ...).
  **No `iqoo.com` or `/iqoo/` entry appears anywhere in the index.**
- `vivo.com/uk/sitemap.xml` — leaf sitemap, direct URL list.

## Identity structure

    /uk/products/param/v21
    /uk/products/param/v235g
    /uk/products/param/x60pro
    /uk/products/param/x80pro
    /uk/products/picture/v21   (image-gallery view of the same model, not a
                                 separate device)

`/products/param/{model}` is the reliable identity path; `/products/picture/`
mirrors the same model set as an alternate view and must be deduplicated
against `/param/` entries, not treated as new candidates.

The sample skewed toward older models (v21, x60pro, x80pro — several
generations back for the UK storefront specifically); a fresher-model check
against a bigger/more current regional sitemap (e.g. `/in/` or global) is
warranted before concluding novelty potential, since this one region's leaf
sitemap alone reads more like legacy catalogue than active new-model
signal.

## iQOO — explicit non-merge finding

Per the mission's explicit instruction not to auto-merge iQOO into Vivo:
**the vivo.com sitemap architecture does not naturally expose iQOO at all.**
iQOO's storefront lives on a separate domain (`iqoo.com`), never referenced
anywhere in vivo.com's sitemap index. This means the identity-policy
question the mission raised is moot for this source — there is no
architectural pressure toward merging, because there is no shared surface
to begin with. iQOO would need to be evaluated as an entirely separate
future candidate on its own domain, not folded into a Vivo adapter. Deferred,
per instruction.

## Automation safety

SAFE. robots.txt and both sitemap levels returned 200, no bot-defense
signals.

## Update (final pre-soak expansion mission, 2026-08-11): structural inconsistency confirmed

Checked three more regional sitemaps looking for a fresher product
catalogue than the stale UK sample: `/in/` (India, Vivo's largest single
market), `/en/` (global English), and `/au/` (Australia). **None of the
three contain any `/products/param/` entries at all** — all three are
corporate/news-only sitemaps (`/about-vivo/*`, career pages, press
releases). Of the four regional sitemaps checked in total, only `/uk/`
was found to expose a product catalogue, and it remains the same stale
set found during qualification (v21, x60pro, x80pro — no X200/X300/V50
or other current-generation flagship anywhere in any of the four
sitemaps checked).

This is no longer a "need to check a fresher region" gap — it's now a
confirmed structural finding: Vivo's sitemap architecture does not
reliably expose a live product catalogue across regions the way Oppo's,
Realme's, Motorola's, and Honor's do. Either product URLs live behind a
JS-rendered catalogue page not captured by static sitemap XML, or the
sitemap generator for most regions simply omits the `/products/` section
entirely. Determining which would require deeper reconnaissance
(inspecting a live product listing page's network requests, or checking
whether a non-sitemap discovery surface exists) — genuinely more research,
not a one-region recheck.

## Verdict: RESEARCH_MORE (unchanged, now with stronger evidence)

Not promoted this mission. The identity pattern that does exist
(`/products/param/{model}`) remains clean when present, and automation
safety remains excellent (zero friction across all four regions probed) —
but there is currently no confirmed source of current-generation Vivo
devices via static sitemap. Held in staging pending dedicated
reconnaissance into why most regional sitemaps omit the product catalogue
section. Per the mission's explicit instruction, this verdict was reached
independently of Oppo's and Realme's outcomes.
