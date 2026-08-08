# Confidence Mutation Audit — v0.3.2

**Date:** 2026-08-02

## Production mutations (must use ConfidenceService)

| File | Line (approx) | Pattern | Status |
|------|---------------|---------|--------|
| `entity_resolution/resolver.py` | was `device.confidence += weight` | illegal | **REMOVED** — evidence only; pipeline applies via service |
| `entity_resolution/decay.py` | was `device.confidence = total` | illegal | **REMOVED** — updates evidence contributions only |
| `entity_resolution/confidence_ledger.py` | `device.confidence = new_conf` | allowed | Ledger is the sole writer used by ConfidenceService |
| `entity_resolution/confidence_service.py` | repair/recalc projections | allowed | Central service |

## Non-device confidence (not ledger-scoped)

| File | Notes |
|------|-------|
| `knowledge/enrichment.py` | `EnrichedKnowledge.confidence` is string high/medium/low — not device score |
| `models/schemas.py` | Pydantic `DeviceRecord.add_evidence` in-memory helper — not ORM |
| `entity_resolution/aliases.py` | alias.confidence field — separate |
| `pipeline.py` | `knowledge_confidence` string field |
| `alerts/discord.py` | min_confidence threshold config |

## Tests / demos

Direct `Device(..., confidence=0)` constructors in tests/demos are allowed as fixture setup.
Assertions reading `.confidence` are allowed.

## Enforcement

- AST scan: `python main.py audit confidence-writes`
- Test: `tests/test_confidence_write_enforcement.py`
