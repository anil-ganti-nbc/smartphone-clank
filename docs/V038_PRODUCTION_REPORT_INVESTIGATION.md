# v0.3.8 — Production Report Contamination Investigation

**Date:** 2026-08-06  
**Scope:** Code forensics + observed operator report numbers  
**Live production DB:** Not re-uploaded in this session; device manufacturer split must be confirmed on the machine with SQL below.

---

## Verdict

```text
Database pollution:                 LIKELY YES (confirm with manufacturer SQL)
Unexpected collectors scheduled:    YES
152 new devices legitimate:         PARTIAL (Samsung catalog expansion + likely non-Samsung junk)
Daily report trustworthy:           NO (aggregates wrong collectors; inflated “health”)
Soak remains valid:                 VALID_WITH_WARNINGS
```

**Root cause (proven in repo config + code):**

1. `config/config.yaml` ships with **non-Samsung collectors `enabled: true`**.
2. `build_collectors()` honors those flags and schedules them on every `main.py run` / daemon cycle.
3. Daily report sums **all** `collector_run_metrics` for the UTC day with **no** production-scope filter.
4. Health starts at **100** and only penalizes hard failures — empty/junk “success” still scores 100.
5. `meaningful_changes` and `alerts_sent` are **never written** by the pipeline → always 0 in reports.

---

## 1. Why non-Samsung collectors ran

### Configuration (authoritative)

From `config/config.yaml` as shipped in the project tree:

| Collector | `enabled` in config.yaml |
|-----------|--------------------------|
| samsung_us_support_sitemap | **true** |
| bluetooth_sig | **true** |
| google_support | **true** |
| oneplus_support | **true** |
| nothing_support | **true** |
| xiaomi_support | **true** |
| samsung_firmware | **true** |
| pixel_ota | **true** |
| nothing_ota | **true** |
| samsung_support (legacy) | false |
| bis / tdra / imda / fcc | false |

This matches the nine collectors listed in the daily report.

**Note:** During the earlier soak, the operator was instructed to set non-Samsung flags to `false` **locally**. The **repository** config was never permanently flipped. Extracting v0.3.7 over the project would restore `enabled: true` for those collectors.

### Runtime path

```text
python main.py run
  → runtime.daemon / pipeline.run_once
    → build_collectors(settings)
      → add(name) if collectors_cfg[name].enabled is true
```

`add()` uses:

```python
if not cfg.get("enabled", False):  # missing key → disabled
    return
```

Default when the key is **missing** is safe (`False`).  
Default when the key is **present and true** (as in shipped YAML) is **run**.

There is **no** second gate that requires `LIVE_VALIDATED` for generic OEM collectors. Only the Samsung sitemap path checks validation status.

### Windows / invocation

Any of these will execute the full enabled set:

| Invocation | Effect |
|------------|--------|
| `python -m runtime.daemon` (Task Scheduler) | Schedules every enabled collector |
| `python main.py run` | Same registry |
| `python main.py run --once` | Runs all enabled collectors once |
| Daily report task | **Does not** run collectors; only reads metrics |

Installer / health-check scripts do not need to “secretly” run collectors: **config alone is sufficient** once the daemon or `--once` runs.

---

## 2. Were they enabled in production configuration?

**Yes — in the repository `config/config.yaml`.**

If the operator’s live file still has the local soak edits (`enabled: false`), non-Samsung would not run. The report listing nine collectors is strong evidence the **live** config currently has those collectors enabled (or an overwrite restored the repo defaults).

**Action for operator:** open `config\config.yaml` and confirm the `enabled:` lines. They almost certainly match the table above.

---

## 3. What command executed them?

Most likely:

1. **Scheduled daemon** (`-m runtime.daemon`) after config had OEMs enabled — intervals 60–360 minutes would produce multiple non-Samsung runs, **or**
2. **`main.py run --once`** after upgrade (operator validation) — one run per enabled collector near the same timestamp, **or**
3. Combination of both.

**Evidence pattern to confirm on the machine:**

```sql
SELECT collector_name, COUNT(*), MIN(started_at), MAX(started_at), SUM(new_devices)
FROM collector_run_metrics
GROUP BY collector_name
ORDER BY MIN(started_at);
```

- Many rows for `samsung_us_support_sitemap` → scheduled production.
- Exactly one row per other collector, clustered timestamps → manual `--once` or first daemon tick after enable.
- Multiple rows for google/oneplus → daemon kept them scheduled.

---

## 4. Live vs fixture vs historical

Generic support collectors hit real public URLs (Google Store, OnePlus support, etc.). Prior session logs showed live HTTP 200/301/403 responses and junk model strings.

They are **live production metric rows**, not fixture demos — unless a demo wrote into the same DB (demos mostly use in-memory SQLite).

`collector_run_metrics` has **no** `run_mode` / `fixture` column today → report cannot exclude demo/test by flag.

---

## 5–6. Where did 152 new devices come from? Manufacturer mix?

### Arithmetic

```text
Starting (post-clean soak baseline):  15
Reported new_devices (sum of metrics): 152
Ending DB devices:                    167
15 + 152 = 167  →  arithmetic consistent with metrics summation
```

### Samsung catalog expansion (legitimate portion)

Coverage at investigation time:

```text
Valid mobile models: 90
Ever attempted: 120 / 126
```

v0.3.7 raised the fetch budget and enabled oldest-checked-first. Expanding from 15 → ~90 **Samsung** models is expected and legitimate.

### Likely pollution (illegitimate portion)

`167 − ~90 ≈ 77` (order of magnitude) aligns with prior **google_support / oneplus_support** marketing-text entities (`PIXEL 10 PHONE DOCKED…`, `ONEPLUSSHOP`, etc.) observed earlier in this project.

**Must confirm on production DB:**

```sql
SELECT manufacturer, COUNT(*) FROM devices GROUP BY manufacturer ORDER BY 2 DESC;
SELECT manufacturer, model_number FROM devices
WHERE manufacturer != 'samsung'
ORDER BY manufacturer, model_number
LIMIT 50;
```

If non-Samsung count > 0 → **YES pollution**.  
If 100% Samsung → 152 is catalog expansion only (report still wrong about other collectors being “healthy production”).

### Evidence 1:1 with devices

Pipeline creates one evidence row per new device on first resolve; re-sights do not add evidence. Exactly 167/167 matches “one baseline evidence row per device.”

---

## 7–8. Why 152 new devices but 0 meaningful discoveries and 0 alerts?

### Meaningful discoveries = 0 (code bug / gap)

`pipeline.run_collector` sets:

- `ctx.new_devices`
- `ctx.updated_devices`
- `ctx.evidence_added`

It **never** sets `ctx.meaningful_changes`.

Daily report:

```python
"meaningful_discoveries": sum(r.meaningful_changes for r in runs)
```

→ always **0**, even for real new Samsung models.

This is **not** proof that discoveries were “baseline suppressed.” The counter is simply unwired.

### Alerts sent = 0 (metrics gap + possible no webhook)

Pipeline calls `alerter.alert_new_device(...)` on `is_new`, but **does not** increment `ctx.alerts_sent`.

Daily report sums `alerts_sent` from metrics → **0** regardless of Discord success/failure.

Additionally, if `DISCORD_WEBHOOK_URL` is unset, alerts fail quietly.

**Baseline import suppression** is not implemented as a stored novelty flag that zeros these counters for sitemap catalog expansion. New sitemap models are treated as `is_new=True` devices.

---

## 9. Health = 100 for empty / junk collectors

`health_score()`:

1. Starts at **100**
2. Deducts only for blocked / failed / partial / high failure rate / parser failures / candidate collapse vs baseline / HTTP spikes
3. **Does not** check:
   - whether collector is enabled in production config
   - validation status (`LIVE_VALIDATED` vs unknown)
   - whether candidates are real model IDs
   - whether the collector is “expected” for Samsung-only soak

A single `status=success` run with 0 or garbage candidates → **health 100**.

`daily_report` builds `by_collector` from **whatever names appear in that day’s metrics**, not from the enabled production set.

---

## 10. Report aggregation window

```python
start = datetime(day.year, day.month, day.day)  # UTC midnight
end = start + timedelta(days=1)
runs = query.filter(started_at >= start, started_at < end)
```

| Field | Meaning |
|-------|---------|
| Collectors run | Distinct `collector_name` in that UTC day |
| Total runs | Row count in that window |
| New devices | **Sum** of `new_devices` over those rows (can exceed net DB growth if recounted across overlapping logic — here matches 152) |
| DB devices | **Current** total table count (not delta) |

No filters for: production mode, enabled config, validation status, Samsung-only policy.

Timezone: **UTC**, not IST — boundary may not match operator’s calendar day in India.

---

## Hypothesis tests

| Hypothesis | Result |
|------------|--------|
| A — one-shot ran all collectors once | **Plausible**; confirm with per-collector run counts |
| B — build_collectors defaults enabled | **Partial**: missing key → false; **shipped YAML sets true** |
| C — report includes demos | **Unlikely** primary cause; live HTTP was observed before |
| D — all 152 from Samsung only | **Possible majority**; confirm manufacturer SQL |
| E — report right about new devices, wrong about health | **YES** for health; new_devices sum is internally consistent |

---

## Root causes (ranked)

1. **Shipped `config/config.yaml` enables non-Samsung collectors** while product policy is Samsung-only soak.
2. **No validation gate** for generic OEM collectors in `build_collectors`.
3. **Daily report** treats any metric row as production health/scope.
4. **Health score** = “didn’t throw / status success,” not “validated production collector.”
5. **`meaningful_changes` / `alerts_sent` never populated** → report fields are dead.

---

## Minimal repairs (after investigation)

1. Set all non-Samsung collectors to `enabled: false` in `config/config.yaml`.
2. Report: only score/list collectors that are enabled in current config (or mark others `out_of_scope`).
3. Health: do not assign Healthy/100 to collectors that are disabled or lack validation status when evaluating production reports.
4. Pipeline: set `meaningful_changes` when `new_c > 0` or true page-change updates; increment `alerts_sent` when alerter returns success.
5. Do **not** delete Samsung devices; optional later cleanup of non-Samsung rows after manufacturer SQL confirms pollution.
6. Tests for enable defaults and report scope.

---

## Operator SQL checklist (run on production DB)

```sql
-- Manufacturer mix
SELECT manufacturer, COUNT(*) FROM devices GROUP BY manufacturer ORDER BY 2 DESC;

-- Non-Samsung samples
SELECT manufacturer, model_number, first_seen FROM devices
WHERE lower(manufacturer) != 'samsung' ORDER BY first_seen DESC LIMIT 40;

-- Evidence by source
SELECT source, COUNT(*) FROM evidence GROUP BY source ORDER BY 2 DESC;

-- Runs by collector
SELECT collector_name, COUNT(*), SUM(new_devices), MIN(started_at), MAX(started_at)
FROM collector_run_metrics GROUP BY collector_name ORDER BY 2 DESC;

-- Today UTC window (match report)
SELECT collector_name, status, new_devices, candidates_found, started_at
FROM collector_run_metrics
WHERE started_at >= date('now') AND started_at < date('now', '+1 day')
ORDER BY started_at;
```

---

## Soak validity

**VALID_WITH_WARNINGS**

- Samsung sitemap coverage ~95% and real `SM-*` growth remain valuable.
- Report contamination and possible non-Samsung device pollution reduce trust in “operational health” totals until config is locked and DB manufacturer mix is verified.
- Do not call the full multi-collector health table production-accurate.

---

## Residual risks

- Operator may still have polluted rows until cleanup after SQL confirmation.
- UTC vs IST report boundary.
- No `run_mode` column → future demos can still pollute if pointed at production DB.
- Extracting zips can overwrite local `config.yaml` soak edits.

---

*Investigation based on repository code and operator-reported numbers. Manufacturer split requires live SQL confirmation.*
