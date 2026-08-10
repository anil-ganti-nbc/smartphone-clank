#Requires -Version 5.1
param([switch]$Foreground)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")
$Paths = Get-ClankPaths
Import-ClankEnv -Paths $Paths
$port = Get-DashboardPort
$hostAddr = if ($env:CLANK_DASHBOARD_HOST) { $env:CLANK_DASHBOARD_HOST } else { "127.0.0.1" }

$venvPy = $Paths.VenvPython
if (-not (Test-Path $venvPy)) { throw "Missing venv: $venvPy" }

$env:PYTHONPATH = $Paths.Root
$env:PYTHONUNBUFFERED = "1"
Set-Location $Paths.Root

if ($Foreground) {
    Write-Host "Starting dashboard on http://${hostAddr}:$port/ (foreground)..."
    & $venvPy -u main.py dashboard --host $hostAddr --port $port
    exit $LASTEXITCODE
}

# Same fix as start-runtime.ps1 (2026-08-10, production/development isolation
# phase): detached start with a recorded PID, so health-check.ps1's
# Test-ClankProcess check can actually find this process on a later cycle,
# and so health-check.ps1 itself does not block forever waiting on a
# synchronous uvicorn server that never returns.
if (Test-ClankProcess -PidFile $Paths.DashboardPid -ExpectedKind "dashboard") {
    $existing = Get-PidMeta -PidFile $Paths.DashboardPid
    Write-Host "Dashboard already running (PID $($existing.pid)) - not starting a duplicate."
    exit 0
}

$stdOutLog = Join-Path $Paths.LogDir "dashboard.out.log"
$stdErrLog = Join-Path $Paths.LogDir "dashboard.err.log"
$proc = Start-Process -FilePath $venvPy `
    -ArgumentList "-u", "main.py", "dashboard", "--host", $hostAddr, "--port", $port `
    -WorkingDirectory $Paths.Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdOutLog `
    -RedirectStandardError $stdErrLog `
    -PassThru

Save-PidMeta -PidFile $Paths.DashboardPid -ProcessId $proc.Id -Kind "dashboard"
Write-Host "Started dashboard, PID $($proc.Id)."
exit 0
