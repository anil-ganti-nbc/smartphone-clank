#Requires -Version 5.1
param(
    [switch]$List,
    [switch]$Verify,
    [string]$Restore = "",
    [switch]$ConfirmRestore
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")
$Paths = Get-ClankPaths
Import-ClankEnv -Paths $Paths
$venvPy = $Paths.VenvPython
$dbPath = Join-Path $Paths.DataDir "clank.db"
$backupDir = $Paths.BackupDir

if ($List) {
    Get-ChildItem $backupDir -Filter "*.db" | Sort-Object LastWriteTime -Descending | Format-Table Name, Length, LastWriteTime
    exit 0
}

if ($Restore) {
    if (-not $ConfirmRestore) { throw "Refusing restore without -ConfirmRestore" }
    if (-not (Test-Path $Restore)) { throw "Backup not found: $Restore" }
    if (Test-Path $dbPath) {
        $pre = Join-Path $backupDir ("pre_restore_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".db")
        Copy-Item $dbPath $pre -Force
        Write-Host "Pre-restore backup: $pre"
    }
    Copy-Item $Restore $dbPath -Force
    Write-Host "Restored $Restore -> $dbPath"
    exit 0
}

if (-not (Test-Path $dbPath)) {
    Write-Host "No database yet at $dbPath"
    exit 0
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dest = Join-Path $backupDir "clank_$stamp.db"

# SQLite online backup via Python
& $venvPy -c @"
import sqlite3, shutil, os
src = r'$dbPath'
dst = r'$dest'
# Prefer backup API
s = sqlite3.connect(src)
d = sqlite3.connect(dst)
with d:
    s.backup(d)
d.close(); s.close()
print('ok', os.path.getsize(dst))
"@

if ($Verify -or $true) {
    $ic = & $venvPy -c "import sqlite3; c=sqlite3.connect(r'$dest'); print(c.execute('PRAGMA integrity_check').fetchone()[0])"
    Write-Host "Backup: $dest integrity=$ic"
    Write-ClankLog -Paths $Paths -Name "backup" -Message "backup=$dest integrity=$ic"
}

# Retention: keep 14 daily-ish newest
$files = Get-ChildItem $backupDir -Filter "clank_*.db" | Sort-Object LastWriteTime -Descending
$i = 0
foreach ($f in $files) {
    $i++
    if ($i -gt 14) { Remove-Item $f.FullName -Force }
}
