# Windows Operations

## Daily

- `.\scripts\windows\status.ps1`
- `.\scripts\windows\health-check.ps1`
- Reports: `runtime\reports\daily-YYYY-MM-DD.md`

## Control

| Action | Script |
|--------|--------|
| Start runtime | `start-runtime.ps1` |
| Stop runtime | `stop-runtime.ps1` |
| Restart runtime | `restart-runtime.ps1` |
| Start dashboard | `start-dashboard.ps1` |
| Stop dashboard | `stop-dashboard.ps1` |
| Backup DB | `backup-database.ps1` |
| Diagnostics ZIP | `collect-diagnostics.ps1` |

## Trusting a quiet day

Only if collector runs were **recorded** (`collector_run_metrics`), success rate is healthy, and health-check is green. Zero runs ≠ quiet success.

## Logs

`runtime\logs\` — runtime, dashboard, health-check, backup, reports, errors (rotated via app config where applicable).

## Uninstall automation (keep data)

```powershell
.\scripts\windows\uninstall.ps1
```
