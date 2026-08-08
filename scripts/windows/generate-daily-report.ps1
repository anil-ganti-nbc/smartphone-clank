#Requires -Version 5.1
$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "_common.ps1")
$Paths = Get-ClankPaths
Import-ClankEnv -Paths $Paths
$venvPy = $Paths.VenvPython
$outDir = $Paths.ReportDir
$day = Get-Date -Format "yyyy-MM-dd"
$md = Join-Path $outDir "daily-$day.md"
Push-Location $Paths.Root
try {
    & $venvPy main.py report daily 2>&1 | Out-File -FilePath $md -Encoding utf8
    Write-Host "Wrote $md"
    Write-ClankLog -Paths $Paths -Name "reports" -Message "daily report $md"
} finally {
    Pop-Location
}
