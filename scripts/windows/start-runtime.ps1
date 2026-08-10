#Requires -Version 5.1
param(
    [switch]$Foreground,
    [switch]$Once
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")
$Paths = Get-ClankPaths
Import-ClankEnv -Paths $Paths

$venvPy = $Paths.VenvPython
if (-not (Test-Path $venvPy)) { throw "Missing venv python: $venvPy" }

$env:PYTHONPATH = $Paths.Root
$env:PYTHONUNBUFFERED = "1"
Set-Location $Paths.Root

if ($Once) {
    Write-Host "One-shot collection..."
    & $venvPy -u main.py run --once
    exit $LASTEXITCODE
}

if ($Foreground) {
    # Synchronous: stays alive for daemon lifetime; exit code = Python exit code.
    # Never used by health-check.ps1 (see below) — this is for a human running
    # it directly in a terminal they intend to watch.
    Write-Host "Starting runtime daemon (foreground)..."
    Write-ClankLog -Paths $Paths -Name "runtime" -Message "start-runtime.ps1 invoking -m runtime.daemon (foreground)"
    & $venvPy -u -m runtime.daemon
    exit $LASTEXITCODE
}

# Default: detached background start, PID recorded so health-check.ps1's
# Test-ClankProcess can actually find it on the next cycle.
#
# BUG THIS FIXES (found during the production/development isolation phase,
# 2026-08-10): this script previously ran the daemon *synchronously* with no
# PID-file write at all — Save-PidMeta (in _common.ps1) already existed but
# was never called here. health-check.ps1 calls this script directly (`&`,
# not backgrounded) every ~15 minutes when Test-ClankProcess reports the
# runtime isn't alive; against a synchronous, never-recorded daemon, that
# check can never succeed, so every cycle that finds "not running" started
# *another* indefinitely-running daemon process, all against the same SQLite
# production database. Two such orphaned processes were found and stopped as
# part of this phase — see docs/infra/PRE_SPLIT_PRODUCTION_SNAPSHOT.md.
if (Test-ClankProcess -PidFile $Paths.RuntimePid -ExpectedKind "runtime") {
    $existing = Get-PidMeta -PidFile $Paths.RuntimePid
    Write-Host "Runtime already running (PID $($existing.pid)) - not starting a duplicate."
    Write-ClankLog -Paths $Paths -Name "runtime" -Message "start-runtime.ps1: already running, PID $($existing.pid), skipped"
    exit 0
}

$stdOutLog = Join-Path $Paths.LogDir "runtime.out.log"
$stdErrLog = Join-Path $Paths.LogDir "runtime.err.log"
$proc = Start-Process -FilePath $venvPy `
    -ArgumentList "-u", "-m", "runtime.daemon" `
    -WorkingDirectory $Paths.Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdOutLog `
    -RedirectStandardError $stdErrLog `
    -PassThru

Save-PidMeta -PidFile $Paths.RuntimePid -ProcessId $proc.Id -Kind "runtime"
Write-Host "Started runtime daemon, PID $($proc.Id)."
Write-ClankLog -Paths $Paths -Name "runtime" -Message "start-runtime.ps1: started PID $($proc.Id)"
exit 0
