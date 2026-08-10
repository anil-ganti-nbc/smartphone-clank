"""
Motorola discovery adapter — regional sitemap (direct URL list, not indexed).

Per docs/wave2/motorola.md: LIVE_VALIDATED, official, structured, and unlike
every other Wave 1/Wave 2 source found so far, exposes a SKU-grade slug
segment (`/p/phones/{family}/{variant}/{sku}`) rather than just a marketing
name. Scoped to a handful of major regions rather than all 51 sitemaps to
keep operational cost bounded — see WAVE2_SOURCE_MATRIX.md.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree

from collectors.wave1.adapter import (
    DISCOVERY,
    LIVE_VALIDATED,
    AdapterMetrics,
    DiscoveryAdapter,
    DiscoveryResult,
)

_XML_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

# Only /p/phones/ product pages count as candidates — /family/* landing pages
# and /p/phones/tablet|wearables/* are explicitly excluded even though they
# share the sitemap.
_PHONE_PRODUCT_RE = re.compile(r"/p/phones/([a-z0-9-]+)/([a-z0-9-]+)/([a-z0-9-]+)$")
_NON_PHONE_FAMILY = {"tablet", "wearables", "accessories"}

_FAMILY_DISPLAY = {"razr": "Razr", "moto-g": "Moto G", "motorola-edge": "Edge", "moto-e": "Moto E"}


def _variant_to_candidate(family_slug: str, variant_slug: str) -> str | None:
    if family_slug in _NON_PHONE_FAMILY:
        return None
    family = _FAMILY_DISPLAY.get(family_slug)
    if not family:
        return None
    # variant slugs look like "razr-2026", "moto-g-power-2026",
    # "razr-plus-gen-2", "g-stylus-5g-gen-4" — strip a leading duplicate of
    # the family token, title-case the rest, uppercase "5G", and fold
    # "gen-N" into "Gen N".
    parts = variant_slug.split("-")
    fam_parts = family_slug.split("-")
    if parts[: len(fam_parts)] == fam_parts:
        parts = parts[len(fam_parts):]
    words = []
    i = 0
    while i < len(parts):
        p = parts[i]
        if p == "5g":
            words.append("5G")
        elif p == "gen" and i + 1 < len(parts) and parts[i + 1].isdigit():
            words.append(f"Gen {parts[i + 1]}")
            i += 1
        elif p.isdigit() and len(p) == 4:
            words.append(p)
        else:
            words.append(p.capitalize())
        i += 1
    suffix = " ".join(words)
    return f"{family} {suffix}".strip() if suffix else family


class MotorolaSitemapDiscoveryAdapter(DiscoveryAdapter):
    manufacturer = "motorola"
    source_name = "motorola_regional_sitemap"
    source_role = DISCOVERY
    validation_state = LIVE_VALIDATED

    REGIONS = {
        "us": "https://www.motorola.com/us/en/sitemap.xml",
        "gb": "https://www.motorola.com/gb/en/sitemap.xml",
        "de": "https://www.motorola.com/de/de/sitemap.xml",
    }

    def discover(self) -> tuple[list[DiscoveryResult], AdapterMetrics]:
        metrics = AdapterMetrics()
        results: list[DiscoveryResult] = []
        seen: set[tuple[str, str]] = set()

        for region, url in self.REGIONS.items():
            resp = self._get(url, metrics)
            if resp is None:
                continue
            try:
                root = ElementTree.fromstring(resp.content)
            except ElementTree.ParseError:
                metrics.errors.append(f"xml_parse_error: {url}")
                continue

            for loc_el in root.iter(f"{_XML_NS}loc"):
                loc = (loc_el.text or "").strip()
                m = _PHONE_PRODUCT_RE.search(loc)
                if not m:
                    continue
                family_slug, variant_slug, sku = m.groups()
                candidate = _variant_to_candidate(family_slug, variant_slug)
                if not candidate:
                    continue
                key = (region, candidate)
                if key in seen:
                    continue
                seen.add(key)
                results.append(DiscoveryResult(
                    manufacturer=self.manufacturer,
                    source=self.source_name,
                    source_url=url,
                    canonical_url=loc,
                    region=region,
                    candidate_identifier=candidate,
                    raw_reference=f"{family_slug}/{variant_slug}/{sku}",
                    source_metadata={"origin": "sitemap_sku_path", "sku": sku},
                ))

        metrics.candidates_found = len(results)
        return results, metrics
