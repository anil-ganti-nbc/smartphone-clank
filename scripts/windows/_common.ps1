# Shared helpers for Clank Windows scripts. Dot-source only.

$ErrorActionPreference = "Stop"

function Get-ClankRoot {
    $here = $PSScriptRoot
    if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
    # scripts/windows -> repo root
    return (Resolve-Path (Join-Path $here "..\..")).Path
}

function Get-ClankPaths {
    $root = Get-ClankRoot
    $rt = Join-Path $root "config\windows_runtime.yaml"
    $paths = @{
        Root          = $root
        VenvPython    = Join-Path $root ".venv\Scripts\python.exe"
        VenvActivate  = Join-Path $root ".venv\Scripts\Activate.ps1"
        RuntimeYaml   = $rt
        LogDir        = Join-Path $root "runtime\logs"
        PidDir        = Join-Path $root "runtime\pids"
        BackupDir     = Join-Path $root "runtime\backups"
        ReportDir     = Join-Path $root "runtime\reports"
        DiagnosticsDir= Join-Path $root "runtime\diagnostics"
        DataDir       = Join-Path $root "data"
        RuntimePid    = Join-Path $root "runtime\pids\runtime.pid"
        DashboardPid  = Join-Path $root "runtime\pids\dashboard.pid"
        RuntimeLock   = Join-Path $root "runtime\pids\runtime.lock"
        DashboardLock = Join-Path $root "runtime\pids\dashboard.lock"
        EnvFile       = Join-Path $root ".env"
        ConfigYaml    = Join-Path $root "config\config.yaml"
        SamsungYaml   = Join-Path $root "config\samsung_sources.yaml"
    }
    foreach ($k in @("LogDir","PidDir","BackupDir","ReportDir","DiagnosticsDir","DataDir")) {
        if (-not (Test-Path $paths[$k])) {
            New-Item -ItemType Directory -Path $paths[$k] -Force | Out-Null
        }
    }
    return $paths
}

function Import-ClankEnv {
    param([hashtable]$Paths)
    $envFile = $Paths.EnvFile
    if (Test-Path $envFile) {
        Get-Content $envFile -Encoding UTF8 | ForEach-Object {
            $line = $_.Trim()
            if (-not $line -or $line.StartsWith("#")) { return }
            $i = $line.IndexOf("=")
            if ($i -lt 1) { return }
            $name = $line.Substring(0, $i).Trim()
            $val = $line.Substring($i + 1).Trim().Trim('"').Trim("'")
            # Never echo secrets
            if ($name -match "WEBHOOK|TOKEN|SECRET|PASSWORD|KEY") {
                [Environment]::SetEnvironmentVariable($name, $val, "Process")
            } else {
                [Environment]::SetEnvironmentVariable($name, $val, "Process")
            }
        }
    }
    if (-not $env:CLANK_DASHBOARD_HOST) { $env:CLANK_DASHBOARD_HOST = "127.0.0.1" }
    if (-not $env:CLANK_DASHBOARD_PORT) { $env:CLANK_DASHBOARD_PORT = "8200" }
    if (-not $env:CLANK_RUNTIME_MODE) { $env:CLANK_RUNTIME_MODE = "production" }
}

function Write-ClankLog {
    param(
        [hashtable]$Paths,
        [string]$Name,
        [string]$Message,
        [string]$Level = "INFO"
    )
    $file = Join-Path $Paths.LogDir "$Name.log"
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $line = "$ts [$Level] $Message"
    Add-Content -Path $file -Value $line -Encoding UTF8
}

function Test-ProcessAlive {
    param([int]$ProcessId)
    try {
        $p = Get-Process -Id $ProcessId -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Get-PidMeta {
    param([string]$PidFile)
    if (-not (Test-Path $PidFile)) { return $null }
    try {
        $raw = Get-Content $PidFile -Raw -Encoding UTF8
        $obj = $raw | ConvertFrom-Json
        return $obj
    } catch {
        return $null
    }
}

function Save-PidMeta {
    param(
        [string]$PidFile,
        [int]$ProcessId,
        [string]$Kind
    )
    $meta = @{
        pid = $ProcessId
        kind = $Kind
        started_utc = (Get-Date).ToUniversalTime().ToString("o")
        command = "SmartphoneIntelClank"
    } | ConvertTo-Json -Compress
    Set-Content -Path $PidFile -Value $meta -Encoding UTF8
}

function Test-ClankProcess {
    param([string]$PidFile, [string]$ExpectedKind)
    $meta = Get-PidMeta -PidFile $PidFile
    if (-not $meta) { return $false }
    $pidVal = [int]$meta.pid
    if (-not (Test-ProcessAlive -ProcessId $pidVal)) { return $false }
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidVal"
        if (-not $proc) { return $false }
        $cmd = $proc.CommandLine
        if ($cmd -and ($cmd -match "main\.py|dashboard|SmartphoneIntelClank|uvicorn")) {
            return $true
        }
        # Fallback: python process with matching start — soft accept if PID alive and meta kind matches
        if ($ExpectedKind -and $meta.kind -eq $ExpectedKind) {
            return $true
        }
    } catch {}
    return $false
}

function Clear-StalePid {
    param([string]$PidFile)
    if (Test-Path $PidFile) {
        if (-not (Test-ClankProcess -PidFile $PidFile -ExpectedKind "")) {
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
            return $true
        }
    }
    return $false
}

function Get-DashboardPort {
    $p = $env:CLANK_DASHBOARD_PORT
    if (-not $p) { $p = "8200" }
    return [int]$p
}

function Test-PortFree {
    param([int]$Port)
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conns) { return $false }
        return $true
    } catch {
        # Fallback: netstat
        $out = netstat -ano | Select-String ":$Port\s+.*LISTENING"
        return -not [bool]$out
    }
}

function Get-PortOwners {
    param([int]$Port)
    $result = @()
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
            $result += [pscustomobject]@{
                LocalAddress = $c.LocalAddress
                Port = $Port
                Pid = $c.OwningProcess
                ProcessName = if ($proc) { $proc.ProcessName } else { "?" }
                Path = if ($proc) { try { $proc.Path } catch { "" } } else { "" }
            }
        }
    } catch {
        $result += [pscustomobject]@{ LocalAddress = "?"; Port = $Port; Pid = 0; ProcessName = "lookup_failed"; Path = "" }
    }
    return $result
}

function Assert-LiveSourcesOrOverride {
    param(
        [hashtable]$Paths,
        [switch]$AllowNonLiveSources
    )
    $yamlPath = $Paths.SamsungYaml
    if (-not (Test-Path $yamlPath)) { return }
    $content = Get-Content $yamlPath -Raw -Encoding UTF8
    $reject = @("BLOCKED", "UNSUPPORTED", "FIXTURE_ONLY", "UNAVAILABLE", "NOT_RELEVANT")
    $enabledBlocks = [regex]::Matches($content, '(?ms)^[ \t]{2,4}([a-z0-9_]+):\s*\r?\n(?:.*?\r?\n)*?[ \t]+enabled:\s*true')
    # Simpler scan: lines with validation_status near enabled true sources
    $bad = @()
    $current = $null
    $enabled = $false
    Get-Content $yamlPath -Encoding UTF8 | ForEach-Object {
        if ($_ -match '^\s{2,4}([a-z0-9_]+):\s*$') { $current = $Matches[1]; $enabled = $false }
        if ($_ -match 'enabled:\s*true') { $enabled = $true }
        if ($enabled -and $_ -match 'validation_status:\s*(\S+)') {
            $st = $Matches[1].Trim('"')
            if ($reject -contains $st) {
                $bad += "$current=$st"
            }
        }
    }
    if ($bad.Count -gt 0 -and -not $AllowNonLiveSources) {
        throw "Enabled sources with non-live validation status: $($bad -join ', '). Pass -AllowNonLiveSources to override."
    }
    if ($bad.Count -gt 0 -and $AllowNonLiveSources) {
        Write-Warning "AllowNonLiveSources: $($bad -join ', ')"
    }
}

function Get-TaskXml {
    param(
        [string]$Name,
        [string]$Command,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [string]$TriggerType,  # startup | logon | daily | weekly | minutes
        [int]$Minutes = 15,
        [string]$UserId = ""
    )
    # Minimal task definition documentation — actual registration uses Register-ScheduledTask
    return [pscustomobject]@{
        Name = $Name
        Command = $Command
        Arguments = $Arguments
        WorkingDirectory = $WorkingDirectory
        TriggerType = $TriggerType
        Minutes = $Minutes
    }
}
