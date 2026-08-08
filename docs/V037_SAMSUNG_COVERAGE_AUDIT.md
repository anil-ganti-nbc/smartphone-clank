# v0.3.7 Samsung Coverage Hostile Audit

| Risk | Mitigation | Status |
|------|------------|--------|
| Always first 15 URLs | oldest_checked_first + persistent ledger | fixed |
| Cursor reset on restart | SQLite `sitemap_product_urls` / `sitemap_traversal_state` | fixed |
| Late sitemap starvation | never-attempted prioritized | fixed |
| Duplicate evidence on resight | same URL/source → last_seen only | fixed |
| Confidence inflation | apply only when evidence_added | fixed |
| Zeroed fake HTTP metrics | real counters from httpx path | fixed |
| Historical runs as zero | legacy rows unchanged; null means uninstrumented | preserved |
| Aggressive parallel fetch | sequential + min_delay | preserved |
| Full wipe of 15 devices | migrations additive only | required on upgrade |

## Residual

- Live full-cycle (126 URLs) requires multiple production runs — WINDOWS/LIVE validation
- Dashboard coverage widget not redesigned; CLI `samsung coverage` is primary
- `pages_fetched` includes sitemap + products
