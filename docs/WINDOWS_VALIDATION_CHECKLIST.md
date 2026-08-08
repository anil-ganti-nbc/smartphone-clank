# Windows Live Validation Checklist

Operator steps after install on a real Windows machine.

| # | Step | Expected |
|---|------|----------|
| 1 | `install.ps1` | Summary printed; tasks registered or warning if policy blocks |
| 2 | Task Scheduler | Tasks named `SmartphoneIntelClank-*` present |
| 3 | `start-runtime.ps1` | PID file under `runtime\pids\runtime.pid` |
| 4 | `start-dashboard.ps1` | http://127.0.0.1:8200/ opens |
| 5 | `status.ps1 -Ports` | Port 8200 owned by python / Clank |
| 6 | `python main.py run --once` | Metrics row in DB / log |
| 7 | Kill runtime process | Health task or manual `start-runtime` recovers |
| 8 | Reboot | Runtime at startup; dashboard at logon |
| 9 | `backup-database.ps1` | `runtime\backups\clank_*.db` integrity ok |
| 10 | Daily report script | File under `runtime\reports\` |
| 11 | `uninstall.ps1` | Tasks removed; DB retained |

Mark each step pass/fail. CI cannot fully exercise Task Scheduler: **WINDOWS_LIVE_VALIDATION_REQUIRED**.
