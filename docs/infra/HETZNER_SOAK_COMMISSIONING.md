# Hetzner Soak Commissioning — Verification Report

**Date: 2026-08-11. Verdict: `MIGRATION_INCOMPLETE`.**

This document verifies (or refutes) the claim that Smartphone Intel Clank's
8-OEM production system has been migrated to Hetzner. It does not perform
new migration work — per the mission's own framing, "if migration has
already occurred, VERIFY it." The finding below is that it has not.

## Executive summary

There is no live Hetzner production deployment to verify. What exists is
**Tier D architecture-prep work** (`ai/handoff/CLOUD_READINESS_CHECKLIST.md`,
explicitly scoped as "planning artifacts, not working infrastructure") plus
a later **scheduler-migration design** (`docs/SCHEDULER_MIGRATION.md`) that
added a `Dockerfile`/`docker-compose.staging.yml` and a `runtime/run_once.py`
one-shot entry point. Neither phase deployed anything to an actual remote
Hetzner server reachable from this session:

- No SSH config, host address, or credential reference to a Hetzner machine
  exists anywhere in the repository (`~/.ssh/config` does not exist; no
  script, doc, or config file names an IP/hostname).
- `docs/SCHEDULER_MIGRATION.md` cites `ai/handoff/HETZNER_DEPLOYMENT.md` as
  the source for its `flock` overlap-test proof — **that file does not
  exist** in the repository. The claim is unverifiable and the referenced
  evidence is missing.
- No Docker images, containers, or volumes for this project exist on this
  machine (`docker images` / `docker ps -a` / `docker volume ls`, all
  filtered for `clank`, return empty) — so even the local Docker Compose
  path described in that doc is not currently running or built here.
- `docker-compose.staging.yml` itself documents that its target is a
  **fresh, isolated named volume** (`smartphone_clank_staging_data`), not
  the Windows production database — by design, per its own comment: "the
  Windows local database was not copied... not a promotion of existing
  production state." Even if that container had been run at some point, it
  was never the authoritative production database.

**There is exactly one production system today, and it runs on Windows.**

## 1. The two hosts, as they actually stand

### WINDOWS (`smartphone-clank-prod`) — the only production host

| Property | Value |
|---|---|
| Tree path | `C:\Users\anil\Desktop\smartphone-clank-prod` |
| Git branch | `feature/wave1-expansion` |
| Git HEAD | `ddfc2a36b2d043bf0a3303093d96e495483520ce` |
| Working-tree status | **Dirty** — 19 tracked files modified relative to that commit (1757 insertions / 284 deletions across `alerts/`, `collectors/wave1/`, `dashboard/`, `database/`, `main.py`, `pipeline.py`, `runtime/`, `config/`, `scripts/windows/`, `HANDOFF.md`, `tests/test_metrics.py`) plus one untracked file (`PRODUCTION_TREE.txt`) |
| Python version | 3.14.6 (`.venv`, no `pytest` installed — documented gap, see §18) |
| venv path | `.venv\Scripts\python.exe` |
| Database path | `data/clank.db` |
| Database size | 1,826,816 bytes (as of 2026-08-11 01:12) |
| Schema revision | `0007_wave1_baseline_state` (== head) |
| Production config source | `config/config.yaml` (this tree, file-copied from dev, not git-tracked as a deploy step) |
| `.env` location | `smartphone-clank-prod/.env` (present, git-ignored) |
| Runtime mechanism | `runtime/daemon.py` (`BlockingScheduler`), launched via Windows Task Scheduler / `scripts/windows/start-runtime.ps1` |
| Scheduler mechanism | In-process APScheduler, per-collector `interval_minutes` from `config.yaml` |
| Dashboard mechanism | `dashboard/app.py`, started via `start-dashboard.ps1` |
| Backup mechanism | `scripts/windows/backup-database.ps1` + ad hoc `cp` before risky operations, into `data/backups/` |

### HETZNER — not a production host; not verifiably running anything

| Property | Value |
|---|---|
| Repository/tree path | **Unknown — no path, host, or credential is documented anywhere in this repo or this machine's SSH config.** |
| Deployment artifacts that exist | `Dockerfile`, `docker-compose.staging.yml` (promoted from `.draft` per `docs/SCHEDULER_MIGRATION.md`, 2026-08-10) |
| Actually built/run anywhere reachable from this session | **No** — zero local Docker images/containers/volumes for this project |
| Database | N/A — compose file targets an isolated fresh named volume, never the production DB, by explicit design |
| Runtime mechanism (as designed, not deployed) | `runtime/run_once.py`, intended to be triggered externally (cron/systemd timer + `flock`) per `docs/SCHEDULER_MIGRATION.md` |
| `.env`/webhook credentials | not_configured (no environment or secret material for a Hetzner host exists here to check) |

## 2. Which host is actually production

Empirically, not by assumption:

- **Windows daemon**: running. PIDs 43276 (daemon) + 39304 (child), and
  45356 (dashboard) + 41392 (child), all under
  `smartphone-clank-prod\.venv\Scripts\python.exe` — confirmed via process
  inspection.
- **Hetzner daemon**: not applicable — no reachable host exists to check.
- **DB receiving current `collector_run`/device rows**: `smartphone-clank-prod\data\clank.db` only — verified via `PRAGMA integrity_check` = `ok`, live counts below.
- **Scheduled execution owner**: Windows Task Scheduler, targeting the `-prod` tree exclusively (per `docs/infra/ISOLATION_AUDIT.md`, unchanged this check).
- **Could both hosts currently be collecting?** No — there is no second live collector process anywhere, on Windows or otherwise, against a divergent database. **No split-brain condition exists.**

## 3. Repository / revision verification

This is the actual blocker, not a formality.

- `origin/main` HEAD: `1b0a183` ("Merge pull request #1 from
  anil-ganti-nbc/feature/cloud-migration-oneshot") — a **different lineage**
  from the production code entirely; it does not contain Wave 1 or Wave 2
  OEM work.
- `origin/feature/wave1-expansion` HEAD: `ddfc2a3` ("Add Wave 1 candidate
  OEM collectors (Google, OnePlus, Nothing, Xiaomi) behind a hard-isolated
  staging environment") — this **is** pushed and matches the local
  checked-out branch exactly. But it predates every promotion after that
  point.
- **Everything after that commit — Google/Nothing/OnePlus/Motorola/Honor/Oppo/Realme production promotion, the alert-semantics rewrite, the production-scope validator, the IST-midnight test fix, all of `HANDOFF.md`'s Wave 1/Wave 2 history — exists only as uncommitted working-tree modifications on both the dev and prod trees on this one Windows machine.** Confirmed identically on both trees (`git status --short`, `git diff --stat`).
- Consequently: `PRODUCTION_OEM_SCOPE` with Honor/Oppo/Realme, the
  production-scope validator, `dropped_out_of_scope` accounting, and the
  deterministic daily-report fix are all real and running — but **not
  recoverable from GitHub.** If this Windows machine were lost today, the
  production system as it currently exists could not be reconstructed from
  the remote.

**This is a confirmed BLOCKER per the mission's own Phase 17/20 criteria** — not a stylistic gap. `HETZNER_SOAK_COMMISSIONED` explicitly requires "GitHub contains recoverable source," which is false today.

## 4–5. Database authority / migration verification

Not applicable as a migration step — there is nothing on the far side to migrate to. For the record, the authoritative production database's current state:

```text
PRAGMA integrity_check: ok
Schema revision: 0007_wave1_baseline_state (== head)
Devices by manufacturer:
  google    7
  honor    22
  motorola 15
  nothing   9
  oneplus  16
  oppo     73
  realme   22
  samsung  97
  ---------------
  total   261
Total evidence rows: 277
```

This matches the fleet audit recorded at soak-start (`HANDOFF.md` §12e) exactly — no drift since 2026-08-11 01:18.

## 6. Configuration verification (Windows, the only live host)

`python main.py production validate` (prod tree):

```text
OEM        approved configured adapter enabled scheduled status
google          YES        YES     YES     YES       YES OK
honor           YES        YES     YES     YES       YES OK
motorola        YES        YES     YES     YES       YES OK
nothing         YES        YES     YES     YES       YES OK
oneplus         YES        YES     YES     YES       YES OK
oppo            YES        YES     YES     YES       YES OK
realme          YES        YES     YES     YES       YES OK
xiaomi           NO        YES     YES      NO        NO OK

Production scope: OK — no mismatches
```

Exactly the intended 8 OEMs (Samsung via its own registry + the 7 above); Vivo/Xiaomi/Redmi/Poco/ASUS/Sony correctly absent or inert. **PASS.**

## 7. Secrets / Discord

Prod tree `.env` (values not printed, keys and presence only):

```text
newsroom webhook: configured
maintenance webhook: configured
```

`.env` is `.gitignore`d in both trees (confirmed via `git check-ignore -v .env`) — never committed. No synthetic Discord test was sent; not necessary since transport was already exercised during the Oppo/Realme canaries.

## 8–15. Linux runtime / scheduling / dashboard / logging / backups / health / first cloud cycle / reboot test

**Not performed.** All of these presuppose a reachable Hetzner host. None exists to test against. Attempting to fabricate results for a server that isn't there would violate the mission's own evidentiary standard ("prove it," "establish current truth from the repository and both hosts" — the second host, as verified, does not currently exist in any checkable form).

## 16. Windows decommission / standby

**Not performed, correctly.** Per Phase 16's own logic, this step is
conditional on Hetzner first being "proven authoritative." Since it isn't,
Windows remains — correctly — the sole production runtime. No production
scheduled task was disabled.

## 17. GitHub loose end

See §3. `origin/main` and `origin/feature/wave1-expansion` are both real,
clean, pushed branches — but neither contains the current production
system. This is flagged, not fixed, per the mission's explicit instruction
not to rewrite history or invent a release process; committing/pushing the
current working tree is a separate, deliberate decision for the operator to
make (it touches `HANDOFF.md`, config, and 18 source files across two
trees) and is not done automatically as part of this verification pass.

## 18. Final test suite

`smartphone-clank-prod\.venv` has no `pytest` installed — a pre-existing,
already-documented gap (`ai/handoff/CLOUD_READINESS_BLOCKERS.md` item 5).
Ran the canonical suite against the equivalent dev-tree working state
(byte-identical source, same uncommitted diff, system-installed Python 3.14.6
with pytest 8.4.2 on PATH):

```text
PYTHONPATH=. python -m pytest -q
181 passed, 954 warnings in 43.35s
```

Matches the known-good baseline from the soak declaration exactly. **0 failed.**

## 19. Residual risks

1. **GitHub does not contain recoverable production source** (§3/§17) — the single most important finding of this verification. Recommended next action (operator decision, not performed here): commit the current working-tree state on both trees, push to a branch, open a PR into `main`, tag the soak-start revision.
2. **No off-host backup exists** — `data/backups/` lives on the same Windows disk as `data/clank.db`. No NAS/off-host replication (explicitly out of scope, consistent with the mission's own §12 instruction not to build this here).
3. **`ai/handoff/HETZNER_DEPLOYMENT.md` is a dangling reference** — `docs/SCHEDULER_MIGRATION.md` cites it as proof of a locking test that cannot currently be verified. Either the file was never committed or the claim needs to be re-substantiated before it's relied on.
4. **No pytest in the production venv** — pre-existing, documented, low-impact (canonical suite is run from the dev tree/system Python by convention).

## 20. Final verdict

```text
MIGRATION_INCOMPLETE
```

Windows is unambiguously the sole production system today: correct code
(uncommitted, but present and running), correct database (261 devices, 277
evidence rows, integrity ok, schema at head), `production validate` PASS,
exactly one daemon and one dashboard, Discord configured, canonical suite
green. No split-brain risk exists because there is nothing else running.
The gap is entirely on the "has Hetzner migration happened" question: it
has not — only architecture-prep and unbuilt deployment scaffolding exist
for that host, and the current production source is not recoverable from
GitHub. Recommend treating an actual Hetzner deployment as new,
deliberately-scoped work with real target-host access, not something to be
assumed already in progress.

## 21. Freeze

Per the mission's own terms, no new OEM/Vivo/Xiaomi/schema/GUI/AI/ranking
work follows from this verification. The only follow-up this report
recommends is the GitHub-recoverability gap in §3 — an operator decision,
not undertaken here.
