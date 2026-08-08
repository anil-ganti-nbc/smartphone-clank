# v0.3.2 Hostile Audit

**Date:** 2026-08-02

## Critical / High findings

### 1. Direct confidence mutation in production (RESOLVED)

- **Severity:** Critical  
- **Files:** `entity_resolution/resolver.py`, `entity_resolution/decay.py`  
- **Reproduction:** grep `device.confidence +=` / `device.confidence =`  
- **Fix:** Removed; pipeline applies scores only via `ConfidenceService`  
- **Test:** `tests/test_confidence_write_enforcement.py`  
- **Residual:** Constructor `Device(confidence=0)` still allowed; ledger/service remain sole mutators of stored projection  

### 2. Alembic vs custom runner

- **Severity:** Medium  
- **Status:** Alembic project present (`alembic.ini`, `alembic/versions/0001–0004`) with **explicit SQL** (not `create_all` inside revisions)  
- **Residual:** Custom `database/migrations_ordered.py` still available as compatibility importer; primary path documented as Alembic  

### 3. Dashboard completeness

- **Severity:** Medium  
- **Status:** Core routes implemented (home, queue, dossier, health, export).  
- **Missing vs full brief:** review-queue mutations, safe merge UI, snapshot visual diff page, scheduler control UI, CSRF tokens on POST forms (no POST mutation routes yet — read-only console).  
- **Residual:** Analyst write actions intentionally deferred until confidence integrity is proven; read-only reduces risk  

### 4. Fixture leakage

- **Severity:** Low  
- **Status:** Demo DBs use separate paths / in-memory; dashboard does not auto-load synthetic fixtures into production URL  

### 5. Release-state overstatement

- **Severity:** High if present  
- **Status:** Dossier defaults to **unknown** with explicit label that novelty ≠ upcoming  

## Pass criteria mapping

| Criterion | Result |
|-----------|--------|
| No production confidence writes outside service | **Pass** (AST enforced) |
| Stored confidence reproducible from ledger | **Pass** when all writes use service |
| Alembic ordered revisions | **Pass** (explicit SQL) |
| Adaptive polling drives scheduler | **Partial** — logic + table; full APScheduler lock recovery demo not expanded in this pass |
| Maintenance incidents | **Partial** — module + dry-run; runtime emission on every failure path incomplete |
| Dashboard distinguishes facts/inferences | **Pass** on dossier labels |
| External content escaped | **Pass** (Jinja autoescape default + esc filter) |
| Demo cannot contaminate production views | **Pass** if separate DB URL used |

## Residual limitations (honest)

1. Review/merge/split UI not implemented in this slice — CLI + services remain the mutation path.  
2. Scheduler restart demo exists as design; full unattended runtime proof still needs a longer soak test.  
3. Alembic env uses sqlite URL from alembic.ini; adopt-alembic auto-stamp for arbitrary create_all DBs is not fully automatic.  
4. Dashboard is **read-first** newsroom — intentional integrity choice.
