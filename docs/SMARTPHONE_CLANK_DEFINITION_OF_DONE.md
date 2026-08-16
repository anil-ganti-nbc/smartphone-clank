# Smartphone Clank — Definition of Done

Status at 2026-08-16. GitHub `main` and the Hetzner checkout are
`b8b89885e5229cb36dbc47e78cd1ef4fd1b32937`.

## Current capability

Smartphone Clank persists device identities, aliases, family links, evidence,
timeline events, baselines, source metrics, health signals, and webhook
delivery records in SQLite. It distinguishes new, updated, resighted and
rejected candidates; uses evidence-backed regional sightings where sources
provide them; and retains absence/baseline state rather than treating a single
missing fetch as removal. The dashboard is local, read-mostly operator UI.

Production scheduling is eight finite source-level systemd invocations with a
same-source lock plus a shared execution lock. Each invocation logs the full
checkout revision. The application backup command produces SQLite-safe,
checksummed daily backups.

## Production source matrix

| OEM | Source scope | Region scope | State | Important limitation |
|---|---|---|---|---|
| Samsung | support sitemap | US | production | traversal/candidate-collapse health needs soak evidence |
| Google | Store phones category | US | production | consent/interstitial must remain degraded, never healthy-zero |
| Nothing | product sitemaps | UK/US/IN | production | mixed product sitemap is denylist-filtered |
| OnePlus | sitemap | US | production | marketing slug, no formal model code |
| Motorola | regional sitemaps | US/GB/DE | production | fail-closed normalizer edge cases |
| Honor | global sitemap | global | production | CN and naming coverage not validated |
| Oppo | EN sitemap | global/EN | production | some suffix variants fail closed |
| Realme | IN/EU sitemaps | IN/EU | production | some suffix variants fail closed |

Xiaomi is experimental and unscheduled because its source is unstable.
Vivo, ASUS/ROG, certifications, firmware/OTA and legacy support collectors are
research, disabled, or explicitly out of production scope.

## Definition of feature complete

The current eight-source scope is feature complete only when it can, without
manual intervention, truthfully answer: observed device identity and region;
new/resighted/changed state and supporting evidence; a source failure,
not-due result, or suspicious zero; and a conservative absence result without
false removal or duplicate delivery. It does **not** mean every OEM or region
is supported.

## Gaps and staged plan

### P0 correctness

- None newly identified in code. Google consent handling and scheduler
  starvation are remediated, but require live soak confirmation.

### P1 completion evidence

- Natural eligible Google run must classify the current consent response
  truthfully.
- Natural eligible runs across multiple sources must prove persistence, health,
  delivery safety and no scheduler starvation.
- Confirm dashboard/operator field workflow on the owner's Windows desktop.

### P2

- Capability evidence for availability and meaningful-page changes remains
  partial/unknown for several accepted sources.
- Snapshot-pruning policy and complete metric finish-wiring need a separately
  scoped decision.

### P3 / Unified-era

- Additional OEMs, certification/OTA/retailer coverage, multi-user dashboard,
  PostgreSQL validation, and Unified Clank integration.

## Stage A — evidence gate

No source expansion. Maintain the accepted scheduler/Google revision on
Hetzner, observe real natural eligible runs, verify the existing SQLite and
delivery invariants, and record results. Automated evidence is sufficient to
continue the soak; **OWNER FIELD TEST PENDING** remains a separate gate.
