# Production Readiness Verdict — Smartphone Intel Clank v0.3.4

**Date:** 2026-08-02  
**Reviewer role:** Principal engineer (hostile review)  
**Scope:** Single-operator, localhost/SQLite, Samsung-first intelligence

---

## Scores

| Subsystem | Score | Justification |
|-----------|------:|---------------|
| Discovery (Samsung sitemap) | **8.8** | Proven live sitemap → product URLs → models. Not unreleased-device magic. |
| Entity resolution | **8.5** | Dedup works; regional/family safeguards present; merge UI incomplete. |
| Confidence / ledger | **9.0** | Central service + AST enforcement; residual dual-writer risk low. |
| Knowledge enrichment | **8.0** | Deterministic YAML; conservative (null over guess). |
| Support-page diffing | **8.2** | Multi-hash + classification solid in fixtures. |
| Observability / metrics | **8.5** | Schema + health + regression + daily report; not fully wired into all collectors. |
| Dashboard | **7.5** | Useful read-only newsroom; no auth; limited analyst actions. |
| Scheduler / adaptive polling | **7.0** | Logic present; unattended soak not proven in CI. |
| Migrations | **7.8** | Explicit Alembic revisions exist; dual system remains. |
| Security | **7.5** | Adequate for localhost; not internet-safe. |
| Testing | **8.0** | Good fixture coverage on critical paths; live HTTP not CI-gated. |
| Maintainability | **8.2** | Single-process Python; some dead/stub collectors cleaned. |
| Documentation | **8.5** | Ops, audits, limitations honest. |

### Overall: **Production Ready With Conditions**

Not “ship to unattended cloud.”  
Yes for **supervised single-operator production** monitoring Samsung public support surfaces with Discord alerts.

---

## Conditions for production use

1. Keep dashboard on **127.0.0.1** (or behind authenticated reverse proxy you own).
2. Leave **BIS/TDRA/IMDA/FCC disabled** until each has LIVE_VALIDATED parsers.
3. Prefer **sitemap discovery** as the Samsung discovery path; treat slug support collector as secondary monitoring.
4. Run **daily report** and inspect health scores; investigate score < 75.
5. **Backup SQLite** before migrations and confidence rebuild --all.
6. Wire **MetricsRecorder.finish()** into every live collector path before claiming full observability.
7. Do not market “detects unreleased phones before anyone” — only published-index discovery is proven.

---

## Remaining risks

- OEM HTML/structure changes → parser_empty / candidate collapse (mitigated by metrics regression).
- Unbounded snapshot growth.
- Operator enables skeleton collectors and trusts empty runs as “all clear.”
- Confidence drift if a future code path mutates confidence outside the service.

## Recommended monitoring

- `/metrics` health scores daily
- `python main.py report daily`
- Maintenance webhook for REGRESSION notes
- Disk size of SQLite file weekly

## Highest-ROI future work

1. Integrate MetricsRecorder into BaseCollector.collect lifecycle.
2. Merge `models_v03` into `models.py`; drop dual migration runner after Alembic adopt is tested once.
3. ETag/Last-Modified on sitemap and product pages.
4. Snapshot retention policy (keep last N per URL).

## Explicitly NOT worth building yet

- Other OEMs until Samsung path runs weeks cleanly
- AI correlation
- Distributed workers / queues
- Public internet dashboard
- Mobile apps
- Graph databases

---

## Runtime validation (this review)

| Check | Result |
|-------|--------|
| Confidence write AST audit | 0 illegal production writes |
| Metrics unit tests | Pass |
| Discovery unit tests | Pass (when deps installed) |
| Long-run simulation | Produces health differentiation + daily report |
| Skeleton collectors | Disabled in config + unregistered |

---

**Sign-off:** Approve for **supervised production** under the conditions above. Reject for **unattended multi-tenant or internet-facing** deployment without further security and soak work.
