# Testing Review — v0.3.4

## Suites

| Test module | Focus |
|-------------|-------|
| `test_confidence_write_enforcement.py` | AST ban on illegal confidence writes |
| `test_v031_discovery.py` | Sitemap parse, polling, ledger, migrations |
| `test_metrics.py` | Run metrics, health, regression, daily report |
| `test_change_detection.py` | Multi-hash / meaningful change |
| `test_samsung_v03.py` | Model validator, ledger |
| `test_entity_resolution.py` | Dedup devices |
| `test_knowledge.py` | Enrichment rules |
| `test_decay.py` | Evidence weight decay |
| `test_aliases_timeline.py` | Aliases / timeline |
| `test_support_diff.py` | Support page diff pipeline |

## Gaps

- No automated browser test of dashboard templates (smoke TestClient only).
- Certification collectors untested (they return empty by design).
- No CI matrix for PostgreSQL.
- Live Samsung tests are manual / dry-run, not CI-gated.

## Flaky risks

- Live HTTP in unit tests — prefer fixtures (`use_fixture_sitemap=True`).
- Time-dependent decay tests — freeze time where possible.

## Coverage philosophy

Prefer deterministic fixture tests over high % coverage of network code.
