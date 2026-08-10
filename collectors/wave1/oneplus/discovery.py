"""
OnePlus discovery adapter — regional sitemap XML.

Per docs/wave1/oneplus_recon.md: `/us/sitemap.xml` is LIVE_VALIDATED (146 URLs,
current lineup present); `/global/sitemap.xml` is UNSTABLE (stale since ~2023,
excluded); root `/sitemap.xml` is BLOCKED (403). Sitemap yields marketing-name
slugs only, never CPH codes — this adapter does not attempt to guess CPH codes.
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

_NON_PRODUCT_PATHS = {
    "store", "support", "blog", "legal", "press", "customer", "brand",
    "sustainability", "trade-in", "rcc", "redcoins-center",
    "affiliate-program", "accessibility", "oxygenos12", "oxygenos13",
    "oxygenos14", "oxygenos15", "store-app", "featuring", "sitemap",
    "jcart", "retail", "discount", "power-of-community", "trade-in-rule",
    "redcoins-shop",
}
_NON_PRODUCT_SUBSTRINGS = ("keyboard", "case", "cover", "screen-protector", "charger", "buds", "watch", "band")

_XML_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _slug_to_candidate(slug: str) -> str | None:
    slug = slug.strip("/").lower()
    if not slug or slug in _NON_PRODUCT_PATHS or any(s in slug for s in _NON_PRODUCT_SUBSTRINGS):
        return None
    if slug in ("open", "oneplus-open"):
        return "OnePlus Open"
    body = slug[len("oneplus-"):] if slug.startswith("oneplus-") else slug
    if body.startswith("n") and len(body) > 1 and body[1].isdigit():
        # Nord-shaped slug (e.g. n30-5g) — best-effort, validator will decide
        return f"OnePlus Nord {body[1:].upper()}"
    m = re.match(r"^(\d{1,2})(r|t)?(-pro)?$", body)
    if m:
        num, suf, pro = m.group(1), (m.group(2) or "").upper(), m.group(3)
        out = f"OnePlus {num}{suf}"
        if pro:
            out += " Pro"
        return out
    return f"OnePlus {body}"


class OnePlusSitemapDiscoveryAdapter(DiscoveryAdapter):
    manufacturer = "oneplus"
    source_name = "oneplus_regional_sitemap"
    source_role = DISCOVERY
    validation_state = LIVE_VALIDATED

    REGIONS = {
        "us": "https://www.oneplus.com/us/sitemap.xml",
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
                if not loc:
                    continue
                prefix = f"/{region}/"
                if prefix not in loc:
                    continue
                slug = loc.split(prefix, 1)[1].strip("/")
                if not slug or "/" in slug:
                    continue
                candidate = _slug_to_candidate(slug)
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
                    raw_reference=slug,
                    source_metadata={"origin": "sitemap_slug"},
                ))

        metrics.candidates_found = len(results)
        return results, metrics
