# Clank Operations Guide — v0.3.3

## Interpreting health scores

| Score | Label | Action |
|------:|-------|--------|
| 90–100 | Healthy | No action |
| 75–89 | Minor issues | Review parser warnings / partial runs |
| 50–74 | Degraded | Investigate candidate or HTTP anomalies |
| 25–49 | Unhealthy | Pause newsroom reliance; fix collector |
| 0–24 | Blocked / critical | Disable source until recovered |

Scores are deterministic sums of factors (blocked, failure rate, parser failures, candidate collapse, HTTP spikes). Always read **factors** on the metrics page or in `collector_summary`.

## When to investigate

1. Health score drops below **75** for two consecutive days.
2. Maintenance note contains `REGRESSION:`.
3. Candidate count is zero while pages still fetch successfully.
4. Runtime > 2× median baseline.
5. Source stays `BLOCKED` after geo/network recovery.

## Expected daily metrics (Samsung US sitemap)

- Runs: 1–4 per day (depending on schedule)
- Pages fetched: typically 5–20 product fetches per discovery run
- Candidates: variable; baseline median established after ≥5 runs
- Success rate: target ≥ 90% over 7 days
- Alerts: only on meaningful post-deployment novelty (not baseline)

## Database growth

Expect growth proportional to:

- snapshots per monitored URL
- ledger entries per evidence event
- immutable `collector_run_metrics` rows (one per run)

Warn if snapshot or evidence counts jump by large multiples without corresponding discovery activity.

## Diagnosing parser failures

1. Check `/metrics` and last run `parser_failures`.
2. Compare candidate count to baseline median.
3. Re-fetch fixture or live page offline; run model validator.
4. If structure changed, update parser tests — do **not** disable validation.
5. Recovery should raise health score and clear regression notes on subsequent healthy runs.

## Recovering blocked sources

1. Confirm HTTP status from the same egress.
2. Keep `validation_status: BLOCKED` until LIVE_VALIDATED again.
3. Do not invent candidates while blocked.
4. After recovery, run one dry discovery and confirm candidates > 0.

## Maintenance incidents

Maintenance alerts use a **separate** webhook from newsroom alerts.
They deduplicate by condition key. Acknowledge ≠ resolve.
If the condition returns, a new incident may open.

## Commands

```bash
python main.py report daily
python main.py report daily --json
python main.py demo long-run
# dashboard metrics section
python main.py dashboard
# open /metrics
```

## Trusting “nothing happened”

A quiet day is trustworthy when:

- Collectors **did run** (runs_24h > 0)
- Status was **success**
- Candidate counts are near baseline (not collapsed to zero)
- Health scores remain ≥ 90
- No open maintenance regressions

If collectors did not run, “nothing happened” is **unknown**, not quiet.
