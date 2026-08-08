#Requires -Version 5.1
param([int]$TimeoutSec = 30)
$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "_common.ps1")
$Paths = Get-ClankPaths
$meta = Get-PidMeta -PidFile $Paths.RuntimePid
if (-not $meta) { Write-Host "Runtime not running (no PID file)."; exit 0 }
$pidVal = [int]$meta.pid
try {
    $p = Get-Process -Id $pidVal -ErrorAction Stop
    Write-Host "Stopping runtime PID $pidVal..."
    $p.CloseMainWindow() | Out-Null
    if (-not $p.WaitForExit($TimeoutSec * 1000)) {
        Write-Warning "Force kill after ${TimeoutSec}s"
        Stop-Process -Id $pidVal -Force
    }
} catch {
    Write-Host "Process already exited."
}
Remove-Item $Paths.RuntimePid -Force -ErrorAction SilentlyContinue
Remove-Item $Paths.RuntimeLock -Force -ErrorAction SilentlyContinue
Write-ClankLog -Paths $Paths -Name "runtime" -Message "stopped"
Write-Host "Runtime stopped."
