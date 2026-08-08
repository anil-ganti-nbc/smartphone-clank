#Requires -Version 5.1
$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "_common.ps1")
$Paths = Get-ClankPaths
Import-ClankEnv -Paths $Paths
$venvPy = $Paths.VenvPython
$day = Get-Date -Format "yyyy-MM-dd"
$md = Join-Path $Paths.ReportDir "week-$day.md"
$json = Join-Path $Paths.ReportDir "week-$day.json"

Push-Location $Paths.Root
$summary = & $venvPy -c @"
import json, os, sqlite3
from datetime import datetime, timedelta
from pathlib import Path

db = Path('data/clank.db')
report = {
  'generated_utc': datetime.utcnow().isoformat() + 'Z',
  'version': '0.3.5',
  'quiet_week_trusted': 'Insufficient data',
  'reasons': [],
  'database_bytes': db.stat().st_size if db.exists() else 0,
  'runs_7d': 0,
  'success_rate': None,
}
if db.exists():
    c = sqlite3.connect(str(db))
    try:
        since = (datetime.utcnow() - timedelta(days=7)).isoformat()
        try:
            rows = c.execute(
                \"SELECT status, COUNT(*) FROM collector_run_metrics WHERE started_at >= ? GROUP BY status\",
                (since,)
            ).fetchall()
            total = sum(n for _, n in rows)
            ok = sum(n for s, n in rows if s == 'success')
            report['runs_7d'] = total
            report['success_rate'] = (ok / total) if total else None
            report['by_status'] = {s: n for s, n in rows}
            if total == 0:
                report['quiet_week_trusted'] = 'No'
                report['reasons'].append('zero collector runs in 7 days')
            elif report['success_rate'] is not None and report['success_rate'] >= 0.9:
                report['quiet_week_trusted'] = 'Yes'
                report['reasons'].append('runs present and success_rate >= 0.9')
            else:
                report['quiet_week_trusted'] = 'Yes, with warnings'
                report['reasons'].append('runs present but success_rate below 0.9')
        except Exception as e:
            report['reasons'].append(f'metrics_table: {e}')
            report['quiet_week_trusted'] = 'Insufficient data'
    finally:
        c.close()
else:
    report['reasons'].append('database missing')

print(json.dumps(report, indent=2))
Path(r'$json').write_text(json.dumps(report, indent=2), encoding='utf-8')
md = [
  f\"# Clank Weekly Report — $day\",
  '',
  f\"Quiet week trusted: **{report['quiet_week_trusted']}**\",
  '',
  'Reasons:',
]
for r in report['reasons']:
    md.append(f'- {r}')
md += [
  '',
  f\"Runs (7d): {report['runs_7d']}\",
  f\"Success rate: {report['success_rate']}\",
  f\"Database bytes: {report['database_bytes']}\",
]
Path(r'$md').write_text('\\n'.join(md) + '\\n', encoding='utf-8')
print('wrote', r'$md')
"@
Write-Host $summary
Write-ClankLog -Paths $Paths -Name "reports" -Message "weekly report $md"

# validation-week-1 if marker present
$marker = Join-Path $Paths.ReportDir "validation_start.json"
if (Test-Path $marker) {
    Copy-Item $md (Join-Path $Paths.ReportDir "validation-week-1.md") -Force
}
