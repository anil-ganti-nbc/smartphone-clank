# Architecture Map

One-page orientation for a developer arriving cold. Per
`docs/ENGINEERING_PRINCIPLES.md` Rule 18 — if this stops being
representable this simply, that's a signal to investigate, not to expand
this document.

## Main intelligence path

    SOURCE (OEM website: sitemap / category page / support index)
      |
      v
    ADAPTER                    collectors/{samsung,wave1,wave2}/*/discovery.py
      |  emits DiscoveryResult (unvalidated candidate)
      v
    VALIDATOR                  collectors/wave1/*/model_validator.py,
      |  emits ValidationOutcome    collectors/wave2/*/model_validator.py
      |  (VALID | INVALID | AMBIGUOUS, fails closed)
      v
    BRIDGE                     collectors/wave1/bridge.py
      |  normalizes VALID outcomes -> models.schemas.Discovery
      v
    RESOLVER                   entity_resolution/resolver.py
      |  finds-or-creates Device, appends Evidence
      v
    DEVICE + EVIDENCE          database/models.py::Device, Evidence
      |
      v
    ALIASES / FAMILIES         entity_resolution/aliases.py, families.py
      |
      v
    CONFIDENCE                 entity_resolution/confidence_service.py,
      |  (+ decay)                 confidence_ledger.py, decay.py
      v
    TIMELINE                   entity_resolution/timeline.py
      |
      v
    ALERT ELIGIBILITY          alerts/eligibility.py::newsroom_eligible()
      |  (reason + backfill -> bool)
      v
    WEBHOOK DELIVERY           alerts/discord.py::_send()/_record_delivery()
      |  ALWAYS writes a WebhookDelivery row (database/models.py),
      |  regardless of outcome — this is the source of truth for
      |  eligible/suppressed/attempted/delivered/failed
      v
    ALERT                      alerts/discord.py::record_alert()
         writes an Alert row ONLY when delivery actually succeeded
         (database/models.py::Alert — "delivered to Discord", nothing else)

Orchestration: `pipeline.py::IntelligencePipeline.process_discoveries()`
drives Resolver -> Aliases -> Families -> Confidence -> Timeline -> Alerts
for every source, Samsung included — this is the "shared downstream
services" Rule 2 refers to. `collectors/wave1/staging_pipeline.py::run_oem_staging_cycle()`
is the same pipeline, entered via the Adapter/Validator/Bridge stages
first for Wave 1/Wave 2 OEMs; Samsung's collector calls
`process_discoveries()` more directly (see Known limitation in
`docs/wave2/POST_WAVE2_COMPLEXITY_AUDIT.md`).

## Scheduler / operations path

    SCHEDULER                  runtime/daemon.py (APScheduler BlockingScheduler,
      |                          single-worker ThreadPoolExecutor — serializes jobs)
      v
    COLLECTORS                 one scheduled job per production source
      |                          (Samsung: dedicated job; Google/Nothing/OnePlus/
      |                           Motorola: shared wave1-collector scheduling loop)
      v
    METRICS                    observability/metrics.py::MetricsRecorder
      |                          -> collector_run_metrics, collector_runs (legacy-compat)
      v
    HEALTH                     database/schema_guard.py (schema authority check
                                 at process start), dashboard/app.py (read-only
                                 view of the above)

## Owning module per stage

| Stage | Module |
|---|---|
| Discovery adapter registration | `collectors/wave1/__init__.py::build_wave1_collectors()` / `build_wave1_production_collectors()` |
| Production eligibility | `collectors/wave1/__init__.py::WAVE1_PRODUCTION_SCOPE` |
| Staging eligibility | `config/config.staging.yaml::manufacturers` + `--environment staging` runtime assertion (`runtime/environment.py`) |
| Entity resolution | `entity_resolution/resolver.py` |
| Confidence mutation | `entity_resolution/confidence_service.py` (ledger: `entity_resolution/confidence_ledger.py`) |
| Evidence persistence | `entity_resolution/resolver.py` (via `database/models.py::Evidence`) |
| Alert eligibility | `alerts/eligibility.py` |
| Alert delivery persistence | `alerts/discord.py::_record_delivery()` -> `WebhookDelivery` |
| Schema migration | Alembic (`alembic/versions/`), enforced via `database/schema_guard.py` |
| Scheduler execution | `runtime/daemon.py` |
| Health reporting | `observability/metrics.py` + `dashboard/app.py` |

## Database semantic boundaries (Rule 12)

    Device            = canonical device identity (one row per real phone)
    Evidence           = one observation supporting a device/state
    WebhookDelivery    = every alert transport decision (eligible/suppressed/
                          attempted/delivered/failed) — always written
    Alert              = successfully delivered alert only — written iff
                          WebhookDelivery.delivered was true this cycle
