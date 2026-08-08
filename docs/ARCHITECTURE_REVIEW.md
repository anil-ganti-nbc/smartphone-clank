# Architecture Review — v0.3.4

## Pipeline (sound)

```
Collector (dumb) → Discovery → Knowledge enrichment → Entity resolution
  → Aliases / Timeline / Families → ConfidenceService (ledger) → Alerts
```

Separation of “what did I find?” from “what does it mean?” is correct and should be preserved.

## Coupling concerns

| Area | Issue | Recommendation |
|------|-------|----------------|
| `pipeline.py` | Orchestrates too many services inline | Acceptable for single-process tool; extract only if files > ~400 lines |
| `ConfidenceService` vs `ConfidenceLedger` vs `ConfidenceDecay` | Three modules; decay no longer mutates device.confidence | Keep; document that only Service/Ledger write confidence |
| Dashboard | Uses ORM models directly | Fine for local console; do not add a second API layer |
| Samsung | `discovery.py`, `sitemap_discovery.py`, `samsung_support.py` | Three entry points; document which is production discovery |

## Unnecessary abstractions

- `normalizers/` package with no modules — remove or fill.
- Half-finished certification collectors — worse than absence.

## Dependency direction

- Collectors must not import ConfidenceService (correct today).
- Dashboard must not contain scoring rules (correct).
- Observability must not change discovery outcomes (correct).

## OEM extension pain points

1. Model validation is Samsung-specific — new OEM needs a validator module.
2. Knowledge YAML is manufacturer-keyed — good.
3. Registry in `collectors/__init__.py` is a manual list — acceptable at this scale.

## Naming inconsistency

- `CollectorRun` (legacy) vs `CollectorRunRecord` (metrics) — rename when safe.
- `SourceType` enum vs free-string `source` columns — tolerate.

## Verdict

Architecture is **appropriate for a single-engineer SQLite tool**. Do not introduce microservices, queues, or multi-process complexity.
