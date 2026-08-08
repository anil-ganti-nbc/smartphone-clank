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

# Synchronous: stays alive for daemon lifetime; exit code = Python exit code
Write-Host "Starting runtime daemon (synchronous)..."
Write-ClankLog -Paths $Paths -Name "runtime" -Message "start-runtime.ps1 invoking -m runtime.daemon"
& $venvPy -u -m runtime.daemon
exit $LASTEXITCODE
