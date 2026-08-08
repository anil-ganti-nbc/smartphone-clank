# Runtime Collector Audit — v0.3.6

## Path for `python main.py run`

1. `main.py run` (not `--once`) → `runtime.daemon.main()`
2. `build_collectors(settings)` loads `config/config.yaml` + `config/samsung_sources.yaml`
3. Registers `SamsungSitemapCollector` when LIVE_VALIDATED and enabled
4. APScheduler interval jobs + **startup DateTrigger** (sitemap ~5s)
5. `pipeline.run_collector` → MetricsRecorder.finish always

## Production registry (post-repair)

| Collector ID | Class | Capability | Validation | Default enabled | Unknown URL discovery |
|--------------|-------|------------|------------|-----------------|----------------------|
| samsung_us_support_sitemap | SamsungSitemapCollector | discovery | LIVE_VALIDATED | yes | **yes** |
| samsung_support | SamsungSupportCollector | monitoring | LIVE_PARTIAL | **no** | no |
| bluetooth_sig | BluetoothSIGCollector | monitoring | depends | config | limited |
| *_support OEM | GenericSupportCollector | monitoring | depends | config | limited |
| skeletons (bis/tdra/imda/fcc) | — | — | — | **never registered** | — |

## Defects repaired

1. Sitemap discovery registered in production path
2. Legacy support secondary/disabled by default
3. Task Scheduler must point at `python -m runtime.daemon` (not detached wrapper)
4. Startup sitemap job within ~5 seconds
5. Metrics on every run via pipeline
