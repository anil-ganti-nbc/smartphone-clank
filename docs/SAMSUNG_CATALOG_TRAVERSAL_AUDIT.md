# Samsung Catalog Traversal Audit (v0.3.7)

## Why only 15 devices entered production DB

1. Sitemap exposes ~126 phone product URLs (`PHONE_PATH_RE` filter).
2. `max_product_fetches` was **15**.
3. Selection was `novel[:max_f] if novel else urls[:max_f]` — **always index 0**.
4. No persistent cursor or per-URL last-checked state.
5. Every run re-fetched the same first 15 product pages (Galaxy A01–A25 range).

## Post-v0.3.7 design

- Table `sitemap_product_urls`: per-URL attempt ledger
- Table `sitemap_traversal_state`: cycle progress
- Strategy: **oldest_checked_first** (never-attempted first)
- Default budget: **60** per run
- Min refetch: 12h; failed retry backoff: 180m × consecutive failures
- HTTP metrics recorded on real requests
- Re-sight: updates `device.last_seen`, no new evidence/confidence/alerts
