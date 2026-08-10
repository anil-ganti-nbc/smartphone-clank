# ASUS / ROG recon

## Headline finding — supersedes everything else below

**ASUS officially exited the smartphone business as of early 2026.** ASUS
chairman Jonney Shih confirmed at ASUS's 2026 kickoff event that the company
will not launch new phone models (Zenfone or ROG Phone) and has no fixed
timeline to return, reframing the company around AI hardware instead.
Existing devices keep warranty/software support, but no new SKUs are
expected. (Reported by Digital Trends, TechRadar, Android Police, Tom's
Guide, Notebookcheck, Android Central — consistent across outlets.)

This caps ASUS's novelty potential at effectively zero for the foreseeable
future, independent of how good the discovery surface itself is.

## Sources probed anyway (for completeness / future-reactivation value)

- `asus.com/robots.txt` → three sitemaps: main `asus.com/sitemap.xml`,
  `asus.com/business/sitemap.xml`, `asus.com/proart/sitemap.xml`. Main
  sitemap is a deeply fragmented per-region index (`africa-fr1..7.xml`,
  `OfficialSite_category*.xml`, `OfficialSite_comparison*.xml` — dozens of
  tiny files per region) with **no distinct smartphone/ROG-phone
  sub-sitemap** visible — exactly the category-pollution risk the mission
  warned about for ASUS.
- **ROG Phone lives on an entirely separate subdomain**, `rog.asus.com`,
  with its own `robots.txt` → single sitemap `rog.asus.com/sitemap.xml`.
  This actually solves the category-isolation problem cleanly for ROG
  specifically (`rog.asus.com/phones/rog-phone-9/` etc., naturally isolated
  from laptops/GPUs/motherboards by subdomain, not just by path).
- Zenfone found via search at
  `asus.com/mobile-handhelds/phones/all-series/` — also a clean,
  phone-isolated path segment (`/mobile-handhelds/phones/`) on the main
  domain, distinct from laptop/motherboard/GPU categories.

## Identity structure (if this were ever reactivated)

Both subdomains give clean, deterministic per-model paths:

    rog.asus.com/phones/rog-phone-9/
    rog.asus.com/phones/rog-phone-9-pro/
    asus.com/mobile-handhelds/phones/zenfone/zenfone-12-ultra/

Category isolation is actually *good* here — the mission's concern about
ASUS's non-phone catalogue polluting extraction is mitigated by the
subdomain/path split, not a real blocker.

## Automation safety

SAFE on both `rog.asus.com` and the `/mobile-handhelds/phones/` path — no
bot-defense signals encountered.

## Verdict: REJECT (for this mission)

Not because the source is bad — the identity/discovery/safety fundamentals
are actually fine — but because the manufacturer has publicly and
specifically exited the product category this system exists to track. Zero
expected editorial value from a "new ASUS phone" sensor when ASUS has said
there won't be one. Revisit only if ASUS publicly reverses course; if that
happens, the `rog.asus.com` and `/mobile-handhelds/phones/` isolation found
here means a future adapter would not face the pollution problem the
mission anticipated.
