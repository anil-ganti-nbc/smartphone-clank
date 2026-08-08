# Technical Debt Register — v0.3.4

| Severity | Files | Reason | Suggested fix | Fixed? |
|----------|-------|--------|---------------|--------|
| **High** | `collectors/bis.py`, `tdra.py`, `imda.py`, `fcc.py` | Always return `[]` but were `enabled: true` in config — false “coverage” | Disable in config; remove from registry; keep files as documented skeletons | **Yes** (disabled + unregistered) |
| **High** | `collectors/samsung_support.py` vs `collectors/samsung/sitemap_discovery.py` | Two Samsung paths; older targets India/UK pages that 403 | Prefer sitemap discovery; mark owners/support as monitoring only | Partial — both exist; config still enables samsung_support |
| **Medium** | `database/models.py` + `models_v03.py` | Split model definitions across two modules | Merge into single `models.py` | No |
| **Medium** | `database/migrations_ordered.py` + `alembic/` | Dual migration systems | Alembic primary; delete ordered runner after adopt path proven | No — both retained |
| **Medium** | `dashboard/app.py` `Base.metadata.create_all` | Demo path can paper over missing migrations | Require alembic upgrade for non-demo | Partial — comment present |
| **Low** | `normalizers/` | Empty package reserved for future | Delete or implement one real normalizer | Deleted content already minimal |
| **Low** | `collectors/support/` | Empty directory | Remove | **Yes** |
| **Low** | `migrations/versions/` (non-alembic) | Empty leftover | Remove | **Yes** |
| **Low** | `main.py` | Accumulated CLI surface; some commands overlap | Split CLI modules when >1k lines | No |
| **Low** | Placeholder comment in `main.py` stats | Misleading comment | Cleaned in review if still present | Check |
| **Info** | Multiple `httpx.Client` create/destroy | Per-request clients in collectors | Acceptable for politeness; shared client optional | No |

## Intentionally retained

- Skeleton cert collectors remain on disk for future work but **must not** be enabled until they parse real data.
- Dual Samsung collectors: sitemap is discovery; support is monitoring of known entry points.
