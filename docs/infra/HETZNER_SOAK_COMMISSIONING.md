# Hetzner Soak Commissioning — Executed Migration Report

**Date: 2026-08-10/11. Verdict: `HETZNER_SOAK_COMMISSIONED`.**

Supersedes the 2026-08-11 verification-only version of this document
(preserved below in §Appendix), which found `MIGRATION_INCOMPLETE` because
no Hetzner deployment existed yet — only Tier D architecture-prep and an
unbuilt Docker/Compose scaffold. This document records the actual executed
migration that followed the GitHub checkpoint (`soak-baseline-2026-08-11`).

## Host

`root@204.168.142.1` (SSH key `hetzner_clank_fleet`), Hetzner Helsinki,
hostname `ubuntu-4gb-hel1-1`, Ubuntu 24.04.4 LTS, kernel 6.8.0-137-generic,
4GB RAM, 38GB disk (29GB free before deployment). Timezone `Etc/UTC`. This
is a **shared multi-project fleet host** — it already runs
korean-tech-wire, oem-radar, free-game-tracker, feature-phone-clank,
smartwatch-clank, watch-clank, semiconductor-intelligence, and
chinese-tech-wire, each isolated under its own system user or the shared
`deploy` user. Smartphone Clank now follows the more production-grade of
the two existing conventions on this host (dedicated system user under
`/opt/`, matching `korean-tech-wire`) rather than the `deploy`-user
"experimental" pattern.

**Pre-existing artifact found and accounted for**: `/home/deploy/staging/smartphone-clank`,
a Docker-based staging deployment from the earlier Tier D/scheduler-migration
work, built from `.deployed-id` = `1b0a183` (`origin/main`'s old
cloud-migration-oneshot lineage — confirmed to predate all Wave 1/2 OEM
work, consistent with the verification-only report's finding). It ran
hourly via a `deploy` crontab entry against an **isolated fresh Docker
volume**, never production data. That cron entry has been commented out
(not deleted) to avoid confusion/log noise alongside the real production
service; the staging tree and Docker volume/image are left in place,
untouched.

## Deployment model

Git checkout + Python venv + systemd, per the mission's explicit preference
and matching `korean-tech-wire`'s existing convention. **No Docker was
introduced** despite the pre-existing `docker-compose.staging.yml` scaffold
— it remains exactly what it was (staging-only, untouched).

| Item | Value |
|---|---|
| Application path | `/opt/smartphone-clank` |
| System user | `smartphone-clank` (dedicated, `nologin`, uid 996) |
| venv | `/opt/smartphone-clank/.venv` (Python 3.12.3) |
| Production DB | `/opt/smartphone-clank/data/clank.db` |
| Secrets | `/opt/smartphone-clank/.env` (mode 600, owned by `smartphone-clank`, git-ignored) |
| Backups | `/opt/smartphone-clank/data/backups/` (14-day bounded retention) |
| Logs | `journalctl -u smartphone-clank.service` / `-u smartphone-clank-dashboard.service` (systemd-managed, bounded — 43.5M on-disk before this deployment, no custom logging built) |
| systemd units | `smartphone-clank.service` (daemon), `smartphone-clank-dashboard.service` (dashboard), `smartphone-clank-backup.service`+`.timer` (daily 02:30 UTC backup) |
| Restart policy | `Restart=on-failure`, `RestartSec=30` |

## Deployed source

Cloned `feature/wave1-expansion` from GitHub (not copied from the mutable
Windows tree). Final deployed SHA: **`83630c4`**.

Two real, previously-invisible bugs were found and fixed during this phase
— both **committed to GitHub first**, deployed only after, per the
mission's explicit rule against uncommitted Hetzner-only patches:

1. **`requirements.txt` never declared `alembic`** (Windows had it installed
   out-of-band since schema-authority work landed). A fresh Linux checkout
   failed `tests/wave1/test_schema_authority.py` at collection. Fixed in
   commit `46f356b`.
2. **`.gitignore`'s unanchored `data/` rule also matched `knowledge/data/`**,
   silently excluding tracked reference YAML (`manufacturers.yaml`,
   `codenames.yaml`, `samsung_model_rules.yaml`) from every commit made so
   far. A fresh checkout was missing static rules data that Samsung
   category classification and knowledge enrichment depend on — surfaced as
   7 test failures (`test_samsung_v03.py`, `test_knowledge.py`) that never
   failed on Windows because the untracked local copy was always present
   there. Fixed in commit `83630c4` (anchored to `/data/`, added the 3
   files).

Both fixes were synced back to the Windows dev and frozen-prod trees to
keep all three copies (dev, prod, Hetzner) byte-identical at the
application-source level.

## Canonical test suite

**181 passed, 0 failed** on native Linux (Hetzner), exact match to Windows.
(Two interim runs failed — 1 and then 7 tests — purely due to the two gaps
above; both are now closed and the fix is permanent, not Hetzner-local.)

## Secrets

Newsroom webhook: **configured**. Maintenance webhook: **configured**.
Transferred directly host-to-host over the SSH pipe (`grep ... | ssh ...
"cat > ..."`) — values were never echoed into any command output or this
session's visible transcript at any point.

## Database migration

Windows remained authoritative through two snapshot/verify cycles:

1. **Validation snapshot** (while Windows daemon was still running, taken
   via SQLite's backup API — not a raw file copy): SHA-256
   `cf780aed6533746f87a36673739935436d1342efad67ece1a396dbdb4961bc3e`,
   1,826,816 bytes. Transferred via `scp`, checksum re-verified identical on
   arrival, `PRAGMA integrity_check` = `ok`, all invariants
   (devices=261, evidence=277, collector_runs=132, webhook_deliveries=140,
   rejected_candidates=1575, alerts=129, wave1_baseline_state=7, per-OEM
   device counts) matched exactly. Used for the Phase 8 controlled
   validation cycle only.
2. **Final cutover snapshot** (taken immediately after the Windows daemon
   was cleanly stopped): **identical SHA-256** to the validation snapshot
   — proof zero writes occurred on Windows between the two snapshots.
   Transferred, re-verified, installed as the live production DB.

Schema revision on both sides: `0007_wave1_baseline_state` (== head).

## Controlled validation cycle (pre-cutover)

Ran the daemon's own real startup pass (all 8 collectors, staggered,
5–160s apart — the actual production invocation mechanism, not a
synthetic one-shot) against the validation snapshot, then stopped it
cleanly with SIGTERM. Result, exactly as the mission predicted for a
migrated existing DB: **pure resighting, not rediscovery**.

| OEM | candidates | valid | new | updated | resighted | dropped_out_of_scope |
|---|---|---|---|---|---|---|
| samsung | 0 (traversal budget) | — | 0 | 0 | 0 | — |
| google | 0 (consent-page redirect, transient) | — | 0 | 0 | 0 | 0 |
| oneplus | 17 | 16 | 0 | 0 | 16 | 0 |
| nothing | 22 | 21 | 0 | 0 | 21 | 0 |
| motorola | 124 | 18 | 0 | 0 | 18 | 0 |
| honor | 80 | 22 | 0 | 0 | 22 | 0 |
| oppo | 99 | 73 | 0 | 0 | 73 | 0 |
| realme | 52 | 22 | 0 | 0 | 22 | 0 |

Zero new devices, zero updates, zero drops, zero alerts, zero pollution.
DB afterward: still 261/277/129 (devices/evidence/alerts), integrity `ok`.

## Pre-cutover comparison

Windows (still live, unchanged) vs. Hetzner (post-validation-cycle):
identical device counts per manufacturer, identical evidence/alert totals,
**zero duplicate identities on either host** (`GROUP BY manufacturer,
model_number HAVING COUNT(*) > 1` returns empty on both).

## Authority cutover

1. Windows had no `AtStartup` scheduled task for the runtime (install.ps1
   defines `SmartphoneIntelClank-Runtime`, but it was never actually
   registered — the daemon had been running as a manually-launched process
   this whole engagement). Nothing to unregister; the running process was
   the only thing to stop.
2. Windows daemon (PID 43276) stopped via `scripts/windows/stop-runtime.ps1`
   — graceful `CloseMainWindow()` timed out after 30s (expected for a
   console app with no message loop), force-killed cleanly. DB integrity
   `ok` immediately after (SQLite's atomic-commit guarantee; no in-flight
   transaction was corrupted).
3. Final snapshot taken, transferred, verified (see above), installed at
   `/opt/smartphone-clank/data/clank.db`.
4. `smartphone-clank.service` (systemd, `Type=simple`, long-lived
   BlockingScheduler — the same in-process scheduler model Windows always
   used; no scheduler redesign) started and `enable`d for boot persistence.
5. `smartphone-clank-dashboard.service` commissioned separately, bound to
   `127.0.0.1:8200` only (verified via `ss -tlnp` — not `0.0.0.0`), `/healthz`
   returns `{"status":"ok","database":"ok"}`.

**Windows production dashboard was left running** (read-only, no mutation
path per the existing report/dashboard `create_all()` fix) as
investigation/rollback material. The Windows daemon is stopped and not
scheduled to restart.

## Post-cutover validation

- Exactly one `runtime.daemon` process at all times (verified via `pgrep`
  after initial start and again after a restart-cycle test).
- `production validate`: **PASS**, all 7 wave1 OEMs + Samsung, identical
  output to Windows. Vivo/Xiaomi/Redmi/Poco/ASUS/Sony confirmed unable to
  schedule (Xiaomi shown `approved=NO configured=YES adapter=YES
  enabled=NO scheduled=NO status=OK`; the others don't even appear in the
  registry).
- Deployed SHA `83630c4` confirmed via `git rev-parse HEAD` in the running
  service's `WorkingDirectory`.
- Schema HEAD, DB integrity `ok`.
- Manufacturer counts: google 7, honor 22, motorola 15, nothing 9, oneplus
  16, oppo 73, realme 22, samsung 97 — **261 total, unchanged from Windows**.
- Zero errors/exceptions/tracebacks across the full systemd journal for
  both the initial startup pass and the restart-cycle test.
- `alerts` table: 129 (unchanged) — zero new alerts fired during migration.
- `webhook_deliveries`: 140 (unchanged).
- `python main.py report daily` (existing observability, reused unchanged):
  0 alert eligible/attempted/delivered/suppressed/failed, "Attention
  required: None", 261/277/0 devices/evidence/snapshots.

## Restart resilience (reboot substitute)

A **full host reboot was deliberately not performed.** This host runs
multiple other live projects (korean-tech-wire, oem-radar,
free-game-tracker, and others via cron/systemd timers) — per the mission's
own stop condition ("If the Hetzner machine hosts unrelated critical
workloads that make reboot unsafe: do NOT reboot... document that reboot
persistence remains unproven"), a kernel-level reboot was judged unsafe to
this shared fleet.

**What was proven instead**: both services are `systemctl enable`d
(confirmed `is-enabled` = `enabled`, meaning they are wired into
`multi-user.target` and will start on the next boot regardless of cause),
and a live `systemctl restart` of both services was exercised — clean
stop, clean start, new PID, exactly one process, DB integrity and counts
unchanged (261/129), dashboard `/healthz` OK immediately after.
**Reboot-specifically-triggered persistence remains formally unproven** —
flagged as a residual risk below, not silently assumed.

## Backups

`smartphone-clank-backup.service`/`.timer` — daily 02:30 UTC (±5min
jitter), reuses the project's own existing `main.py db backup` mechanism
(the same one Windows has always used — no new backup implementation
built), wrapped with SHA-256 checksumming and 14-day bounded retention.
First run executed manually to prove it works: `clank_20260810_204535.db`,
checksum recorded, `PRAGMA integrity_check` = `ok` on the backup file
itself, 261 devices.

**Residual risk, explicitly not solved here** (per the mission's own "do
not invent NAS integration during this mission" instruction): backups live
only on the same Hetzner disk as production. No off-host copy exists yet.

## Rollback plan (documented, not executed — system is healthy)

1. `systemctl stop smartphone-clank.service smartphone-clank-dashboard.service`
   on Hetzner; `systemctl disable` both to prevent restart-on-reboot.
2. Take a fresh SQLite-backup-API snapshot of `/opt/smartphone-clank/data/clank.db`,
   `scp` it back to the Windows prod tree's `data/backups/`, verify SHA-256
   and `PRAGMA integrity_check` on arrival.
3. Restore that snapshot to `smartphone-clank-prod/data/clank.db` (after
   backing up whatever is currently there, even though Windows was not
   written to during the soak).
4. Re-enable Windows: `scripts\windows\start-runtime.ps1` (and
   `start-dashboard.ps1` if needed — it was never stopped).
5. `python main.py production validate` on Windows — must show PASS before
   considering Windows authoritative again.
6. Confirm via process inspection that exactly one authority exists
   (Hetzner's `smartphone-clank.service` disabled+stopped, Windows daemon
   running).

Not executed — the migration is healthy and this plan exists purely as
insurance, per the mission's explicit "do not actually roll back a healthy
migration merely to demonstrate it."

## Soak start

**Authoritative soak start: `2026-08-10T20:39:49 UTC` / `2026-08-11
02:09:49 IST`** — the timestamp of `smartphone-clank.service`'s first
`runtime entering scheduler loop` log line as the sole production
authority, immediately after the Windows daemon was confirmed stopped and
the final snapshot installed. This supersedes the earlier
"2026-08-11 Windows 8-OEM freeze" timestamp recorded in `HANDOFF.md` §12e
— that was the Windows expansion-freeze point, not the cloud soak start,
per the migration mission's own explicit instruction to reset the mental
soak clock.

Recommended initial soak window: **7 days**, ending **2026-08-17**. During
this window: no new OEMs, no Xiaomi work, no schema cleanup, no zero-row
table deletion, no architectural refactor, no alert-policy experimentation.
Only correctness/reliability fixes justified by observed soak failures.

## Remaining loose ends, ranked by severity

1. **Reboot-specifically-triggered persistence is unproven** (host-level
   reboot was judged unsafe on this shared fleet host — see above).
   Service-level restart is proven; kernel reboot is not.
2. **Backups are single-host** — no off-host/NAS copy yet. Flagged, not
   solved, per explicit scope instruction.
3. **`.deployed-id` staging Docker artifact remains on disk** at
   `/home/deploy/staging/smartphone-clank` (old `1b0a183` lineage, cron now
   disabled but not removed) — harmless, but is dead weight an operator may
   want to clean up in a future, separate housekeeping pass.
4. **Google's collector returned 0 candidates** during both cutover cycles
   due to a `consent.google.com` redirect chain (regional consent-wall
   variance, not a code defect — flagged by the collector's own
   `zero_candidates_despite_healthy_fetch` metric, exactly as designed).
   Worth watching during the 7-day soak; not a migration blocker (Google's
   own device catalogue in the migrated DB is untouched and correct).
5. **Each production source was polled 3 times within ~15 minutes**
   (validation cycle, cutover startup, restart-cycle test) — all
   single-request sitemap fetches, not scraping loops, so not abusive, but
   more than strictly necessary. Noted for future migrations: prefer
   reusing one validation cycle as both the pre-cutover proof and the
   soak-start cycle where possible.

## Final verdict

```text
HETZNER_SOAK_COMMISSIONED
```

---

## Appendix: prior verification-only report (2026-08-11, superseded)

The original `MIGRATION_INCOMPLETE` verification report (written before
this migration was performed) is preserved in git history at commit
`6d3e333` and `128601a` for reference. Its core finding — that no Hetzner
deployment existed prior to this phase, and that GitHub did not contain
recoverable production source — was accurate at the time and directly
motivated the two-stage approach (GitHub checkpoint first, actual migration
second) that produced this document.
