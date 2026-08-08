# Reliability Review — v0.3.4

## Strengths

- Content-hash evidence dedup.
- Ledger-based confidence (rebuildable).
- Adaptive polling state machine defined.
- Source health + regression detection in metrics.
- Honest LIVE_VALIDATED vs BLOCKED statuses.

## Gaps

| Gap | Risk | Notes |
|-----|------|-------|
| MetricsRecorder not wired into every collector finish path | Medium | Runs may not appear in /metrics until integrated |
| Scheduler lock recovery | Medium | Designed; long soak not proven in CI |
| Skeleton collectors previously enabled | High (mitigated) | Disabled in v0.3.4 |
| Timezone: `datetime.utcnow()` used widely | Low | Prefer timezone-aware UTC |
| Double alert on restart | Low | Depends on alert dedup by device+type |
| Conditional HTTP (ETag) incomplete on all paths | Low | Bandwidth only |

## Clock / restart

- Assume wall clock can jump; store absolute next_run timestamps.
- On restart, reload scheduler_jobs / discovered_urls next_run.

## “Nothing happened today”

Only trustworthy if runs_24h > 0 and health ≥ 90 with no REGRESSION notes (see operations.md).

## Verdict

Core discovery and confidence paths are **reliable enough for supervised production**. Unattended multi-week operation requires MetricsRecorder integration into live collectors and a scheduler soak test.
