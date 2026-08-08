#Requires -Version 5.1
param(
    [switch]$Json,
    [switch]$Ports,
    [switch]$Verbose
)
$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "_common.ps1")
$Paths = Get-ClankPaths
Import-ClankEnv -Paths $Paths
$port = Get-DashboardPort

$runtimeOk = Test-ClankProcess -PidFile $Paths.RuntimePid -ExpectedKind "runtime"
$dashOk = Test-ClankProcess -PidFile $Paths.DashboardPid -ExpectedKind "dashboard"
$rtMeta = Get-PidMeta -PidFile $Paths.RuntimePid
$dMeta = Get-PidMeta -PidFile $Paths.DashboardPid

$healthz = $null
try {
    $healthz = Invoke-RestMethod -Uri "http://127.0.0.1:$port/healthz" -TimeoutSec 3
} catch { $healthz = $null }

$dbPath = Join-Path $Paths.DataDir "clank.db"
$dbSize = if (Test-Path $dbPath) { (Get-Item $dbPath).Length } else { 0 }

$status = [ordered]@{
    product = "Smartphone Intel Clank"
    version = "0.3.5"
    runtime = @{
        running = $runtimeOk
        pid = if ($rtMeta) { $rtMeta.pid } else { $null }
        started = if ($rtMeta) { $rtMeta.started_utc } else { $null }
    }
    dashboard = @{
        running = $dashOk
        url = "http://127.0.0.1:$port/"
        health = if ($healthz) { $healthz.status } else { "unreachable" }
        pid = if ($dMeta) { $dMeta.pid } else { $null }
    }
    database = @{
        path = $dbPath
        size_bytes = $dbSize
    }
}

if ($Ports) {
    $status.port_owners = Get-PortOwners -Port $port
}

if ($Json) {
    $status | ConvertTo-Json -Depth 6
    exit 0
}

Write-Host "Smartphone Intel Clank" -ForegroundColor Cyan
Write-Host ""
Write-Host "Runtime:"
Write-Host "  $(if($runtimeOk){'Running'}else{'Stopped'})"
if ($rtMeta) { Write-Host "  PID: $($rtMeta.pid)"; Write-Host "  Started: $($rtMeta.started_utc)" }
Write-Host ""
Write-Host "Dashboard:"
Write-Host "  $(if($dashOk){'Running'}else{'Stopped'})"
Write-Host "  URL: http://127.0.0.1:$port/"
Write-Host "  Health: $(if($healthz){$healthz.status}else{'unreachable'})"
Write-Host ""
Write-Host "Database:"
Write-Host "  Size: $([math]::Round($dbSize/1MB, 2)) MB"
Write-Host "  Path: $dbPath"
if ($Ports) {
    Write-Host ""
    Write-Host "Port $port owners:"
    Get-PortOwners -Port $port | Format-Table -AutoSize
}
