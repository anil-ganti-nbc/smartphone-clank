# Performance Notes — v0.3.4

## Observed / estimated

| Issue | Impact | Status |
|-------|--------|--------|
| New `httpx.Client` per fetch in some collectors | Low at current poll rates | Acceptable |
| Regex compiled at class level in validators | Good | OK |
| Sitemap full parse every discovery run (~300KB XML) | Low | OK; conditional GET can be added later |
| N+1 evidence queries in pipeline | Medium if many devices | Mitigated by session-level flush; not batch-optimized |
| Dashboard loads all devices without pagination beyond limit 100 | Low for newsroom scale | OK |
| Snapshot content stored as TEXT | Growth risk | Monitor via metrics DB size |
| Metrics regression checks on every finish | Negligible | OK |

## Indexes present

- devices (model, manufacturer)
- evidence (device_id, source)
- aliases unique constraints
- collector_run_metrics (collector_name, started_at)

## Not worth optimizing yet

- Connection pooling beyond SQLite defaults
- Parallel collectors (rate-limit politeness is more important)
- Caching HTML beyond content-hash skip

## Guidance

Measure with `collector_run_metrics.duration_ms` before changing algorithm. Prefer fewer HTTP requests over micro-optimizing parsers.
