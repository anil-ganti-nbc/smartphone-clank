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

Write-Host "Starting dashboard on http://${hostAddr}:$port/ (synchronous)..."
& $venvPy -u main.py dashboard --host $hostAddr --port $port
exit $LASTEXITCODE
