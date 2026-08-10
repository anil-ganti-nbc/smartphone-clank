# Production Scope Audit

Written during the scope-unification phase that followed the Motorola
promotion (`docs/wave2/MOTOROLA_CANARY_REPORT.md`), which exposed that two
independent, uncross-checked mechanisms both had to say "yes" for an OEM's
discoveries to actually reach `Device`/`Evidence` — and only one of them
was checked before startup.

## Part 2 — every mechanism that can include/exclude an OEM from production

| Mechanism | Purpose | Authoritative or derived? | Runtime consumer | Failure mode | Motorola mismatch relevance |
|---|---|---|---|---|---|
| `collectors/wave1/__init__.py::PRODUCTION_OEM_SCOPE` (was `WAVE1_PRODUCTION_SCOPE`, now an alias — see Part 3) | The explicit "is this OEM approved for production at all" allowlist | **Authoritative** | `build_wave1_production_collectors()` | None known — well-tested (`tests/wave1/test_production_scope.py`) | Motorola *was* correctly in this set; this mechanism worked |
| `config.yaml::manufacturers` | Pipeline-level filter — `pipeline.py::process_discoveries()` drops any `Discovery` whose manufacturer isn't in this list, for *every* source including Samsung | **Was a second, uncross-checked authority; now validated against scope (Part 4)** | `IntelligencePipeline.process_discoveries()` | Silently `continue`s past every discovery for an omitted manufacturer — no exception, no log line (before this phase), no visible effect except zero devices | **This is exactly what happened.** Motorola was in `PRODUCTION_OEM_SCOPE` and `wave1.motorola.enabled: true`, but absent from `manufacturers`, so every validated candidate was dropped after the fact |
| `config.yaml::wave1.<oem>.enabled` | Per-OEM operational on/off switch | Derived — meaningless without also being in `PRODUCTION_OEM_SCOPE` | `build_wave1_collectors()` / `build_wave1_production_collectors()` | A typo flipping this to `true` for a non-approved OEM does nothing by itself (regression-tested) | Not the bug — this flag was correctly `true` |
| `collectors/wave1/__init__.py::ADAPTER_REGISTRY` | Which OEMs have a real, callable `discover()` implementation | Derived (code-level fact, not a decision) | `build_wave1_collectors()` | An OEM missing here can never run regardless of every other flag — safe failure direction | Not the bug — Motorola's adapter was registered |
| `collectors/wave1/__init__.py::INTEGRATED_OEMS` | Which OEMs go through the full shared pipeline (`run_oem_staging_cycle`) vs. discovery-only quarantine (Xiaomi) | Derived — should always be a superset of `PRODUCTION_OEM_SCOPE` plus any staging-only integrated OEMs | `run_wave1_once()` (staging path only; production path in `runtime/daemon.py` doesn't use this — it calls `run_oem_staging_cycle` directly per-adapter) | An OEM absent here degrades silently to discovery-only (no persistence) — this *is* the intended path for Xiaomi | Not the bug — Motorola was correctly integrated |
| `models/schemas.py::Manufacturer` (enum) | Whether a string is a *recognized* manufacturer at all — a schema/type constraint, not a scope decision | Derived — a prerequisite, not a gate | `collectors/wave1/bridge.py::normalize_wave1_discovery()` (raises `UnsupportedManufacturerError` if absent) | Missing entry blocks *everything* for that OEM, everywhere — safe failure direction | Not the bug — Motorola was in the enum |
| `collectors/__init__.py::production_scope()` | Samsung's own collector-ID-based production gate (`production.samsung_only` config) | Authoritative, but scoped entirely to Samsung's specialized path — architecturally separate | `collectors/__init__.py::build_collectors()` | N/A to non-Samsung OEMs | Not applicable — Motorola never touches this function |
| `collectors/__init__.py::build_collectors()`'s hardcoded manufacturer fallback (`["samsung","google","oneplus","nothing","xiaomi"]`) | Fallback default for `bluetooth_sig`'s manufacturer-scan list *only*, used only if `settings.manufacturers` is completely absent from config | Derived, low-stakes, dead in practice (config.yaml always sets `manufacturers`) | `BluetoothSIGCollector` | Stale list here has zero effect on Device/Evidence persistence — `bluetooth_sig` is a certification-record collector, not part of the intelligence pipeline gate | Not the bug, but noted as a *sixth* place Motorola's name could theoretically need adding if this fallback were ever exercised. Left as-is — fixing this would require a source-controlled default (see Part 13 discussion of consolidation, out of scope here) |
| Adapter `validation_state` (`LIVE_VALIDATED` etc.) | Informational recon-quality signal, not a production gate | Derived/informational | Documentation, `main.py production scope` output | N/A — never gates persistence | Not applicable |
| Health/report "expected source" lists | Searched for; **none found**. `dashboard/app.py` and `main.py report` read directly from `collector_run_metrics`/`collector_runs`, with no separate static expectation list to drift out of sync | N/A | N/A | N/A | Confirms this specific failure mode doesn't have a *seventh* place to check |

## How many independent truths existed before this phase?

**Two**, for the specific question "will this OEM's discoveries actually
persist in production": `PRODUCTION_OEM_SCOPE` and `config.yaml::manufacturers`.
Every other mechanism in the table above is either a genuine prerequisite
(adapter exists, manufacturer is a recognized enum value) with a safe
(fail-closed) failure direction, or is architecturally separate (Samsung's
own gate). The bug was specifically that these two authorities were never
cross-checked against each other before startup.

## Part 3 — one authoritative declaration

`PRODUCTION_OEM_SCOPE` (`collectors/wave1/__init__.py`) remains the single
authoritative answer to "which non-Samsung OEMs are approved for
production." It is now an explicit alias of the pre-existing
`WAVE1_PRODUCTION_SCOPE` object (not a second variable — literally
`PRODUCTION_OEM_SCOPE = WAVE1_PRODUCTION_SCOPE`), so every existing test,
docstring, and call site referencing the old name keeps working unchanged.
New code (this phase's validation function and CLI command) uses the new
name. A full rename sweep was considered again and deferred a third time
for the same reason as the last two phases: it's a cosmetic change with no
functional benefit, and this phase's actual fix is the validation layer
below, not the name.

`config.yaml::manufacturers` is no longer an independent, uncross-checked
authority. It remains a real, separate config file (a manufacturer must
still be listed there for its discoveries to persist — that mechanism
itself is unchanged, see Rule 1 discussion below), but Part 4's startup
check now requires it to *agree* with `PRODUCTION_OEM_SCOPE` before the
daemon will start.

**Why keep two config surfaces instead of collapsing to one?** `manufacturers`
is a pipeline-wide filter shared by Samsung, staging OEMs, and production
OEMs alike (it's the same list `process_discoveries()` checks regardless
of caller) — collapsing it into `PRODUCTION_OEM_SCOPE` would either give
Wave 1/Wave 2's production allowlist authority over Samsung and staging
too (wrong — those have their own gates) or require threading a
Wave1-specific allowlist through Samsung's and staging's unrelated code
paths (unnecessary coupling). Keeping them separate but *validated for
agreement* is the minimal fix — see Part 4.

## Part 4 — fail-closed startup invariant

`collectors/wave1/__init__.py::validate_production_scope(settings)` computes,
for every OEM in `PRODUCTION_OEM_SCOPE` (plus every registered adapter, for
visibility into staging-only OEMs too): `manufacturer_configured` (in
`settings.manufacturers`), `adapter_registered` (in `ADAPTER_REGISTRY`),
`config_enabled` (`wave1.<oem>.enabled`), and `scheduled` (would actually
appear in `build_wave1_production_collectors()`'s output). An approved OEM
is `ok` only if all four are true.

`runtime/daemon.py::main()` calls
`assert_production_scope_or_refuse(settings)` immediately after loading
settings (before building any collector, before scheduling anything). On
mismatch it raises `ProductionScopeError` — `main()` catches it, logs the
full per-OEM breakdown, and returns exit code 1. **This is not a warning
path; the daemon does not start.** See `runtime/daemon.py` around the
`assert_production_scope_or_refuse` call.

Also exposed read-only via `python main.py production validate` (Part 7)
for diagnosis without needing a restart.

## Part 5/6 — baseline completion and no-silent-drop

Two related fixes in `pipeline.py::process_discoveries()` and
`collectors/wave1/staging_pipeline.py::run_oem_staging_cycle()`:

1. `process_discoveries()` now returns a fourth value,
   `dropped_out_of_scope` — the count of discoveries silently `continue`d
   past because their manufacturer wasn't in `settings.manufacturers`. Each
   drop is now also logged at `WARNING` level with the manufacturer and
   source, rather than being invisible.

2. `run_oem_staging_cycle()` computes
   `pipeline_accepted_something = (new + updated + resighted) > 0` and
   flags `silent_drop = result.valid > 0 and not pipeline_accepted_something`
   — validated candidates existed, but the pipeline persisted none of them.
   This is exactly the Motorola incident's shape. When `silent_drop` is
   true: the metrics run status is set to `"regression"` (not `"success"`),
   an explicit `SILENT_DROP` note and log line are recorded with the exact
   counts, and — critically — **`BaselineTracker.record_run()` is called
   with `run_succeeded=False`**, so baseline completion is refused. A
   source that fetches fine and returns valid candidates, but whose
   candidates are all dropped by a downstream scope mismatch, can no longer
   mark its baseline complete.

   Baseline completion was deliberately *not* changed to require "at least
   one new device" — a legitimate already-fully-baselined catalogue
   producing zero new devices on a later cycle is normal and must not be
   flagged. The invariant is specifically: *if validated candidates
   existed, the pipeline must have done something with at least one of
   them* (new, updated, or resighted all count — resighting alone is
   sufficient proof the pipeline is actually processing that manufacturer's
   discoveries, not silently discarding them).

See `tests/wave1/test_production_scope.py` (Part 8) for the regression
test reproducing this exact scenario end-to-end.
