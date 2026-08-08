# Adding a New OEM

Do **not** add OEMs until Samsung path has run cleanly for weeks.

When ready:

1. Add manufacturer enum / config allowlist entry.
2. Write a **validator** (regex + category rules) with unit tests.
3. Add knowledge YAML mappings (families, tiers) — leave unknown null.
4. Implement one collector with LIVE_VALIDATED status or keep disabled.
5. Register in `collectors/__init__.py` behind `enabled: false` until validated.
6. Extend novelty / release-state rules conservatively.

Never enable a collector that returns empty lists as “success.”
