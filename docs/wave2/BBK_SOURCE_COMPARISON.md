# BBK Source Comparison

Oppo, Vivo, and Realme share a corporate parent (BBK Electronics). This
document answers the mission's explicit question honestly:
**similarity must be discovered, not assumed.** It was — and the three
turned out to be less alike than the shared ownership might suggest.

## Comparison table

| Capability | Oppo | Vivo | Realme |
|---|---|---|---|
| Enumerable official catalogue | **YES** — `oppo.com/en/sitemap.xml`, direct URL list | PARTIAL — exists only on some regions | **YES** — `realme.com/sitemap-{cc}.xml`, per-country |
| Sitemap available | YES (single `/en/` sitemap, not an index) | YES (index of 50 regional sitemaps) | YES (index of 50+ per-country sitemaps) |
| Product-only filtering possible | **YES** — `/en/smartphones/` path segment cleanly separates from `/en/accessories/`, `/en/tablets/`, `/en/wearables/`, `/en/audio/`, `/en/routers/` | Not applicable — see below | **YES** — no non-phone content observed in any regional sitemap sampled |
| Regional duplication | Single global `/en/` sitemap used — no duplication problem | Inconsistent: `/uk/` has products, `/en/` (global) and `/in/` and `/au/` do not (corporate/news-only) | Yes — same device appears across `/eu/`, `/in/`, other country sitemaps; requires cross-region dedup, same pattern as Motorola |
| Stable canonical identity | YES — `/series-{family}/{model}/[specs]` path, family classifier free | YES where present — `/products/param/{model}` | YES — `/{cc}/{device-slug}[/specs]` |
| Static HTML / no JS | YES (sitemap is static XML; category page also server-rendered) | YES (sitemap is static XML) | YES (sitemap is static XML) |
| JS required | NO | NO | NO |
| Structured metadata | Path segments only (no JSON-LD observed) | Path segments only | Path segments only |
| Rate limiting observed | None | None | None |
| 403/429 observed | None | None | None |
| CAPTCHA/bot challenge | None | None | None |
| Safe polling cadence | 2-4 polls/day (static sitemap, matches Motorola/Honor pattern) | N/A this mission | 2-4 polls/day on a handful of high-value regional sitemaps |

## Phase 4 — is shared plumbing justified?

**Q1: Do Oppo, Vivo, and Realme genuinely expose sufficiently similar
discovery structures to justify shared code?**

No. Despite the common corporate parent, the three URL taxonomies are
meaningfully different:

    Oppo:   /en/smartphones/series-{family}/{model}/[specs]/
    Vivo:   /{region}/products/param/{model}    (where present at all)
    Realme: /{cc}/{device-slug}[/specs]

Oppo encodes a family/series taxonomy directly in the path. Vivo uses a
flat `param`-style identifier with no family segment. Realme uses a flat
slug with no category or family segment and no `/products/` prefix at
all. A generic parser would need to know, per manufacturer, which path
shape to expect — which is exactly per-OEM logic, just relocated into a
shared file instead of three files.

**Q2: Would shared code reduce complexity?**

No. The genuinely shared parts — HTTP fetching with politeness delays,
XML sitemap parsing, candidate deduplication, metrics reporting — are
**already shared**, via `collectors/wave1/adapter.py`
(`DiscoveryAdapter`/`AdapterMetrics`/`DiscoveryResult`) and
`collectors/wave1/common.py` (`pre_filter`). Every OEM adapter built so
far (Google, Nothing, OnePlus, Motorola, Honor) already reuses this
infrastructure. There is nothing BBK-specific left to factor out beyond
what the existing contract already provides.

**Q3: Would shared code instead create conditional spaghetti?**

Yes — a `BBKDiscoveryAdapter` would immediately need
`if manufacturer == "oppo": ... elif manufacturer == "vivo": ...` branches
for path parsing, exactly the anti-pattern the mission warns against, for
zero complexity benefit over three independent ~100-line adapter files.

## Decision

**No BBK abstraction is built.** Oppo and Realme (where qualified — see
their own recon/canary docs) each get an independent adapter and
validator, following the exact same `collectors/wave1/*` contract
Motorola and Honor already use. Vivo remains in research/staging — its
own recon doc explains why independently, not as a consequence of Oppo's
or Realme's outcome (per the mission's explicit instruction that one
BBK-family manufacturer's success must not influence another's score).

## What actually is shared (and always was)

- `collectors/wave1/adapter.py` — `DiscoveryAdapter` base class, `_get()`
  polite-fetch helper, `AdapterMetrics`, `DiscoveryResult`.
- `collectors/wave1/common.py::pre_filter()` — hostile-text rejection
  heuristics (cookie/promo/nav text, accessory/watch/tablet/audio/charger/
  case keyword denylists, sentence detection).
- `collectors/wave1/validator.py` — the `ValidationOutcome`/`VALID`/
  `INVALID`/`AMBIGUOUS` contract every OEM validator implements.
- `collectors/wave1/staging_pipeline.py::run_oem_staging_cycle()` — the
  one integration path every OEM (Wave 1 or Wave 2) enters production
  through.

This was true before this mission and remains true after it. Nothing
new was added to accommodate Oppo/Realme — the existing generic
infrastructure was sufficient, which is itself evidence that no BBK-
specific abstraction was ever needed.
