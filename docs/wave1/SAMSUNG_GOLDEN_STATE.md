# Samsung Golden-State Report — pre–Wave 1 baseline

Captured: 2026-08-10, from `data/clank.db` (local/production copy).
Backup taken before any Wave 1 work: `data/backups/clank_pre_wave1_20260810_140158.db`.

This is the reference point Wave 1 must not regress. Re-run the queries below
after any shared-core change and diff against these numbers.

## Device / evidence counts

```text
Total devices:            97
Devices by manufacturer:  samsung: 97   (100% — zero non-Samsung rows)
Evidence rows:            98
Evidence by source:       samsung_us_support_sitemap: 98
Rejected candidates:      0
```

## Sitemap traversal state (`sitemap_traversal_state`, source_id=samsung_us_support_sitemap)

```text
total_eligible_urls:        126
cursor_position:            0
cycles_completed:           55
strategy:                   oldest_checked_first
last_completed_cycle_at:    2026-08-10 08:31:40
```

## Collector runs

```text
collector_runs rows:        118  (all samsung_us_support_sitemap / samsung_support family)
```

## Production scope enforcement (already in place, verified in code)

`collectors/__init__.py::production_scope()`:
- Default `production.samsung_only = True` (config/config.yaml).
- Scope hard-coded to `{"samsung_us_support_sitemap"}` plus any Samsung source that
  is both `LIVE_VALIDATED` in `config/samsung_sources.yaml` **and** in
  `RUNNABLE_SAMSUNG_SOURCE_IDS`.
- Non-Samsung collectors cannot enter production scope regardless of `enabled:` in
  `config.yaml` — confirmed by `tests/test_v038_scope.py` and `tests/test_production_scope.py`,
  both passing in the canonical suite (see below).
- This is the mechanism that prevented the August 5 incident from recurring even
  though `config/config.yaml` still ships several OEM collectors with commented-out
  `enabled: false` flags (defense in depth: config *and* code-level scope gate).

## Canonical test baseline

```bash
PYTHONPATH=. python -m pytest -q
```

```text
81 passed, 0 failed, 0 skipped, 0 xfailed
```

(One stale test fixed as maintenance: `tests/test_change_detection.py` imported
`extract_hashes`/`compare_hashes`, which were renamed to `extract_fingerprint`/
`compare_fingerprints` in a prior refactor. Updated to the current API — no
behavior change.)

## Regression policy

Any Wave 1 change to shared code (`entity_resolution/`, `alerts/`, `database/`,
`pipeline.py`, `collectors/__init__.py`, `observability/`) must be followed by:

1. `PYTHONPATH=. python -m pytest -q` → must stay at 81+ passed, 0 failed.
2. Re-run the SQL above against `data/clank.db` → Samsung counts must be unchanged
   (Wave 1 work happens against `data/clank-staging.db`, never this file).
