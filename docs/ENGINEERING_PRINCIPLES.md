# Engineering Principles

Permanent project policy, written 2026-08-10 during the Wave 2 governance
phase. These rules exist to prevent Smartphone Intel Clank from repeating
OEM Radar's failure mode: **breadth increased faster than certainty about
what the system actually covered and how it actually worked.**

Every implementation decision in this project — not just this phase — is
expected to follow these rules. `docs/wave2/POST_WAVE2_COMPLEXITY_AUDIT.md`
is the first audit against them; future phases should re-run that audit's
questions before any similarly large addition.

## 1. One authoritative path per responsibility

Exactly one mechanism owns each of: discovery adapter registration,
production eligibility, staging eligibility, entity resolution, confidence
mutation, evidence persistence, alert eligibility, alert delivery
persistence, schema migration, scheduler execution, health reporting.

Before adding a second implementation of any of these: **STOP**. Do not
create `v2`, `new`, `legacy2`, `experimental2`, `alternate`, or `compat`
versions merely because modifying the existing path is inconvenient. If
duplicates already exist, identify and document them, classify which one
is authoritative, and do not casually refactor them outside of a mission
where correctness requires it.

## 2. Collectors are sensors, not applications

A collector may fetch, parse, normalize source-specific structure, emit
candidates, and report source health. It may **not** independently create
Device rows, mutate confidence, send Discord alerts, decide editorial
importance, merge identities, modify production scope, or perform
migrations. All intelligence flows through the shared downstream services
(`entity_resolution/`, `alerts/`, `database/`). If an OEM requires
bypassing this contract, that OEM does not qualify for production.

## 3. No fake coverage

A registered collector is not equivalent to coverage. Every source needs
an explicit lifecycle state: `RESEARCH_ONLY`, `FIXTURE_ONLY`,
`LIVE_PARTIAL`, `LIVE_VALIDATED`, `STAGING`, `PRODUCTION`, `BLOCKED`,
`RETIRED`. Only appropriate live states contribute to coverage claims. An
empty collector returning `[]` is not healthy coverage. A fixture-only
parser is not live coverage. A source untested in months is not assumed
healthy.

## 4. Coverage means editorial capability, not catalogue size

Do not optimize for collector count, URL count, product count, or
manufacturer count. Optimize for the probability of surfacing something a
smartphone journalist should investigate. A source producing 1,000
historic devices may be less useful than one exposing a single newly
published product/support page.

## 5. Source health != source capability

Track separately. **Health**: reachable, parser functioning, candidate
volume plausible, latency normal, failure rate normal. **Capability**:
unknown-device discovery, regional launch detection, support-page
preparation, availability changes, variant detection, pre-/post-launch
usefulness. A perfectly healthy low-capability collector must not make
Clank appear broadly covered — see Part G's capability matrix in
`docs/SOURCE_INVENTORY.md`.

## 6. No silent zero

An unexpected `HTTP 200` + `0 candidates` must not automatically mean
"nothing happened." For established sources it may indicate parser/source
regression. Every production source needs enough behavioral history to
recognize catalogue collapse; unexpected zero must surface operationally,
not silently.

## 7. Experiments never become production by accident

Promotion path: RESEARCH → LIVE VALIDATION → STAGING → BASELINE →
REPEATABILITY → CANARY → PRODUCTION. No shortcuts. Setting `enabled: true`
must never be sufficient to enter production — explicit production
allowlisting (`collectors/wave1/__init__.py`'s scope set) remains the final
independent gate, regression-tested against config-typo bypass.

## 8. Negative knowledge is first-class data

Failed source research is valuable. Record 403/429/CAPTCHA, JS-only
shells, unstable endpoints, useless catalogues, marketing pollution, lack
of a deterministic identity, unreasonable request cost, and discontinued
endpoints — with why, when tested, what was tested, and conditions for
reconsideration. Do not rediscover the same dead ends every few months
(see `docs/wave1/SOURCE_MATRIX.md` and `docs/wave2/WAVE2_SOURCE_MATRIX.md`
for the existing record of this).

## 9. Do not build a generic extraction engine too early

Prefer several readable OEM adapters over one universal rules engine,
unless repeated real implementations demonstrate the abstraction
naturally. No generic scraping DSL. No config-driven parser complexity to
eliminate modest duplication. Readability for one developer is a hard
requirement.

## 10. Dead structure must not look active

Do not leave unused collectors, abandoned migrations, obsolete config,
superseded scripts, or dead parser implementations inside normal runtime
namespaces indefinitely. Use clearly marked areas (`deprecated/`,
`archive/`, `docs/history/`) for anything kept for historical reasons. The
source tree should communicate what actually runs.

## 11. Configuration must not lie

Every configuration option must represent implemented behavior. Don't
retain settings like `adaptive_polling: true` if that isn't really wired.
Don't allow an enabled-but-unregistered collector, a registered-but-
unexecutable collector, or a production source absent from health
reporting. Add config↔registry↔runtime consistency tests where practical.

## 12. One database semantic per fact

`Device` = canonical device identity. `Evidence` = an observation
supporting a device/state. `WebhookDelivery` = alert eligibility/transport
decision/outcome (every attempt, regardless of result). `Alert` =
successfully delivered alert only (see `alerts/discord.py::record_alert()`
docstring). Do not create overlapping tables representing vaguely similar
truths. Before adding a table, explain why the existing schema cannot
represent the fact.

## 13. Database growth must be measured

Track row-growth characteristics for `Evidence`, timeline events,
collector run metrics, `WebhookDelivery`, `Alert`, `RejectedCandidate`,
snapshots, confidence ledger, baseline state. Estimate rows/day and
MB/month where meaningful. Identify intentionally-permanent append-only
tables versus eventual retention candidates. Do not implement retention
policy merely because an audit exists — measure first (see
`docs/wave2/POST_WAVE2_COMPLEXITY_AUDIT.md` Part F for the first pass).

## 14. Re-sightings are not news

Repeated unchanged observations prove source health. They must not
inflate confidence forever, create duplicate evidence, spam timelines,
send alerts, or make editorial activity look artificially high. A
re-sighting is operational evidence unless something actually changed.

## 15. Every OEM must be removable

No OEM should become entangled with core architecture. Disabling Motorola
must not require rewriting the scheduler, dashboard, confidence engine,
alerts, database schema, or entity resolver. OEM-specific knowledge stays
behind an adapter, a validator, source metadata, and manufacturer
knowledge — nothing else should know an OEM's name.

## 16. Production must survive development failure

A broken staging experiment must never stop production, mutate production
schema, touch the production DB, modify production config, alter Task
Scheduler, or send a production Discord message. Retain regression
coverage for this invariant (`tests/wave1/test_schema_authority.py` and
the physical prod/dev tree split are the current enforcement mechanisms).

## 17. Document current truth, not a development diary

`HANDOFF.md` should answer: what runs now, what is trusted, what is
staging, what is blocked, what is broken, what happens next. It should not
become an exhaustive chronological transcript — historical investigations
belong in dedicated reports (`docs/wave1/*`, `docs/wave2/*`,
`docs/V038_*`). Keep HANDOFF useful to a developer arriving cold.

## 18. Maintain a simple architecture map

`docs/ARCHITECTURE_MAP.md` communicates the main path on roughly one
screen: SOURCE → ADAPTER → VALIDATOR → RESOLVER → DEVICE + EVIDENCE →
CHANGE/CONFIDENCE → ALERT ELIGIBILITY → WEBHOOK DELIVERY → ALERT, alongside
SCHEDULER → COLLECTORS → METRICS → HEALTH, each stage naming its owning
module. If it cannot be represented simply, investigate why before adding
more.

## 19. Maintain an authoritative source inventory

`docs/SOURCE_INVENTORY.md` is the single answer to "what exactly does
Smartphone Intel Clank monitor?" — one row per source, without requiring a
reader to cross-reference configuration, Python, and six recon documents.

## 20. Complexity budget

Before introducing a major subsystem, ask: does this solve a demonstrated
failure? If not, don't build it. Continue explicitly rejecting speculative
additions — Kafka, Redis, a vector DB, a generic rules DSL, a plugin
framework, LLM classification, a public API, multi-user authentication,
Kubernetes, microservices, heavy frontend frameworks — until operational
evidence requires them. SQLite + Python + deterministic rules remain the
preferred architecture.

---

**Governing principle:** prefer fewer trustworthy sensors over many
nominal collectors; explicit missing coverage over false confidence;
boring architecture over clever architecture; measured editorial
usefulness over impressive catalogue counts. The project may become
enormous. It must never become unknowable.
