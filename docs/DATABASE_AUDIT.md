# Database Audit — v0.3.4

## Systems

1. **Alembic** (`alembic/versions/0001–0004`) — primary, explicit SQL.
2. **Ordered runner** (`database/migrations_ordered.py`) — compatibility.
3. **create_all** — demos/tests only.

## Integrity risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Orphan evidence if device deleted without cascade | Medium | Soft-delete `active=False` preferred |
| Dual model modules (`models` + `models_v03`) | Medium | Import both carefully; merge later |
| Confidence projection drift | Medium | `confidence rebuild` / verify via service |
| Snapshot unbounded growth | Medium | Metrics track count; prune policy not implemented |
| Ledger unique (device, evidence, rule) | Good | Prevents double-count |
| SQLite FK enforcement | Depends on PRAGMA | Ensure `PRAGMA foreign_keys=ON` on connect |

## Growth expectations

- 1 row per collector run in `collector_run_metrics` (append-only).
- Evidence and ledger grow with real discoveries — expected.
- Do not delete historical runs or ledger rows.

## Backup

Before `db upgrade` / confidence rebuild --all: copy SQLite file.
Ordered runner and Alembic both assume operator-managed backup.

## Verdict

Schema is usable. Largest operational risk is **unbounded snapshots** and **split model definitions**, not missing uniqueness on core device identity.
