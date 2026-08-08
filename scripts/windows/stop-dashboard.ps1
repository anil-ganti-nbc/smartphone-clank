#Requires -Version 5.1
param([int]$TimeoutSec = 20)
$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "_common.ps1")
$Paths = Get-ClankPaths
$meta = Get-PidMeta -PidFile $Paths.DashboardPid
if (-not $meta) { Write-Host "Dashboard not running."; exit 0 }
$pidVal = [int]$meta.pid
try {
    Stop-Process -Id $pidVal -Force -ErrorAction Stop
} catch {}
Remove-Item $Paths.DashboardPid -Force -ErrorAction SilentlyContinue
Write-ClankLog -Paths $Paths -Name "dashboard" -Message "stopped"
Write-Host "Dashboard stopped."
