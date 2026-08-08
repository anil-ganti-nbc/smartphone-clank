#Requires -Version 5.1
param(
    [switch]$IncludeDatabaseCopy,
    [switch]$IncludeSnapshots
)
$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "_common.ps1")
$Paths = Get-ClankPaths
Import-ClankEnv -Paths $Paths
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stage = Join-Path $Paths.DiagnosticsDir "bundle_$stamp"
New-Item -ItemType Directory -Path $stage -Force | Out-Null

# Sanitized config (strip webhook-like lines)
if (Test-Path $Paths.EnvFile) {
    Get-Content $Paths.EnvFile | Where-Object { $_ -notmatch "WEBHOOK|TOKEN|SECRET|PASSWORD" } |
        Set-Content (Join-Path $stage "env.sanitized") -Encoding UTF8
}
Copy-Item $Paths.ConfigYaml (Join-Path $stage "config.yaml") -ErrorAction SilentlyContinue
Copy-Item $Paths.SamsungYaml (Join-Path $stage "samsung_sources.yaml") -ErrorAction SilentlyContinue
Copy-Item $Paths.RuntimeYaml (Join-Path $stage "windows_runtime.yaml") -ErrorAction SilentlyContinue

# Versions
$venvPy = $Paths.VenvPython
if (Test-Path $venvPy) {
    & $venvPy --version | Out-File (Join-Path $stage "python_version.txt")
    & $venvPy -m pip freeze 2>$null | Out-File (Join-Path $stage "pip_freeze.txt")
}
[System.Environment]::OSVersion | Out-File (Join-Path $stage "windows_version.txt")

# Tasks
Get-ScheduledTask | Where-Object { $_.TaskName -like "SmartphoneIntelClank*" } |
    Select-Object TaskName, State | ConvertTo-Json | Set-Content (Join-Path $stage "scheduled_tasks.json")

# Logs (recent tails)
$logStage = Join-Path $stage "logs"
New-Item -ItemType Directory $logStage -Force | Out-Null
Get-ChildItem $Paths.LogDir -Filter "*.log" -ErrorAction SilentlyContinue | ForEach-Object {
    Get-Content $_.FullName -Tail 200 -ErrorAction SilentlyContinue |
        Set-Content (Join-Path $logStage $_.Name) -Encoding UTF8
}

# Schema / integrity
$dbPath = Join-Path $Paths.DataDir "clank.db"
if ((Test-Path $dbPath) -and (Test-Path $venvPy)) {
    & $venvPy -c "import sqlite3; c=sqlite3.connect(r'$dbPath'); print(c.execute('PRAGMA integrity_check').fetchone()[0]); print('tables', [r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()])" |
        Out-File (Join-Path $stage "db_integrity.txt")
    if ($IncludeDatabaseCopy) {
        Copy-Item $dbPath (Join-Path $stage "clank.db.copy")
    }
}

# Ports
Get-PortOwners -Port (Get-DashboardPort) | ConvertTo-Json | Set-Content (Join-Path $stage "ports.json")

$zip = Join-Path $Paths.DiagnosticsDir "diagnostics_$stamp.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force
Write-Host "Diagnostic bundle: $zip"
Write-Host "Includes DB copy: $IncludeDatabaseCopy  snapshots: $IncludeSnapshots (not packed by default)"
