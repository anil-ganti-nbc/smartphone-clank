# Smartphone Intel Clank — Progress Report v0.3.7

**Date:** 2026-08-06  
**Release:** v0.3.7 — Samsung Coverage Completion and Metrics Integrity  
**Author context:** Unattended Windows soak (Phase A) observed; Phase B instrumentation shipped.

---

## 1. Executive summary

v0.3.7 closes the two largest remaining Samsung operational gaps after a successful ~3.5-day unattended soak:

1. **Catalog traversal** — the collector no longer re-fetches only the first 15 sitemap product URLs every run.
2. **Metrics integrity** — HTTP/page counters and re-sight semantics reflect real network activity and dossier freshness without inventing evidence or confidence.

**Google and other OEMs remain intentionally disabled.** This release does not expand manufacturer scope.

---

## 2. Production database state before this release (observed)

Source: operator-uploaded `clank.db` from the Windows soak machine (inspected 2026-08-06).

| Metric | Value |
|--------|--------|
| Devices | 15 |
| Manufacturer mix | 100% Samsung |
| Junk / marketing-copy entities | 0 |
| Evidence rows | 15 |
| Successful collector runs | 51 |
| Active collector | `samsung_us_support_sitemap` only |
| First run | 15 new devices |
| Later runs | 0 new, 0 updated (dedup working) |
| Median run interval | ~45 minutes |
| Longest gap | ~10.7 hours (then resumed) |
| Span | 2026-08-02 → 2026-08-05 |

**Models present (all valid `SM-*`):**  
SM-A015, SM-A025, SM-A037U, SM-A102U, SM-A115, SM-A125U, SM-A135U, SM-A136U, SM-A146U, SM-A156U, SM-A166U, SM-A205U, SM-A215U, SM-A236U, SM-A256U

**Interpretation:** Runtime, scheduler, deduplication, and Samsung-only policy were healthy. Coverage was incomplete because of a fixed first-batch fetch budget, not because discovery was broken.

---

## 3. Confirmed limitations addressed in v0.3.7

### Limitation A — Fixed first-batch fetching
- Sitemap exposes ~126 phone product URLs.
- `max_product_fetches: 15` plus `urls[:max_f]` always started at index 0.
- Result: clean DB dominated by early Galaxy A entries; S/Z/F series never reached.

### Limitation B — No persistent catalog traversal
- No cursor / per-URL last-checked state across restarts.
- Reboots and process restarts repeated the same prefix.

### Limitation C — Re-sightings did not refresh dossiers
- Metrics showed `candidates_found=15` on repeat runs.
- `device.last_seen` and related freshness fields did not reliably move.
- Risk of looking “stale” while the collector was actually healthy.

### Limitation D — Incomplete HTTP metrics
- `pages_requested`, `pages_fetched`, `bytes_downloaded` often 0 while real candidates existed.
- Candidate count was more trustworthy than page metrics until this release.

---

## 4. What v0.3.7 implemented

### 4.1 Persistent URL ledger and traversal state

**New tables (additive; existing data preserved):**

- `sitemap_product_urls` — per-URL attempt ledger  
  Fields include: normalized URL, slug/series, first/last sitemap sighting, last attempt/success, HTTP status, attempt/success/failure counts, consecutive failures, backoff (`next_eligible_fetch_at`), associated device, last model extracted.

- `sitemap_traversal_state` — cycle-level state  
  Fields include: sitemap hash, total eligible URLs, cursor, cycle counters, strategy, last completed cycle timestamp.

**Module:** `collectors/samsung/traversal.py`

### 4.2 Selection strategy

**Strategy:** `oldest_checked_first` (documented and tested)

Priority order:

1. Never attempted (ordered by `first_discovered_at`)
2. Oldest successful check past `min_refetch_hours` (default 12)
3. Skip URLs still under backoff (`next_eligible_fetch_at > now`)

**Per-run budget:** default raised **15 → 60** (configurable).  
Sequential fetches with existing polite delay; no burst concurrency.

### 4.3 Attempt results

Every selected product URL records one of:

- `FETCH_SUCCESS_MODEL_FOUND`
- `FETCH_SUCCESS_NO_MODEL`
- `FETCH_SUCCESS_IRRELEVANT`
- `FETCH_HTTP_ERROR`
- `FETCH_BLOCKED`
- (related parse/skip variants as applicable)

Failed URLs enter scaled backoff (status-aware: 429 / 403 / 404 / 5xx).

### 4.4 Re-sighting semantics

On known model + same source/URL with no content change:

| Action | Allowed? |
|--------|----------|
| Update `device.last_seen` | Yes |
| Update evidence `last_seen` | Yes (existing row) |
| New evidence row | No |
| Confidence ledger entry | No |
| Newsroom alert | No |
| Meaningful timeline event | No |

Pipeline now tracks **`resighted`** separately from **`new`** and **`updated`**.

### 4.5 HTTP / page metrics

`SamsungSitemapDiscovery._fetch` instruments real httpx activity:

- `pages_requested`
- `pages_fetched`
- `bytes_downloaded`
- `http_failures`
- `timeouts`
- `redirects`
- status code distribution

Collector exposes `_last_http_metrics` to the pipeline for `MetricsRecorder`.

**Historical runs** are not backfilled as zero (that would falsify “no requests”). Pre-v0.3.7 rows remain legacy/uninstrumented.

### 4.6 Coverage CLI

```bash
python main.py samsung coverage
python main.py samsung coverage --json
python main.py samsung verify-upgrade
```

Coverage report includes: eligible URLs, attempted, successful, models found, never attempted, backoff, cycle progress %, cycles completed.

### 4.7 Config defaults

```yaml
samsung_us_support_sitemap:
  enabled: true
  max_product_fetches: 60
  min_refetch_hours: 12
  failed_retry_minutes: 180
  traversal_strategy: oldest_checked_first
```

---

## 5. Files touched (v0.3.7)

| Path | Role |
|------|------|
| `database/models.py` | `SitemapProductUrl`, `SitemapTraversalState` |
| `collectors/samsung/traversal.py` | **New** — sync, select, record, coverage |
| `collectors/samsung/sitemap_discovery.py` | HTTP metrics, product fetch split |
| `collectors/samsung/sitemap_collector.py` | DB-backed traversal integration |
| `collectors/__init__.py` | Budget + refetch kwargs |
| `entity_resolution/resolver.py` | Always refresh `last_seen` on resolve |
| `pipeline.py` | Resight counts + HTTP metrics wiring |
| `main.py` | `samsung coverage`, `samsung verify-upgrade` |
| `config/config.yaml` | Budget 60 + traversal settings |
| `tests/test_v037_traversal.py` | **New** unit tests |
| `demo/samsung_catalog_traversal_demo.py` | Offline 126-URL multi-run demo |
| `docs/SAMSUNG_CATALOG_TRAVERSAL_AUDIT.md` | Why first-15 happened |
| `docs/V037_SAMSUNG_COVERAGE_AUDIT.md` | Hostile audit notes |
| `docs/PROGRESS_v0.3.7.md` | This document |

---

## 6. Verification performed in this environment

| Check | Result |
|-------|--------|
| `test_v037_traversal.py` (advance batch, backoff, resight, coverage, HTTP metrics) | PASS |
| `demo/samsung_catalog_traversal_demo.py` (126 URLs, 3 runs → 100% attempted) | PASS |
| Offline: Run1 60 → Run2 120 → Run3 126; restart does not reset to first batch | PASS |

**Not executed here (requires operator Windows machine):**

- Live full-cycle against production `clank.db`
- Task Scheduler multi-day Phase B soak
- Dashboard coverage widget (CLI is primary surface)

---

## 7. Soak period classification guidance

Do **not** pretend the entire week used identical runtime behavior.

| Phase | Behavior |
|-------|----------|
| **Phase A** (≈ Aug 2–5) | Fixed 15-URL prefix; limited metrics |
| **Phase B** (from v0.3.7 upgrade) | Persistent traversal budget 60; real HTTP metrics; last_seen refresh |

Suggested soak labels after more Phase B data:

- **VALID_WITH_WARNINGS** — if Phase A gap + mid-soak instrumentation change, but Phase B advances coverage and metrics reconcile
- **VALID** — only after eligible catalog URLs are attempted (or a full cycle completes) with stable metrics and no junk growth
- **INVALID** — traversal cursor stuck, metrics missing, or junk pollution returns

---

## 8. Upgrade procedure (preserve production DB)

```powershell
# Stop runtime (Ctrl+C or stop scheduled task)
# Extract v0.3.7 over project; do NOT delete data\clank.db

cd C:\Users\anil\Desktop\smartphone-clank
$env:PYTHONPATH = (Get-Location).Path

.\.venv\Scripts\python.exe -c "from database.session import init_db,get_engine; from database.models import SitemapProductUrl,SitemapTraversalState; from config.settings import load_settings; s=load_settings('config/config.yaml'); init_db(s.database_url); e=get_engine(s.database_url); SitemapProductUrl.__table__.create(bind=e,checkfirst=True); SitemapTraversalState.__table__.create(bind=e,checkfirst=True); print('tables ok')"

.\.venv\Scripts\python.exe -u main.py samsung verify-upgrade
.\.venv\Scripts\python.exe -u main.py run --once
.\.venv\Scripts\python.exe -u main.py samsung coverage
```

Expect after 2–3 runs: coverage progress well above the original 15 URLs; `pages_requested` / `pages_fetched` non-zero; `resighted` on already-known models.

---

## 9. Explicit non-goals (this release)

- No Google / OnePlus / Nothing / Xiaomi collectors enabled
- No AI / LLM enrichment
- No new OEM discovery sources
- No dashboard redesign (coverage is CLI-first)
- No wipe or reseed of the 15 clean Samsung devices

---

## 10. Prior major revisions (index)

| Version | Theme | Key outcome |
|---------|--------|-------------|
| v0.1 | Core pipeline | Collectors → normalize → resolve → SQLite → Discord |
| v0.2 | Intelligence layer | Knowledge, aliases, timeline, confidence |
| v0.2.1 | Support-page diffing | Multi-hash change detection |
| v0.3 | Production Samsung | Live validation honesty, source registry |
| v0.3.1 | Real discovery | US support sitemap as discovery path |
| v0.3.2 | Integrity + console | Confidence service enforcement, newsroom UI |
| v0.3.3 | Observability | `collector_run_metrics`, health, reports |
| v0.3.4 | Hostile audit | Delete dead code, production readiness docs |
| v0.3.5 | Windows unattended | Task Scheduler packaging |
| v0.3.6 | Runtime repair | Sitemap registered in `main.py run`; Python supervised by Task Scheduler |
| **v0.3.7** | **Samsung coverage** | **Full-catalog traversal + metrics integrity** |

Supporting audits live under `docs/` (`RUNTIME_COLLECTOR_AUDIT.md`, `V036_RUNTIME_REPAIR_AUDIT.md`, `SAMSUNG_CATALOG_TRAVERSAL_AUDIT.md`, `V037_SAMSUNG_COVERAGE_AUDIT.md`, etc.).

---

## 11. Recommended next steps (after Phase B proves out)

1. Run 2–3 live collection cycles; confirm `samsung coverage` progress and non-zero HTTP metrics.
2. Continue unattended until a full catalog attempt (or explicit soak end).
3. Only then harden **one** non-Samsung parser (Google first) with strict model-ID rules.
4. Keep other OEM flags false until each parser passes a dry-run without marketing-text pollution.

---

## 12. Residual risks

| Risk | Severity | Notes |
|------|----------|-------|
| Live cycle not yet proven on operator DB | Medium | Offline 126-URL demo passed; production must confirm |
| Cycle-complete counter edge cases | Low | Driven by `never_attempted == 0`; watch first full cycle |
| Metrics notes JSON for status distribution | Low | Structured field preferred later |
| Dashboard coverage section | Low | CLI sufficient for operators |
| Machine access window (~2 weeks from earlier note) | Operational | Export `data/clank.db` + logs off-box regularly |

---

*Document generated for release v0.3.7. Update or supersede with `PROGRESS_v0.3.x.md` after each major revision.*
