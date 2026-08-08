#Requires -Version 5.1
param(
    [switch]$NoRestart,
    [switch]$Json,
    [switch]$Verbose
)
# Exit: 0 healthy, 1 warning, 2 unhealthy, 3 script failure
$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "_common.ps1")
$Paths = Get-ClankPaths
Import-ClankEnv -Paths $Paths
$port = Get-DashboardPort
$level = 0
$issues = @()

function Add-Issue($msg, $sev) {
    $script:issues += $msg
    if ($sev -gt $script:level) { $script:level = $sev }
    if ($Verbose) { Write-Host "[$sev] $msg" }
}

if (-not (Test-Path $Paths.VenvPython)) { Add-Issue "venv missing" 2 }
if (-not (Test-Path $Paths.ConfigYaml)) { Add-Issue "config missing" 3 }

$runtimeOk = Test-ClankProcess -PidFile $Paths.RuntimePid -ExpectedKind "runtime"
$dashOk = Test-ClankProcess -PidFile $Paths.DashboardPid -ExpectedKind "dashboard"
if (-not $runtimeOk) { Add-Issue "runtime not running" 2 }
if (-not $dashOk) { Add-Issue "dashboard not running" 1 }

$hz = $null
try { $hz = Invoke-RestMethod -Uri "http://127.0.0.1:$port/healthz" -TimeoutSec 5 } catch { Add-Issue "healthz unreachable" 2 }
if ($hz -and $hz.database -ne "ok") { Add-Issue "database degraded" 2 }

$dbPath = Join-Path $Paths.DataDir "clank.db"
if (Test-Path $dbPath) {
    try {
        $venvPy = $Paths.VenvPython
        $ic = & $venvPy -c "import sqlite3; c=sqlite3.connect(r'$dbPath'); print(c.execute('PRAGMA integrity_check').fetchone()[0])"
        if ($ic -notmatch "ok") { Add-Issue "integrity_check=$ic" 2 }
    } catch { Add-Issue "integrity check failed" 2 }
}

# disk
try {
    $drive = (Get-Item $Paths.Root).PSDrive.Name
    $freeGB = [math]::Round((Get-PSDrive $drive).Free / 1GB, 2)
    if ($freeGB -lt 10) { Add-Issue "low disk ${freeGB}GB" 1 }
} catch {}

# optional restart once
if (-not $NoRestart) {
    if (-not $runtimeOk) {
        try { & (Join-Path $PSScriptRoot "start-runtime.ps1") } catch { Add-Issue "runtime restart failed" 2 }
    }
    if (-not $dashOk) {
        try { & (Join-Path $PSScriptRoot "start-dashboard.ps1") } catch { Add-Issue "dashboard restart failed" 1 }
    }
}

Write-ClankLog -Paths $Paths -Name "health-check" -Message "level=$level issues=$($issues -join '; ')"

if ($Json) {
    @{ level = $level; issues = $issues; port = $port } | ConvertTo-Json
}
exit $level
