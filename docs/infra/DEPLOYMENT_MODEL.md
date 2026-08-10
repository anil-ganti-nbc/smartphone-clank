# Deployment Model

The rule this project now operates under:

```text
development
  ↓
tests
  ↓
review
  ↓
release/deploy
  ↓
explicit migration if required
  ↓
production restart
```

not:

```text
edit a Python file
  ↓
live scheduled process imports it
  ↓
production changes
```

The second pattern is exactly what caused the `wave1_baseline_state` leak
(traced in full in `docs/infra/MIGRATION_AUDIT.md` to `main.py db upgrade`
using `create_all()` as its actual implementation — a real command, run
against a live-edited tree, not a phantom process).

## Current topology (as of this phase — split executed)

```text
GITHUB                LOCAL — two trees, physically separated       HETZNER / CLOUD
  canonical source      smartphone-clank-prod                          not yet targeted
  repository              - frozen, Task Scheduler target only         by any Wave 1 OEM
                          - live daemon runs here exclusively          (explicitly out of
                          - production DB: data/clank.db                scope this phase)
                          - has PRODUCTION_TREE.txt

                       smartphone-clank (dev)
                          - all Claude Code editing happens here
                          - staging DB: data/clank-staging.db
                          - has DEVELOPMENT_TREE.txt
                          - no Task Scheduler task references it
```

**Local topology is now two physically separated trees.** The split was
executed with explicit operator confirmation — full command-by-command log
in `docs/infra/PROD_DEV_SPLIT.md` §"Execution status". Two independent
pre-existing bugs (duplicate daemon spawning via `start-runtime.ps1`/
`start-dashboard.ps1` never recording their PID) were found and fixed during
execution, not just documented.

## What was achieved

All four of the mission's goals:

| Goal | Status |
|---|---|
| Make explicit migrations the only schema authority | **Done** — see `docs/infra/MIGRATION_AUDIT.md`, `docs/infra/PRODUCTION_RUNTIME.md` |
| Prevent `create_all()` from silently mutating production schema | **Done** — production/daemon/cloud-one-shot entry points refuse instead of mutating |
| Separate production code from active development code | **Done** — see `docs/infra/PROD_DEV_SPLIT.md` |
| Prove the live scheduler executes only the frozen production tree | **Done** — verified via process command-line inspection, repointed-task readback, and the development-isolation marker-file proof (`ISOLATION_AUDIT.md`) |

The schema-safety half of this phase's mandate was built to hold regardless
of directory topology (a migration-gated production process is safer than an
ungated one whether it runs from a shared tree or a frozen one) — and now
both halves are in place together.

## GitHub / Hetzner relationship (unchanged this phase)

No Hetzner config was touched. No NAS work was done. The intended eventual
path (`GitHub → tested commit → Hetzner production`) is unchanged in
principle; this phase's local schema-authority work directly benefits that
path (a Hetzner deployment would go through `db init`/`db adopt` +
`ensure_schema_or_refuse()` the same way this local production tree now
does), but no Hetzner-specific work was performed.
