# Windows Troubleshooting

| Problem | Action |
|---------|--------|
| Port 8200 in use | `status.ps1 -Ports`; stop conflicting app or free port |
| Task registration failed | Run elevated PowerShell; or start scripts manually |
| Runtime not restarting | Check Task Scheduler history; `health-check.ps1 -Verbose` |
| Dashboard unreachable | Confirm bind 127.0.0.1:8200; PID file; firewall not required for loopback |
| DB locked | Stop runtime; backup; restart |
| Install rejects sources | Expected for BLOCKED sources; fix status or `-AllowNonLiveSources` |
| Secrets in logs | Should never appear; if seen, rotate webhooks and file issue |

Live Task Scheduler behaviour: **WINDOWS_LIVE_VALIDATION_REQUIRED** on non-Windows CI hosts.
