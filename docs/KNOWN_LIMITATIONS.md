# Known Limitations

1. **Sitemap discovery only sees published support pages** — unreleased unlisted devices will not appear.
2. **Certification collectors (BIS/TDRA/IMDA/FCC)** are skeletons; disabled by default as of v0.3.4.
3. **India/UK Samsung support** often HTTP 403 from non-local egress.
4. **Release state defaults to unknown** — novelty ≠ upcoming.
5. **Dashboard is localhost read-mostly** — not multi-user.
6. **Dual migration tooling** until Alembic adoption is universal.
7. **Snapshot pruning not implemented** — disk growth operator responsibility.
8. **Metrics must be wired into collector finish()** for complete observability.
9. **No PostgreSQL production validation** in this environment.
10. **Firmware/OTA collectors** are best-effort and may break when OEM pages change.
