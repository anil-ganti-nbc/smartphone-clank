#Requires -Version 5.1
# WINDOWS_LIVE_VALIDATION_REQUIRED for Task Scheduler restart checks.
$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "_common.ps1")
$Paths = Get-ClankPaths
Write-Host "=== Runtime supervision validation ===" -ForegroundColor Cyan
Write-Host "1. Preferred task action must be python.exe -m runtime.daemon"
$task = Get-ScheduledTask -TaskName "SmartphoneIntelClank-Runtime" -ErrorAction SilentlyContinue
if ($task) {
    $act = $task.Actions | Select-Object -First 1
    Write-Host "   Execute: $($act.Execute)"
    Write-Host "   Arguments: $($act.Arguments)"
    Write-Host "   WorkingDirectory: $($act.WorkingDirectory)"
    if ($act.Execute -like "*python*" -and $act.Arguments -match "runtime.daemon") {
        Write-Host "   PASS: Task points at Python daemon" -ForegroundColor Green
    } else {
        Write-Host "   FAIL: Task does not supervise Python daemon" -ForegroundColor Red
    }
} else {
    Write-Host "   Task not registered (run install.ps1 on Windows)" -ForegroundColor Yellow
}
Write-Host "2. Manual proof: start daemon, kill PID, confirm Task Scheduler restart"
Write-Host "   WINDOWS_LIVE_VALIDATION_REQUIRED"
