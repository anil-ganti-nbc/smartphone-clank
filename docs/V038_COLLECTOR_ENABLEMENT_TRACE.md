# v0.3.8 — Collector Enablement Trace

## Authoritative sources

| Source | Role |
|--------|------|
| `config/config.yaml` → `collectors.*.enabled` | **Authoritative for generic OEM / secondary collectors** |
| `config/samsung_sources.yaml` | Validation status + optional enable for Samsung sources |
| `build_collectors()` | Instantiates only when `enabled` is true |
| Env / Windows YAML | No alternate collector enable list found |

## Default when key missing

```python
if not cfg.get("enabled", False):
    return  # disabled
```

Missing key → **disabled**. Explicit `enabled: true` → **enabled**.

## Pre-repair shipped state (contamination cause)

| Collector | Instantiated | enabled source | validation gate | Expected for Samsung-only soak? |
|-----------|--------------|----------------|-----------------|----------------------------------|
| samsung_us_support_sitemap | yes | config true + LIVE_VALIDATED | yes | **yes** |
| bluetooth_sig | yes | config **true** | none | no |
| google_support | yes | config **true** | none | no |
| oneplus_support | yes | config **true** | none | no |
| nothing_support | yes | config **true** | none | no |
| xiaomi_support | yes | config **true** | none | no |
| samsung_firmware | yes | config **true** | none | no |
| pixel_ota | yes | config **true** | none | no |
| nothing_ota | yes | config **true** | none | no |
| samsung_support | no | config false | n/a | no |
| bis/tdra/imda/fcc | no | config false | n/a | no |

## Post-repair (v0.3.8)

All non-Samsung rows set to `enabled: false` in `config/config.yaml`.  
Only `samsung_us_support_sitemap` remains true.

## Commands that execute the registry

- `python main.py run`
- `python main.py run --once`
- `python -m runtime.daemon`

`python main.py report daily` does **not** run collectors.
