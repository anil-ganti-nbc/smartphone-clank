# Samsung Live Validation Report — v0.3

**Access date:** 2026-08-02  
**User-Agent:** SmartphoneIntelClank/0.3 (research; respectful crawler)  
**Egress:** cloud sandbox (non-IN/UK geo)

## Summary

| Source ID | Region | HTTP | Parser | Fixture | Status | Safe default enable? |
|-----------|--------|------|--------|---------|--------|----------------------|
| samsung_us_owners_product | US | 200 | SM- extracted | yes | **LIVE_VALIDATED** | **yes** |
| samsung_us_support_landing | US | 200 | 0 candidates | landing only | LIVE_PARTIAL | yes (monitor only) |
| samsung_in_support | IN | 403 | n/a | no | **BLOCKED** | **no** |
| samsung_uk_support | GB | 403 | n/a | no | **BLOCKED** | **no** |
| samsung_de_support | DE | not tested | n/a | no | UNSUPPORTED | no |
| samsung_kr_support | KR | not tested | n/a | no | UNSUPPORTED | no |

## LIVE_VALIDATED details

### samsung_us_owners_product

- **Pattern:** `https://www.samsung.com/us/support/owners/product/{slug}`
- **Examples validated:**
  - `galaxy-s24-ultra` → `SM-S928ULBEXAA` (HTTP 200, 243KB)
  - `galaxy-s24` → `SM-S921ULBAXAA`
  - `galaxy-z-fold6` → `SM-F956UAKAXAA`
- **Fixtures:**
  - `fixtures/samsung/live_samsung_us_galaxy_s24_ultra.html`
  - `fixtures/samsung/live_samsung_us_galaxy_s24.html`
  - `fixtures/samsung/live_samsung_us_zfold6.html`
- **Limitations:** Requires known product slugs; not a full catalog crawl. Carrier suffixes present (LBEXAA etc.). Static HTML sufficient — no browser automation.

### samsung_us_support_landing

- URL: `https://www.samsung.com/us/support/`
- HTTP 200, ~267KB
- Product search is client-side JS; regex over static HTML yields **zero** SM- models
- Useful only as a health/canary check that the host responds

### BLOCKED sources

India and UK support hosts returned **HTTP 403** with Akamai edge headers from this egress.  
They are registered with `enabled: false` and `validation_status: BLOCKED`.  
Re-test from an appropriate region before enabling.

## Policy

- No CAPTCHA bypass, no proxy rotation, no logged-in sessions
- Kill switch available in `config/samsung_sources.yaml`
- Fixture fallback is logged as `parser_warnings` when live fetch fails for a validated seed path
