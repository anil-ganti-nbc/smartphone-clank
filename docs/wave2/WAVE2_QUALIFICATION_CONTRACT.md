# Wave 2 Qualification Contract

Governs how Motorola, Oppo, Vivo, Realme, Honor, and ASUS/ROG are evaluated.
Every OEM is scored against the same six dimensions below — no dimension is
skipped, softened, or reweighted per-OEM. This mirrors the Wave 1 process
(`docs/wave1/SOURCE_MATRIX.md`, `docs/wave1/WAVE1_REPORT.md`) but is written
down explicitly this time so the framework itself, not just its output, is
auditable.

Wave 2 is a **qualification** exercise, not a promotion exercise. Nothing
scored here goes to production in this mission (see Phase 18/19).

## A. Discovery quality

Can Clank learn about an unknown/new device without a human first supplying
the product URL?

Qualifying surfaces (highest to lowest value):
- Official sitemap (XML, enumerable)
- Official product/category index
- Official newsroom/press feed
- Official support index (per-device support pages)
- Public OTA/firmware index
- Official regional catalogue page

**Known-slug monitoring does not qualify as discovery** — a source that only
confirms a slug you already know about is MONITORING or CONFIRMATION, not
DISCOVERY (see role taxonomy in Phase 5 / SOURCE_MATRIX).

Score: /20. LIVE_VALIDATED discovery-capable surface with structured data →
15-20. Discovery-capable but unstructured/HTML-scrape-only → 8-14.
Monitoring/confirmation-only, no true discovery surface found → 0-7.

## B. Automation safety

Classify each source:

- **SAFE** — plain HTTP GET, no bot defenses observed, robots.txt permits it
- **SAFE_WITH_LIMITS** — works, but needs conservative pacing/backoff or hits
  occasional soft blocks
- **FRAGILE** — works intermittently, unpredictable 403/429, JS-rendering
  required for content that might otherwise be static
- **BLOCKED** — consistently 403/429/CAPTCHA on plain requests
- **UNSUITABLE** — would require anti-bot circumvention to use at all
- **UNKNOWN** — insufficient probing to classify

Hard rule (mission-wide, not just this contract): no CAPTCHA solving, no
proxy rotation, no stealth browser, no fingerprint spoofing, no auth bypass,
no brute-forcing model IDs, no WAF circumvention. A source that fights
automation gets probed once, scored, and left alone.

Score: /20. SAFE → 18-20. SAFE_WITH_LIMITS → 12-17. FRAGILE → 5-11.
BLOCKED/UNSUITABLE → 0-4.

## C. Identity quality

Can the source expose a deterministic phone identity (marketing name, model
number, SKU, codename, or product slug) without natural-language inference?
What's the false-positive risk (accessories, promo copy, navigation labels
masquerading as product identifiers)?

Score: /20. Structured, low-collision identifier (model number/SKU/codename)
→ 15-20. Marketing-name slug only, still deterministic → 10-14. Requires
prose parsing / high pollution risk → 0-9.

## D. Novelty potential

Does the source plausibly expose unreleased-device preparation, newly
published pages, pre-launch support pages, regional launches, new
variants/configs, or availability transitions — as opposed to a static
catalogue of years-old devices?

Score: /10 (folded into "regional/novelty value" — see Phase 17 ranking).
Evidence of recent (this-generation) product churn observed during
reconnaissance → high. Catalogue dominated by discontinued/legacy models →
low.

## E. Regional value

Do meaningful regional differences exist (India-only model, China-first
launch, carrier variant, EU-only availability)? Regional differences are a
signal of source value, not license to fork device identity — manufacturer +
canonical identity remains the identity boundary (Phase 13).

Folded into the same /10 as novelty in the final ranking.

## F. Editorial usefulness

Would a smartphone journalist plausibly want to know about this before
finding out elsewhere? Higher-value signals: flagship/mid-range launches,
regional releases, unexpected variants, certification/support evidence,
pre-launch publication. Raw catalogue size is not a proxy for this.

Score: /20 (final ranking dimension "Editorial value").

## Total and verdict

    Discovery quality       /20
    Identity cleanliness    /20
    Automation safety       /20
    Editorial value         /20
    Regional/novelty value  /10
    Operational cost        /10
    ───────────────────────────
    Total                   /100

Verdict vocabulary (Phase 18) — exactly one per OEM:

- `PROMOTE_WITH_CONDITIONS` — recommended for a *future* production canary;
  NOT a promotion in this mission
- `CONTINUE_STAGING` — viable, needs more staging cycles before a canary
  recommendation
- `RESEARCH_MORE` — promising but reconnaissance was inconclusive
- `KEEP_MANUAL` — source exists but automation isn't worth the operational
  cost/risk; track manually
- `BLOCKED` — automation-hostile, do not build
- `REJECT` — no viable discovery surface, or identity/pollution risk too high

No OEM is promoted to production as part of Wave 2. See Phase 19 for the
production-invariance proof this contract's application must not violate.
