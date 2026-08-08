# v0.3.6 Runtime Repair Audit

| Original defect | Repair | Test | Validation |
|-----------------|--------|------|------------|
| Sitemap not in `build_collectors` | `SamsungSitemapCollector` adapter + registry | `test_runtime_registry.py` | locally executed |
| Obsolete support substituted | `samsung_support` disabled by default | test_legacy_support_disabled | locally executed |
| Task Scheduler supervises wrapper | install registers `python.exe -m runtime.daemon` | validate-runtime-supervision.ps1 | WINDOWS_LIVE_VALIDATION_REQUIRED |
| Detached Start-Process | start-runtime.ps1 synchronous `& python; exit $LASTEXITCODE` | script review | fixture/script |
| No immediate startup run | DateTrigger +5s for sitemap in daemon | code review | locally reviewed |
| Installer warns on critical failure | Register-ClankPythonTask exits 2 on failure | script review | WINDOWS_LIVE_VALIDATION_REQUIRED |
| Metrics missing | already in pipeline.run_collector | test_metrics | locally executed |
| Soak can pass without runs | weekly report checks runs_7d (prior) | weekly report logic | residual: enforce INVALID in report text |

## Residual risk

- Windows Task Scheduler restart behaviour not executed in this Linux environment
- bluetooth_sig / generic OEM collectors may still be noisy if enabled
- Installer read-back of tasks requires Windows
