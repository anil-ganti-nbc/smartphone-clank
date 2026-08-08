# Windows Readiness Audit — v0.3.5

| Finding | Severity | Status |
|---------|----------|--------|
| Hardcoded C: or username | High | **None** — paths from repo root |
| Dashboard default port | — | **8200** |
| Secrets in scripts | High | Env load skips printing; diagnostics sanitize |
| Duplicate tasks | Medium | Install unregisters then re-registers same names |
| Uninstall wildcards | High | Only `SmartphoneIntelClank-*` task names |
| Stale PID | Medium | Cleared if process not alive / not matching |
| SQLite backup | Medium | Python `Connection.backup()` API |
| Restart loops | Medium | Task restart count 5 / 2 min; health-check limited |
| External bind | High | Default 127.0.0.1; warning otherwise |
| Non-live sources enabled | High | Install rejects unless `-AllowNonLiveSources` |
| Metrics on every run | High | **Wired** in `pipeline.run_collector` |
| Snapshot growth | Medium | **Retention** `max_per_url` (default 20) |
| Task Scheduler live test | — | **WINDOWS_LIVE_VALIDATION_REQUIRED** |

## Critical fixes applied pre-packaging

1. MetricsRecorder.finish on every collector completion (success and failure).
2. Snapshot retention prune.
3. Skeleton collectors remain disabled and unregistered.
4. Installer source-policy gate for non-live validation statuses.
