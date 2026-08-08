# Troubleshooting

| Symptom | Check |
|---------|-------|
| No new devices | Did collectors run? `report daily` runs_24h. Health score. |
| Health score low | `/metrics` factors; REGRESSION notes on last run |
| Candidate count 0 with HTTP 200 | Parser breakage — update selectors; do not disable validation |
| Source BLOCKED | Geo/WAF; keep disabled; re-validate from allowed egress |
| Confidence drift | `confidence verify`; rebuild only with explicit command + backup |
| Dashboard empty | Point at correct DB URL; run discovery or demo populate |
| Migration fails | Restore backup; inspect schema_version / alembic_version |

See also `docs/operations.md`.
