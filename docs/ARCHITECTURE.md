# Architecture

Clank is a **single-process Python application** with SQLite (Postgres-compatible models).

## Data flow

1. **Collectors** fetch public pages/sitemaps; emit `Discovery` objects.
2. **Knowledge** enriches with deterministic YAML rules (no LLM).
3. **Entity resolution** maps discoveries to one device record; attaches evidence.
4. **ConfidenceService** records ledger entries; device.confidence is a projection.
5. **Alerts** — newsroom Discord vs maintenance Discord (separate).
6. **Observability** — immutable run metrics, health scores, daily report.
7. **Dashboard** — FastAPI + Jinja2, localhost, primarily read-only.

## Design rules

- Collectors stay dumb.
- Never invent model numbers.
- Prefer null over guess.
- Prefer deleting stubs over shipping empty “coverage.”
