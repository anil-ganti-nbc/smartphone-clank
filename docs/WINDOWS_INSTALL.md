# Windows Install Guide — Clank v0.3.5

## Prerequisites

- Windows 10 or 11
- Python 3.10+ on PATH (`python --version`)
- PowerShell 5.1+ (Windows PowerShell or PowerShell 7)
- Ability to create scheduled tasks for the current user

## Install

```powershell
cd path\to\smartphone-clank
copy .env.example .env
# Edit .env — optional Discord webhooks; leave empty if unused

Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\install.ps1
```

Options:

```powershell
.\scripts\windows\install.ps1 -Force
.\scripts\windows\install.ps1 -SkipDependencyInstall
.\scripts\windows\install.ps1 -DashboardPort 8200
.\scripts\windows\install.ps1 -ForcePort          # only if you accept port conflict
.\scripts\windows\install.ps1 -AllowNonLiveSources  # reject BLOCKED/FIXTURE sources unless set
.\scripts\windows\install.ps1 -ValidationDays 7
```

## After install

```powershell
.\scripts\windows\start-runtime.ps1
.\scripts\windows\start-dashboard.ps1
.\scripts\windows\status.ps1
```

Dashboard: **http://127.0.0.1:8200/**

## Notes

- Installer is idempotent; re-run updates tasks.
- Port **8200** must be free unless `-ForcePort`.
- Enabled Samsung sources with `BLOCKED` / `FIXTURE_ONLY` status cause install failure unless `-AllowNonLiveSources`.
- Task Scheduler registration may require interactive elevation depending on policy — mark live validation if registration is blocked.
