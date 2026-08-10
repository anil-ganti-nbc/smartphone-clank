# Wave 1 Integration Report

Date: 2026-08-10. Scope: connect Google, OnePlus, Nothing to the real shared
intelligence pipeline inside the isolated staging environment; keep Xiaomi
quarantined; determine independent production-readiness per OEM.

## A. Production integrity

**Before:** 97 Samsung devices, 98 evidence rows, 0 non-Samsung rows,
SHA-256 `addb5e29...` (see `docs/wave1/SAMSUNG_GOLDEN_STATE.md`), backed up to
`data/backups/clank_pre_wave1_integration_20260810_144540.db`.

**During:** production `collector_runs` grew from 118 → 121 and
`sitemap_traversal_state.cycles_completed` advanced (55 → 67) *during* this
session. Verified this was the **real, independently-running production
Windows-scheduled task** (`run_reason` on the new rows is exclusively
`samsung_us_support_sitemap` / `production_scheduled` and `production_manual`
— matches the mission's own description of an already-operating scheduled
collector), not anything Wave 1 code touched. Confirmed via:
- Zero rows for any Wave1-named collector in `collector_run_metrics` newer
  than the 2026-08-05 incident's historical rows (those are the original
  incident record, `google_support`/`oneplus_support` etc. dated 2026-08-05,
  correctly still present as a permanent audit trail, not new activity).
- `devices` table unchanged: 97 rows, 100% Samsung, both before and after.

**One real anomaly, found and corrected:** `wave1_baseline_state` (a table
introduced this phase) briefly appeared — empty, 0 rows — in production
`data/clank.db`, discovered via a SHA-256 mismatch investigation. Root cause
not conclusively isolated (see `HANDOFF.md` §11 for the working theory:
`Base.metadata` is a process-wide SQLAlchemy singleton, and some `create_all()`
call, plausibly triggered by the independently-running production scheduler
sharing this working tree, ran after `database.models_v03` had been imported
by Wave 1 code somewhere). Dropped from production immediately on discovery;
Samsung's 97/98 counts were independently confirmed unaffected before and
after. Recommended follow-up: gate new tables behind an explicit Alembic
migration rather than `create_all()`.

**After:** 97 Samsung devices, 98 evidence rows, 0 non-Samsung rows, 0 Wave 1
tables in production, 0 Wave 1 evidence/aliases/confidence-ledger rows in
production. Canonical suite: **119 passed, 0 failed, 0 skipped, 0 xfailed**.

## B. Shared-core findings (Samsung-assumption hostile audit)

Searched `entity_resolution/`, `database/models.py`, `pipeline.py`, `alerts/`,
`observability/` for `samsung`/`SM-`/`galaxy` (case-insensitive):

| Location | Finding | Classification | Action |
|---|---|---|---|
| `alerts/maintenance.py` | Maintenance alert hardcoded `"Samsung Collector Degraded"` regardless of which collector actually degraded | **Incorrect shared-core assumption** | Fixed — generalized to `"Collector Degraded"` |
| `entity_resolution/resolver.py::_extract_family_key` | Regional-suffix stripping tuned for Samsung's `SM-XXXXB/U/N/W/0/E/J/Z` pattern, comment says "typical for Samsung etc." | Legitimate Samsung-adapter knowledge, but generically applied | Verified harmless for other OEMs (none of their identifiers end in those single letters immediately after a digit) — left as-is, documented, not rewritten (spec: don't rewrite without demonstrated need) |
| `entity_resolution/families.py::infer_and_attach` | Family-name regex originally covered only `galaxy s\d+`, `galaxy z \w+`, `pixel \d+`, `nothing phone\d*` | Incomplete, not incorrect — false-split-safe gap | Extended to include `cmf phone`, `oneplus \d+`/`open`/`nord`, `redmi note \d+`/`redmi \d+`, `poco \w+`, `xiaomi \d+` |
| `knowledge/data/manufacturers.yaml` | Already had profiles for google/oneplus/nothing/xiaomi (launch months, series patterns) before this phase | Pre-existing, correctly generic | No change needed |
| `pipeline.py` (log line, not Samsung-specific but discovered operating Wave1 live) | `f"{old_confidence} → {device.confidence}"` uses a unicode arrow that crashes on Windows cp1252 console (`UnicodeEncodeError`) the first time this exact log branch fires in this environment | Robustness bug, not a Samsung assumption | Fixed — ASCII `->` |
| `database/models.py::Device.model_number` | `nullable=False`, `UniqueConstraint(manufacturer, model_number)` | See §C — not actually blocking, but investigated as instructed | No change |

No other `samsung`/`SM-`/`galaxy` occurrences found outside `collectors/samsung*`
(legitimate, Samsung's own collector code) and comments/docstrings.

## C. Candidate-vs-Device boundary audit

`models/schemas.py::Discovery.model_number` is a required `str`, and
`database/models.py::Device.model_number` is `NOT NULL` with a unique
constraint on `(manufacturer, model_number)`. This is a real constraint — but
**it was never actually triggered this phase**, because every Wave 1 OEM
validator's `VALID` outcome always carries a non-null `normalized_identifier`
by construction (marketing name doubles as the canonical identifier when an
OEM exposes no separate internal code, e.g. Google's `"Pixel 11"`, Nothing's
`"Phone (3)"`). A candidate that has no usable identifier text is `INVALID`
or `AMBIGUOUS`, never `VALID` with a null identifier — see
`collectors/wave1/validator.py::ValidationOutcome.__post_init__`.

The deeper concern the spec raises (a bare "Pixel 11" series-name teaser
might later split into "Pixel 11", "Pixel 11 Pro", "Pixel 11 Pro XL" as
separate shipping devices) is a **family-relationship** question, not a
null-identifier one. Today's resolver does not auto-link "Pixel 11" and a
later "Pixel 11 Pro" into one family (no shared regional-suffix or explicit
rule connects them) — they would resolve as two independent sibling Device
rows. This is exactly the "false split is safer than false merge" outcome
the spec itself prefers (section 19/21), so it was left as-is rather than
"fixed." The existing `RejectedCandidate` table already serves as the
analyst-review/candidate layer the spec describes for anything that doesn't
reach VALID — no new table was needed.

**Google Pixel 11 teaser, concretely** (spec section 57): when the adapter
resolves `"Pixel 11"` as VALID (matches the OEM validator's bare-generation
grammar), it becomes a real `Device` row with `manufacturer=google`,
`model_number="PIXEL 11"`, `marketing_name="Pixel 11"`, confidence 10 (single
support-page-tier evidence), family `Pixel` (via `FamilyService`). No model
number was fabricated — the marketing name *is* the identifier Google itself
exposes; there is no invented precision beyond what the source actually said.
If a later official Google source reveals a formal Pixel 11 variant/SKU
identifier, it will resolve into either the same Device (if `find_existing`
matches) or a sibling Device (if it doesn't) — either outcome is safe by the
spec's own stated preference.

## D. Integration bridge

`collectors/wave1/bridge.py::normalize_wave1_discovery()` — narrow, single
function, no entity-resolution/confidence logic. Preserves manufacturer,
raw identifier, marketing name, canonical URL, source name, region, discovery
timestamp, validation result, and source metadata in `Discovery.raw`. CMF (a
real brand the Nothing adapter surfaces, not in the `Manufacturer` enum) is
explicitly **not** coerced into an existing enum value or silently dropped —
it's routed to `RejectedCandidate` with reason
`unsupported_manufacturer_pending_schema_decision`, per the spec's own
instruction to defer the CMF schema decision rather than solve it here.

No `GooglePipeline`/`OnePlusPipeline`/`NothingPipeline` were created. All
three OEMs share one `IntelligencePipeline` instance and one
`process_discoveries()` call path — see `collectors/wave1/staging_pipeline.py::run_oem_staging_cycle()`.

## E. Per-OEM baseline epochs

`database/models_v03.py::SourceBaselineState` — one row per `source_id`
(`google_store_category_phones`, `oneplus_regional_sitemap`,
`nothing_products_sitemap`), independent completion timestamps. Verified
Google completing baseline does not block/depend on OnePlus or Nothing
(`tests/wave1/test_integration.py`, live smoke run — all three completed
baseline in the same run but each recorded independently).

## F. Cross-OEM integrity — proven, not assumed

`tests/wave1/test_integration.py`:
- `test_identical_marketing_strings_stay_separate_across_manufacturers`
- `test_same_model_string_different_manufacturer_never_merges` — the direct
  collision test: the *same* identifier string (`"PHONE X"`) pushed through
  both OnePlus and Nothing resolves to two distinct `Device` rows.

Live hostile audit of the real staging DB after 3 cycles (`docs/wave1/` SQL
queries, full results below) found: 0 duplicate marketing names across
manufacturers, 0 duplicate model numbers across manufacturers, 0 devices with
no evidence, 0 promotional/suspicious words in any accepted identifier, 0
multi-space identifiers.

```text
manufacturer counts:        google=7, oneplus=16, nothing=9
duplicate marketing_name across mfr:  none
duplicate model_number across mfr:    none
devices with zero evidence:           none
suspicious words (offer/receive/buy/series/http): none matched
longest model_number:  "ONEPLUS NORD 200-5G" (19 chars) — legitimate
confidence range:       google 10-10, oneplus 10-10, nothing 20-30 (multi-region corroboration)
```

## G. Alerting — staging vs production, proven

- `tests/wave1/test_integration.py::test_baseline_import_creates_no_alerts` —
  baseline import: 0 rows in `webhook_deliveries`, 0 `alerts` rows with a
  non-null `discord_message_id`.
- `tests/wave1/test_integration.py::test_post_baseline_candidate_is_alert_eligible_not_suppressed_as_backfill` —
  fixture-controlled post-baseline event (catalogue A, then catalogue A + a
  genuinely new item) correctly distinguishes the new item from the
  unchanged resighting.
- `tests/wave1/test_discord_safety.py` (5 tests, permanent regression) —
  staging settings never resolve `DISCORD_WEBHOOK_URL` even when present in
  the process environment; staging fails closed to "no webhook" rather than
  borrowing the production URL; a staging message is visibly labelled
  `🧪 STAGING — NOT A PRODUCTION ALERT`; zero delivery attempts reach any
  transport when staging has no webhook configured, proven via an
  instrumented `WebhookTransport`.
- One real staging alert message generated end-to-end (webhook disabled,
  content captured, not sent) — see `docs/wave1/sample_staging_alert.txt`.

## H. Operations

- Live 3-cycle staging soak against real official sources (Google, OnePlus,
  Nothing): device/evidence counts identical across cycles 2 and 3 (32
  devices / 44 evidence, stable). `run_count=3` per source in
  `wave1_baseline_state`.
- Restart test: `tests/wave1/test_integration.py::test_baseline_state_and_devices_survive_process_restart` —
  fresh `IntelligencePipeline`/`session_factory` instances against the same
  file-backed staging DB path, no shared Python state, baseline/device data
  intact.
- Failure isolation: `tests/wave1/test_integration.py::test_one_oem_crash_does_not_block_others` —
  a crashing adapter for one OEM does not prevent another OEM's cycle from
  completing (also demonstrated live: the pre-fix `AttributeError` in
  Google's bridge call crashed only Google's cycle; Xiaomi's discovery-only
  path completed normally in the same run).
- HTTP failure semantics (`tests/wave1/test_failure_semantics.py`, 6 tests):
  403/429/500/timeout never complete baseline, never remove existing devices,
  always record the failure; recovery after a temporary failure resumes
  normally (new candidates still detected, no data loss).
- Real live observation of the 200⇄403 instability: Xiaomi's `mi.com/global/sitemap/`
  returned HTTP 403 on this session's second `main.py run --environment staging --once`
  and HTTP 200 on the third, within minutes of each other — direct
  confirmation of the recon finding that justified KEEP_STAGING.

## I. Tests

```bash
PYTHONPATH=. python -m pytest -q
```

```text
119 passed, 0 failed, 0 skipped, 0 xfailed
```

(98 pre-this-phase + 21 new: 10 in `test_integration.py`, 6 in
`test_failure_semantics.py`, 5 in `test_discord_safety.py`.)

## J. Known limitations

See `HANDOFF.md` §11 for the full list (SourceBaselineState production leak
+ remediation, `init_db()` not running migrations, `record_alert()`
unconditional local row, RegionalSighting table not yet wired, SourceHealth
table not yet wired for any OEM including Samsung).
