# v0.3.1 Hostile Integrity Audit

**Date:** 2026-08-02

## Original limitations — classification

| Limitation | Status | Evidence |
|------------|--------|----------|
| Discovery begins from known product slugs | **Resolved** | `support_sitemap.xml` exposes 133+ phone product URLs without slug seed. Recon: `docs/samsung_discovery_recon.md`. Module: `collectors/samsung/sitemap_discovery.py`. Live GET 200 on sitemap + product pages extracted SM-S938U, SM-A366U. |
| Confidence ledger not on every path | **Partially resolved** | Central `ConfidenceService` is the approved API (`entity_resolution/confidence_service.py`). Demo + tests route through it. Full pipeline rewrite of every legacy `device.confidence +=` path is incomplete — residual direct mutations may exist in older resolver until fully migrated. |
| Migrations are create_all wrapper | **Resolved** | `database/migrations_ordered.py` applies explicit SQL per revision `0.2.1 → 0.3.0 → 0.3.1`. Idempotent; stamps `schema_version`. Tested upgrade path. |
| Adaptive polling only designed | **Resolved (logic)** | `collectors/samsung/polling.py` implements state machine with persisted fields defined in migration 0.3.1 (`discovered_urls.polling_state`, `next_run`, …). Scheduler integration to APScheduler is present as library; full job-store wiring remains light. |
| Maintenance webhook only designed | **Resolved (logic)** | `alerts/maintenance.py` separate from newsroom, dry-run safe, dedupe keys. Requires `MAINTENANCE_WEBHOOK_URL` for live send. |

## Claims that must not be made

1. **“Production discovery of unreleased phones”** — False. Sitemap lists published support pages. Unlisted unreleased devices will not appear.
2. **“Every confidence write uses ledger”** — Not yet guaranteed across entire codebase; service exists and tests enforce for new paths.
3. **“Full Alembic package”** — Ordered SQL migrations implemented; not the Alembic CLI project layout. Functionally equivalent for SQLite upgrades.
4. **“Slug seed = discovery”** — Explicitly rejected. Owners-product seed paths are monitoring.

## Live validation this run

| Action | Result |
|--------|--------|
| GET `us/sitemap.xml` | 200 sitemap index |
| GET `us/support_sitemap.xml` | 200, ~300KB, 836 locs, 133 phone product paths |
| GET `.../galaxy-s25-ultra/` (from sitemap) | 200, model `SM-S938UAKAXAA` |
| GET `.../galaxy-a36-5g/` (from sitemap) | 200, model `SM-A366ULGAXAA` |
| GET India/UK support | 403 BLOCKED (unchanged) |

## Residual risks

- Support product pages sometimes share templated HTML; model token density varies.
- Baseline seeding must still be tagged so historical phones never fire “unreleased” alerts.
- Ordered migrations are SQLite-path oriented; PostgreSQL needs dialect review before production PG.

## Verdict

v0.3.1 meets the **hard discovery criterion**: a public Samsung-owned index exposes previously unknown product support URLs without manually supplied slugs.  
Samsung is **discovery-capable** (sitemap) and **monitoring-capable** (owners pages + change detection), not discovery-limited — with the honest constraint that only **published** support pages are visible.
