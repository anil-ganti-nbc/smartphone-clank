# v0.3.8 — Daily Report Aggregation Audit

## How `report daily` worked (pre-repair)

1. Select all `collector_run_metrics` with `started_at` in **UTC** calendar day.
2. `collectors_run` = distinct collector names in that set.
3. `new_devices` = sum of `new_devices` column (not net DB delta).
4. `meaningful_discoveries` = sum of `meaningful_changes` (**always 0** — never set by pipeline).
5. `alerts_sent` = sum of metrics field (**always 0** — never set by pipeline).
6. Health per collector via `health_score()` starting at 100.
7. DB counts = current totals (all time), not day delta.

## Failure modes observed

| Symptom | Cause |
|---------|--------|
| 9 collectors “healthy” | Config enabled them; report listed any runner that day |
| health=100 for junk/empty | Score only penalizes hard failures |
| New devices 152, meaningful 0 | Counter unwired + real Samsung expansion |
| Alerts 0 | Metrics field never incremented |

## Post-repair behavior

- `daily_report(..., enabled_collectors=set, production_scope_only=True)`
- Headline metrics use **enabled** collectors only.
- Out-of-scope runs reported separately.
- Timezone labeled **UTC**.
- Pipeline sets `meaningful_changes = new_c + upd_c` (interim definition).

## Still limited

- No `run_mode` column (demo vs production).
- Alert count still may lag Discord unless further wiring of `alerts_sent`.
- UTC day boundary ≠ IST local day.
