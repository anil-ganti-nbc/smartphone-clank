# Progress — v0.3.8 Production Report Contamination

**Date:** 2026-08-06

## Verdict

- Unexpected collectors scheduled: **YES** (config had OEMs `enabled: true`)
- Daily report trustworthy: **NO** (pre-repair)
- Soak: **VALID_WITH_WARNINGS**
- 152 new devices: **PARTIAL** legitimacy (Samsung expansion + likely junk) — confirm with manufacturer SQL

## Root cause

Shipped `config/config.yaml` enabled google/oneplus/nothing/xiaomi/bluetooth/firmware/OTA collectors. Daemon and `run --once` executed them. Report listed any collector with a metrics row that UTC day and scored health=100 on bare success.

## Repairs applied

1. All non-Samsung collectors set `enabled: false` in config
2. Daily report accepts `enabled_collectors` production scope filter
3. Pipeline sets `meaningful_changes` for new+updated
4. Investigation docs under `docs/V038_*.md`
5. Tests in `tests/test_v038_scope.py`

## Operator must still

```sql
SELECT manufacturer, COUNT(*) FROM devices GROUP BY manufacturer;
```

If non-Samsung rows exist, clean them without wiping Samsung. Do not re-enable OEMs until parsers are strict.
