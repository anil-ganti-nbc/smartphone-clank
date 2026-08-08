#Requires -Version 5.1
$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "stop-runtime.ps1")
Start-Sleep -Seconds 2
& (Join-Path $PSScriptRoot "start-runtime.ps1")
