# Samsung Collector Audit — v0.3

**Date:** 2026-08-02  
**Scope:** Existing `collectors/samsung_support.py` prior to v0.3 production hardening.

## Current implementation (as of v0.2.1)

### URLs accessed

| URL | Purpose | Status (this environment) |
|-----|---------|---------------------------|
| `https://www.samsung.com/in/support/model/` | India model index | **BLOCKED** (HTTP 403 Akamai) |
| `https://www.samsung.com/us/support/` | US support landing | **LIVE_PARTIAL** (200, no SM- models in static HTML) |
| `https://www.samsung.com/uk/support/model/` | UK model index | **BLOCKED** (HTTP 403) |
| `https://www.samsung.com/in/support/mobile-devices/` | India mobile devices | **BLOCKED** (HTTP 403) |

### Discovery method

- Hardcoded list of 4 TARGETS
- Single GET per URL
- Regex `SM-[A-Z0-9]{4,10}` over full page text
- No pagination, no sitemap, no search API
- No category filtering (any SM- match accepted)
- No model validation beyond regex length

### Regions configured

India, US, UK — as URL paths only. No locale headers, no regional sighting model.

### Pagination

Not implemented.

### Selectors / extraction

- `selectolax` body text dump
- No CSS selectors for product cards
- No structured data (JSON-LD) parsing
- No download section extraction (handled by support_monitor separately)

### Rate limits / retries / caching

- Inherited from `BaseCollector`: min_delay 1.5s, tenacity retries on network errors
- No ETag / If-Modified-Since
- No response-size limit
- No per-host concurrency control beyond sequential loop

### Conditional requests

Not implemented.

### Fixture coverage (pre-v0.3)

- Synthetic only (`knowledge/fixtures/support_pages.py`)
- No live-captured Samsung HTML

### Live validation status

| Source | Status |
|--------|--------|
| India support | BLOCKED |
| UK support | BLOCKED |
| US support landing | LIVE_PARTIAL (HTML loads, zero model candidates) |
| US product owner pages (e.g. galaxy-s24-ultra) | **LIVE_VALIDATED** (see below) |

### Live reconnaissance findings (2026-08-02)

Polite GETs from this environment:

```
GET https://www.samsung.com/us/support/owners/product/galaxy-s24-ultra  → 200
  Extracted: SM-S928ULBEXAA

GET https://www.samsung.com/us/support/owners/product/galaxy-s24       → 200
  Extracted: SM-S921ULBAXAA

GET https://www.samsung.com/us/support/owners/product/galaxy-z-fold6   → 200
  Extracted: SM-F956UAKAXAA
```

Fixtures saved under `fixtures/samsung/live_samsung_us_*.html`.

India and UK regional hosts returned 403 (Akamai geo/bot edge). Treat as BLOCKED from this network; may work from other egress.

### Known false positives

- Broad regex can match firmware tokens if present in scripts
- No rejection of TV / appliance / monitor model families that use different prefixes (lower risk for SM-S/A/F)

### Known parser failures

- Landing pages are JS-rendered product search — static HTML yields 0 candidates
- Model numbers often appear only on individual product support pages
- Carrier suffixes (e.g. LBEXAA, LBAXAA) exceed previous `{4,10}` capture group in some cases

### Placeholder / fabricated behaviour

- None fabricated into DB
- Empty returns on 403 are honest failures
- Synthetic fixtures used only for offline demos (clearly labeled)

## Intended v0.3 behaviour (this phase)

1. Source registry with explicit validation_status per source
2. Strict model validator with category filtering
3. Discovery via known public product-support URL patterns + live-validated fixtures
4. Regional sightings model
5. Confidence ledger
6. Health tracking
7. Adaptive polling states
8. Alembic migrations

**Principle:** Prefer one LIVE_VALIDATED discovery path over five mocked ones.
