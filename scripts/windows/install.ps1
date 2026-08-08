#Requires -Version 5.1
<#
.SYNOPSIS
  Install Smartphone Intel Clank Windows unattended runtime.
#>
param(
    [switch]$Force,
    [switch]$SkipDependencyInstall,
    [int]$DashboardPort = 8200,
    [switch]$ForcePort,
    [switch]$AllowNonLiveSources,
    [int]$ValidationDays = 7
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$Paths = Get-ClankPaths
Import-ClankEnv -Paths $Paths
$env:CLANK_DASHBOARD_PORT = "$DashboardPort"

Write-Host "=== Smartphone Intel Clank Windows Install ===" -ForegroundColor Cyan
Write-Host "Root: $($Paths.Root)"

# Windows version
$os = Get-CimInstance Win32_OperatingSystem
Write-Host "OS: $($os.Caption) $($os.Version)"

# Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) { throw "Python not found on PATH. Install Python 3.10+ and re-run." }

$verOut = & $py.Source --version 2>&1
Write-Host "Python: $verOut"
if ($verOut -notmatch "Python 3\.(1[0-9]|[2-9][0-9])") {
    Write-Warning "Recommended Python 3.10+. Found: $verOut"
}

# Venv
$venvPy = $Paths.VenvPython
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating .venv..."
    & $py.Source -m venv (Join-Path $Paths.Root ".venv")
}
if (-not (Test-Path $venvPy)) { throw "Failed to create virtualenv at $($Paths.VenvPython)" }

if (-not $SkipDependencyInstall) {
    Write-Host "Installing dependencies..."
    & $venvPy -m pip install --upgrade pip
    $req = Join-Path $Paths.Root "requirements.txt"
    if (Test-Path $req) {
        & $venvPy -m pip install -r $req
    }
    & $venvPy -m pip install fastapi uvicorn jinja2 "apscheduler>=3.10" alembic
}

# Port check
Write-Host "Checking port $DashboardPort..."
if (-not (Test-PortFree -Port $DashboardPort)) {
    $owners = Get-PortOwners -Port $DashboardPort
    foreach ($o in $owners) {
        Write-Host "  LISTEN $($o.LocalAddress):$($o.Port) PID=$($o.Pid) $($o.ProcessName) $($o.Path)" -ForegroundColor Yellow
    }
    if (-not $ForcePort) {
        throw "Port $DashboardPort is in use. Free the port or pass -ForcePort (not recommended)."
    }
    Write-Warning "ForcePort: continuing despite port conflict."
}

# Source policy
Assert-LiveSourcesOrOverride -Paths $Paths -AllowNonLiveSources:$AllowNonLiveSources

# Database backup before migrate
$dbPath = Join-Path $Paths.DataDir "clank.db"
if (Test-Path $dbPath) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $bak = Join-Path $Paths.BackupDir "pre_install_$stamp.db"
    Copy-Item $dbPath $bak -Force
    Write-Host "Pre-migrate backup: $bak"
}

# Migrations (best-effort)
Write-Host "Running migrations..."
Push-Location $Paths.Root
try {
    & $venvPy -c "from database.migrations_ordered import upgrade; print(upgrade('sqlite:///./data/clank.db'))"
    if (Test-Path (Join-Path $Paths.Root "alembic.ini")) {
        & $venvPy -m alembic upgrade head 2>&1 | Out-Host
    }
} catch {
    Write-Warning "Migration note: $_"
} finally {
    Pop-Location
}

# Integrity
Write-Host "Database integrity..."
$integrityScript = @'
import sqlite3, os
p = "data/clank.db"
if os.path.exists(p):
    c = sqlite3.connect(p)
    print(c.execute("PRAGMA integrity_check").fetchone()[0])
    c.close()
else:
    print("no_db_yet")
'@
& $venvPy -c $integrityScript

# Validation marker
$valFile = Join-Path $Paths.ReportDir "validation_start.json"
$valObj = [ordered]@{
    started_utc = (Get-Date).ToUniversalTime().ToString("o")
    validation_days = $ValidationDays
    expected_end_utc = (Get-Date).ToUniversalTime().AddDays($ValidationDays).ToString("o")
    version = "0.3.5"
    dashboard_port = $DashboardPort
}
$valObj | ConvertTo-Json | Set-Content $valFile -Encoding UTF8

# Scheduled tasks — Task Scheduler must supervise Python, not a short-lived wrapper
$psExe = (Get-Command powershell.exe).Source
$repoRoot = $Paths.Root
$venvPy = $Paths.VenvPython
if (-not (Test-Path $venvPy)) { throw "Critical: venv python missing after install: $venvPy" }

function Register-ClankPythonTask {
    param(
        [string]$TaskName,
        [string]$Arguments,
        $Trigger,
        [string]$Description = "Smartphone Intel Clank"
    )
    $action = New-ScheduledTaskAction -Execute $venvPy -Argument $Arguments -WorkingDirectory $repoRoot
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 5 `
        -RestartInterval (New-TimeSpan -Minutes 2) `
        -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
        -MultipleInstances IgnoreNew
    try {
        $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($existing) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $Trigger -Settings $settings -Description $Description -Force | Out-Null
        # Read-back validation
        $rb = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        $act = ($rb.Actions | Select-Object -First 1)
        if (-not $act.Execute -or ($act.Execute -notlike "*python*")) {
            throw "Task $TaskName read-back failed: Execute=$($act.Execute)"
        }
        Write-Host "Registered+verified task: $TaskName -> $($act.Execute) $($act.Arguments)"
    } catch {
        Write-Error "CRITICAL task registration failed: $TaskName - $_"
        exit 2
    }
}

function Register-ClankScriptTask {
    param(
        [string]$TaskName,
        [string]$ScriptName,
        $Trigger
    )
    $scriptPath = Join-Path $repoRoot "scripts\windows\$ScriptName"
    $argLine = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
    $action = New-ScheduledTaskAction -Execute $psExe -Argument $argLine -WorkingDirectory $repoRoot
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
    try {
        $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($existing) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $Trigger -Settings $settings -Description "Smartphone Intel Clank helper" -Force | Out-Null
        Write-Host "Registered helper task: $TaskName"
    } catch {
        Write-Warning "Helper task registration failed (non-critical): $TaskName - $_"
    }
}

# CRITICAL: Runtime + Dashboard point at Python directly
Register-ClankPythonTask -TaskName "SmartphoneIntelClank-Runtime" -Arguments "-u -m runtime.daemon" -Trigger (New-ScheduledTaskTrigger -AtStartup)
Register-ClankPythonTask -TaskName "SmartphoneIntelClank-Dashboard" -Arguments "-u main.py dashboard --host 127.0.0.1 --port $DashboardPort" -Trigger (New-ScheduledTaskTrigger -AtLogOn)

# Helper scripts may use PowerShell
$healthTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration ([TimeSpan]::FromDays(3650))
Register-ClankScriptTask -TaskName "SmartphoneIntelClank-HealthCheck" -ScriptName "health-check.ps1" -Trigger $healthTrigger
Register-ClankScriptTask -TaskName "SmartphoneIntelClank-DailyBackup" -ScriptName "backup-database.ps1" -Trigger (New-ScheduledTaskTrigger -Daily -At 3am)
Register-ClankScriptTask -TaskName "SmartphoneIntelClank-DailyReport" -ScriptName "generate-daily-report.ps1" -Trigger (New-ScheduledTaskTrigger -Daily -At 6am)
Register-ClankScriptTask -TaskName "SmartphoneIntelClank-WeeklyReport" -ScriptName "generate-weekly-report.ps1" -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 7am)

Write-ClankLog -Paths $Paths -Name "task-install" -Message "install complete port=$DashboardPort validation_days=$ValidationDays"

Write-Host ""
Write-Host "Installation summary" -ForegroundColor Green
Write-Host "  Root:       $($Paths.Root)"
Write-Host "  Python:     $venvPy"
Write-Host "  Dashboard:  http://127.0.0.1:$DashboardPort/"
Write-Host "  Validation: $ValidationDays days (marker: $valFile)"
Write-Host "  Next:"
Write-Host "    .\scripts\windows\status.ps1"
Write-Host "    .\scripts\windows\start-runtime.ps1"
Write-Host "    .\scripts\windows\start-dashboard.ps1"
