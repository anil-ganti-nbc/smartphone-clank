#Requires -Version 5.1
param(
    [switch]$KeepData,
    [switch]$RemoveRuntimeFiles,
    [switch]$RemoveVirtualEnvironment
)
$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "_common.ps1")
$Paths = Get-ClankPaths

Write-Host "Stopping processes..."
& (Join-Path $PSScriptRoot "stop-runtime.ps1")
& (Join-Path $PSScriptRoot "stop-dashboard.ps1")

$removed = @()
Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -like "SmartphoneIntelClank-*" } | ForEach-Object {
    Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false
    $removed += "task:$($_.TaskName)"
}

Write-Host "Preserving database and backups by default."
if ($RemoveRuntimeFiles) {
    foreach ($d in @($Paths.LogDir, $Paths.PidDir, $Paths.DiagnosticsDir, $Paths.ReportDir)) {
        if (Test-Path $d) {
            Remove-Item $d -Recurse -Force -ErrorAction SilentlyContinue
            $removed += "dir:$d"
        }
    }
}
if ($RemoveVirtualEnvironment) {
    $venv = Join-Path $Paths.Root ".venv"
    if (Test-Path $venv) {
        Remove-Item $venv -Recurse -Force
        $removed += "venv"
    }
}

Write-Host "Removed:"
$removed | ForEach-Object { Write-Host "  $_" }
Write-Host "Database and backups were NOT deleted."
Write-Host "Repository source was NOT deleted."
