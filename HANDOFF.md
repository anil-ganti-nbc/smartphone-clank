# HANDOFF — Smartphone Intel Clank

Last updated: 2026-08-08, end of v0.3.9 integrity pass.

This is the authoritative "what's actually true right now" document. If this
conflicts with a `docs/V038_*` or `PROGRESS_v0.3.*` doc, **this file wins** —
those are historical audit trails, this is current state.

## 1. Current state (verified live, not from memory)

- **Database**: `data/clank.db` — 97 devices, **all Samsung**, 98 evidence rows.
  No Google/OnePlus/Nothing/Xiaomi/BluetoothSIG rows exist.
- **Samsung sitemap coverage**: 126/126 URLs in `sitemap_product_urls` have
  `attempt_count > 0` (zero `never_attempted`). Coverage is complete for the
  current sitemap snapshot.
- **Production scope** (`collectors.production_scope()`): `{samsung_us_support_sitemap}`
  only. `samsung_support` (legacy secondary) is `LIVE_PARTIAL`/not validated,
  stays out. `samsung_us_owners_product` is `LIVE_VALIDATED` in
  `config/samsung_sources.yaml` but has **no collector implementation** — it is
  explicitly excluded from scope (`RUNNABLE_SAMSUNG_SOURCE_IDS` in
  `collectors/__init__.py`) so scope never advertises something nothing can run.
- **Config provenance**: no `config/config.local.yaml` present → running on
  tracked repo defaults (Samsung-only). Verify anytime with
  `python main.py production scope`.
- **`.env`**: now actually loaded by every Python entry point (CLI, dashboard,
  daemon) — see §4.

## 2. What changed in this session (v0.3.9, two phases)

### Phase 1 — Discord webhook test transport
- `alerts/eligibility.py`, `alerts/delivery.py` (structured `DeliveryResult`,
  `WebhookTransport` with retry/backoff/429 handling, URL redaction).
- `database.models.WebhookDelivery` — every send attempt persisted (eligible/
  suppressed/attempted/delivered/status/error), test sends flagged `test_mode`.
- `alerts/discord.py` / `alerts/maintenance.py` rewritten onto the above,
  signature-compatible with existing pipeline call sites.
- CLI: `python main.py discord status`, `discord test newsroom`, `discord test maintenance`.
- Dashboard: `/discord` page. Never renders a webhook URL, only "configured"/"not_configured".

### Phase 2 — Production scope lock + report integrity
**Provenance finding (resolved):** 73 non-Samsung device rows were traced to
one manual `main.py run --once` on 2026-08-05 while `config.yaml` had OEM
collectors mistakenly enabled — parser garbage (marketing text mis-parsed as
model numbers), not real intelligence. Backed up to
`data/backups/clank_pre_v039_cleanup_*.db`, then deleted (devices + cascaded
evidence/timeline/alerts/aliases). `collector_runs` history for the incident
was deliberately left as an audit trail.

- `collectors.production_scope()` + a unified `_eligible()` gate applied to
  every collector, Samsung and generic alike. Verified against a simulated
  config regression (flipping `google_support.enabled=true` in a live
  `Settings` object) — it stays excluded.
- `config/config.local.yaml` — untracked, deep-merged operator overlay.
  `config/config.yaml` (tracked) stays the safe Samsung-only baseline; a
  repo/archive re-extract can only ever touch tracked files, so local scope
  widening survives upgrades instead of being silently reverted.
- `run_reason` column (`production_scheduled` / `production_manual` / `demo`
  / `validation` / `test` / `fixture`) on `CollectorRun` and
  `CollectorRunRecord`, threaded through `pipeline.py`, `runtime/daemon.py`.
- `daily_report()` rewritten: IST (`Asia/Kolkata`) day boundary by default,
  expected/running/missing collectors, alert numbers sourced from
  `WebhookDelivery` (not the dead `alerts_sent` field), discoveries/updates/
  re-sightings/baseline-runs reported as four distinct numbers.
- `health_score()`: out-of-scope collectors report `N/A`; a collector needs
  ≥3 runs before it can be labeled "Healthy" (single clean run → "Provisional");
  stale collectors (>2× configured interval since last run) capped at 40.
- `alerts/delivery.py::channel_summary()` — single source of truth for alert
  counts, shared by CLI/dashboard/report.
- `python main.py production scope` — shows effective config provenance +
  live collector registry with skip reasons.

## 3. This session's integrity-pass fixes (post-phase-2, narrow scope)

1. **`samsung_us_owners_product` resolved** — excluded from `production_scope()`
   via `RUNNABLE_SAMSUNG_SOURCE_IDS` (only IDs with a real collector class).
   Scope/report/CLI no longer show a phantom `[MISSING]` for something
   nothing can run.
2. **`.env` loading regression fixed** — `.env` was previously only parsed by
   the PowerShell wrapper (`scripts/windows/_common.ps1`); running Python
   directly (CLI, dashboard, daemon) never saw it. `config/settings.py` now
   parses `.env` (stdlib only, `os.environ.setdefault`, real env vars still
   win) before reading `DISCORD_WEBHOOK_URL`/`MAINTENANCE_DISCORD_WEBHOOK_URL`.
   Verified both webhooks now show "configured" in `discord status`, the
   dashboard, and would be seen identically by the daemon.
3. **Re-sighting mechanism proved, not just fixed** — `tests/test_resighting.py`
   (4 tests) proves at the `EntityResolver` level: a re-fetch of an unchanged
   page does not create a duplicate `Evidence` row, does not change
   `confidence_contribution`, but does refresh `device.last_seen`; a genuinely
   different page for the same device still counts as new evidence. Cross-checked
   against live data: of 97 devices with repeat sitemap fetches, only one
   (`SM-G360`) has 2 evidence rows, and that's a legitimate case (two distinct
   URL slugs — `core-prime` and `galaxy-core-prime` — not a detection failure).
   The `resighted` counter itself was already wired into `daily_report()` in
   phase 2 (previously buried in an unread JSON blob in `notes`).
4. **Missing expected collectors now surface under "Attention required"** —
   `daily_report()` previously only evaluated collectors that had runs in the
   window; an expected-but-silent collector was invisible. Missing collectors
   now get a synthetic `{"score": None, "label": "MISSING"}` entry and appear
   in both `by_collector` and `attention`.
5. **Full test suite, exact count**: **78 passed / 0 failed / 3 blocked by a
   pre-existing, unrelated collection error**, 81 test functions total across
   16 files. The 3 blocked are in `tests/test_change_detection.py` — it
   imports `extract_hashes`/`compare_hashes` from `knowledge/change_detection.py`,
   which no longer exports them (renamed to `extract_fingerprint`/
   `compare_fingerprints` at some point before this session). Unrelated to
   production-scope/reporting work; not fixed here per "no unrelated features."
   (4 other files — `test_aliases_timeline`, `test_decay`,
   `test_entity_resolution`, `test_knowledge` — only fail when run as bare
   `python file.py` because they lack a `sys.path` bootstrap the other test
   files have; under correct invocation all 7 of their test functions pass.
   This project has no `pytest` in its own `.venv`, so "canonical" here means
   each file run directly via `.venv/Scripts/python.exe`.)
6. This document.

## 4. Known non-blocking issue (found, not fixed — flagging for the record)

`collectors/samsung/sitemap_collector.py`'s cycle-completion check
(`if cov["never_attempted"] == 0: cycles_completed += 1`) increments on
**every** run once the first full lap ever completes, not just when a fresh
lap actually completes — `never_attempted` stays permanently 0 after that
point, so the condition is always true. Live `sitemap_traversal_state` shows
`cycles_completed = 42`, which is not a real count of full traversals — it's
approximately "how many times this collector has ever run since first
reaching full coverage," inflated further by manual testing this session.
**This does not affect coverage accuracy** — `coverage_report()`'s
attempted/never_attempted/126 numbers are computed independently and are
correct — but `cycles_completed` itself is not a meaningful metric today. Not
wired into any report/health/CLI output, so low-impact; worth a real fix
before it's ever surfaced anywhere.

## 5. Soak checklist (next 2-3 days, no code changes during this window)

- [ ] Coverage stays 126/126 (`python main.py samsung discover` /
      `coverage_report()` via `sitemap_product_urls`/`sitemap_traversal_state`)
- [ ] Failed/backoff URLs behave sensibly (`next_eligible_fetch_at` backoff
      scales with `consecutive_failures`; 429→6h min, 403→12h min, 404→24h min)
- [ ] Re-sightings increment in `python main.py report daily` as the same 126
      URLs get re-fetched past `min_refetch_hours=12`
- [ ] Daily report stays clean — no `[MISSING]` expected collectors, no
      out-of-scope runs, `production scope` matches config
- [ ] No rogue collectors appear (`python main.py production scope` — registry
      should only ever show `samsung_us_support_sitemap` RUNNING)
- [ ] `discord status`/`discord test newsroom`/`discord test maintenance` work
      end-to-end against the real configured webhooks
- [ ] No junk devices return (spot-check `python main.py status`,
      manufacturer breakdown stays 100% Samsung)
- [ ] Scheduler survives a restart (`python -m runtime.daemon`, or Task
      Scheduler if installed via `scripts/windows/`)

## 6. Roadmap

**Now → soak**: no further code changes for 2-3 days while the above holds.

**Next development task: Google as OEM #2.** Purpose is architectural, not
coverage — prove `collectors/`, `production_scope()`, the eligibility gate,
run-provenance tagging, and the report/health system generalize to a second
manufacturer without touching core pipeline/entity-resolution code. Concretely
this means: a real `GoogleSupportCollector` (or equivalent) with an actual
validated parser (not the marketing-text-polluted `GenericSupportCollector`
currently disabled in `config.yaml`), a `validation_status` concept for it
(currently Samsung-only via `samsung_sources.yaml` — Google will need either
its own `google_sources.yaml` or a generalized cross-manufacturer registry),
and an update to `production_scope()`/`RUNNABLE_SAMSUNG_SOURCE_IDS` (rename to
something manufacturer-agnostic once a second OEM exists).

**After Google, reassess**: expand to OnePlus/Nothing, or start the native
PySide6 GUI — not before, and not until Google proves the collector
architecture is genuinely reusable.

## 7. Quick reference

```bash
python main.py production scope        # effective config + live registry
python main.py report daily             # IST, production-only by default
python main.py report daily --tz UTC    # UTC boundary instead
python main.py discord status           # both webhook channels, redacted
python main.py discord test newsroom    # synthetic test send, no device rows
python main.py db upgrade               # picks up new columns/tables
```

Config layering: `config/config.yaml` (tracked defaults) →
`config/config.local.yaml` (untracked, optional, deep-merged) →
`DISCORD_WEBHOOK_URL`/`MAINTENANCE_DISCORD_WEBHOOK_URL` env vars (highest
precedence). `.env` at repo root is now loaded automatically by every entry
point (see §3.2).
