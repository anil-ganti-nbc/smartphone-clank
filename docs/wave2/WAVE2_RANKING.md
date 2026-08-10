# Wave 2 Ranking

Scored per `docs/wave2/WAVE2_QUALIFICATION_CONTRACT.md`. Ratings reflect
`docs/wave2/{motorola,honor,oppo,vivo,realme,asus_rog}.md` recon and, for
Motorola/Honor, the live staging results below (baseline + 3 cycles, 0
alerts, 0 cross-OEM collisions, stable repeat counts).

| OEM | Discovery /20 | Identity /20 | Automation safety /20 | Editorial value /20 | Regional/novelty /10 | Operational cost /10 | Total /100 | Verdict |
|---|---|---|---|---|---|---|---|---|
| Motorola | 18 | 17 | 19 | 15 | 8 | 7 | **84** | **PROMOTED 2026-08-10** — see `docs/wave2/MOTOROLA_CANARY_REPORT.md` |
| Honor | 16 | 12 | 19 | 14 | 7 | 8 | **76** | **PROMOTED 2026-08-11** — see `docs/wave2/HONOR_CANARY_REPORT.md` |
| Oppo | 18 | 14 | 19 | 16 | 6 | 9 | **82** | **PROMOTED 2026-08-11** — see `docs/wave2/OPPO_CANARY_REPORT.md` |
| Realme | 17 | 14 | 19 | 15 | 7 | 7 | **79** | **PROMOTED 2026-08-11** — see `docs/wave2/REALME_CANARY_REPORT.md` |
| Vivo | 8 | 14 | 19 | 5 | 3 | 8 | **57** | RESEARCH_MORE (re-scored, see `docs/wave2/vivo.md` update — structural sitemap gap confirmed across 4 regions, not promoted) |
| ASUS/ROG | 15 | 15 | 19 | 1 | 0 | 5 | **55** | REJECT |

## Rationale

**Motorola (84, PROMOTE_WITH_CONDITIONS)** — highest score by a clear
margin. Only Wave 2 source with a SKU-grade identifier, not just a
marketing-name slug (Identity 17/20). True enumerable sitemap discovery,
zero automation friction, live-validated with a real baseline (15 new
devices, 3 evidence-merged updates) and 3 stable repeat cycles (0 new, 0
evidence explosion). Docked on operational cost (51 regional sitemaps if
polled exhaustively — mitigated by scoping to a handful of regions, as
done here) and editorial value (mature/incremental product line, not a
frequent-surprise brand).

**Honor (76, PROMOTE_WITH_CONDITIONS)** — second-highest. Clean
category-isolated sitemap (`/phones/` vs every other product line),
live-validated with a real baseline (22 new devices) and 3 stable repeat
cycles. Docked on identity quality (marketing-name slug only, no formal
model number found) and a known gap: only the `/global/` locale was
sampled — the much larger `/cn/` locale (flagged by the mission for
Huawei-era stale-catalogue risk) is unverified.

**Oppo (82, PROMOTED 2026-08-11)** — re-scored after the final pre-soak
expansion mission decomposed `oppo.com/sitemap.xml` and found
`oppo.com/en/sitemap.xml`: a true enumerable sitemap (not the curated
category page used previously), with clean category-path isolation
(`/en/smartphones/` vs `/en/accessories/`/`/en/tablets/`/`/en/wearables/`)
and current flagships present (Find X9/X9 Pro/X9 Ultra). This resolved
the prior blocker entirely. Live staging: 99 raw candidates, 73 valid, 0
rejected as pollution, 3 stable cycles, 0 cross-OEM collisions. See
`docs/wave2/OPPO_CANARY_REPORT.md`.

**Realme (79, PROMOTED 2026-08-11)** — re-scored after checking
`realme.com/sitemap-in.xml` (India, Realme's largest market): 80 entries,
all current-generation (15/16/GT7/Narzo series), resolving the prior
single-small-region blocker. The promotional-text risk the mission
flagged was confirmed real but only on landing pages, never in sitemap
slugs — validator hardened with that understanding regardless. Live
staging: 52 raw candidates, 22 valid, 0 rejected as pollution, 3 stable
cycles, 0 cross-OEM collisions. See `docs/wave2/REALME_CANARY_REPORT.md`.

**Vivo (57, RESEARCH_MORE, re-scored downward)** — the "check a fresher
region" hypothesis from the prior ranking was tested directly this
mission: `/in/`, `/en/` (global), and `/au/` were all checked in addition
to the original `/uk/` sample, and **none of the three contain any
product-catalogue entries at all** — only `/uk/` exposes
`/products/param/{model}` URLs, and it remains the same stale set
(v21/x60pro/x80pro, no current-generation flagship) found during
qualification. This is now a confirmed structural finding, not a gap —
scored down accordingly (Discovery 12→8, Editorial 8→5, Regional/novelty
5→3). Not promoted. iQOO question remains resolved cleanly (no merge
pressure — see `vivo.md`); that resolution doesn't affect the score
either direction, it just removes a risk that would have applied
regardless of the sitemap finding.

**ASUS/ROG (55, REJECT)** — technically the source fundamentals are
fine (subdomain/path isolation from PC hardware actually solves the
mission's stated pollution concern), which is why Discovery/Identity/Safety
score respectably. But editorial value and novelty are scored at
essentially zero because ASUS **publicly exited the smartphone business
as of early 2026** — no new Zenfone or ROG Phone models are expected. A
technically-clean sensor for a product line that has stopped shipping new
products has no purpose. This is the one OEM where the numeric dimensions
don't drive the verdict — the business-context finding overrides them.

## Post-ranking update (2026-08-10, governance + canary phase)

Motorola was promoted to production the same day this ranking was
finalized, following the engineering governance lock-in
(`docs/ENGINEERING_PRINCIPLES.md`) and a clean complexity-audit gate
(`docs/wave2/POST_WAVE2_COMPLEXITY_AUDIT.md`). Honor's
`PROMOTE_WITH_CONDITIONS` status was preserved but deliberately not acted
on that mission.

## Second post-ranking update (2026-08-11, Honor canary)

Honor promoted to production, using the exact scope/config mechanism
Motorola proved — see `docs/wave2/HONOR_CANARY_REPORT.md`. No new
architecture required. Production OEMs now: Samsung, Google, Nothing,
OnePlus, Motorola, Honor. Oppo/Vivo/Realme/ASUS verdicts unchanged.

## Missing OEM noted, not pursued

**Sony (Xperia)** came up during recon as a plausible seventh candidate —
a major-brand flagship line not in the initial pool. Not investigated
this mission per the explicit instruction not to expand scope beyond the
six named OEMs; flagged here only per that instruction's own allowance
("mention it in the final report only").
