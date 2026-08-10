"""
Honor discovery adapter — global storefront sitemap (direct URL list).

Per docs/wave2/honor.md: LIVE_VALIDATED, official, `/phones/{slug}` is
path-isolated from every other product category (`/laptops/`, `/wearables/`,
`/tablets/`, `/audio/`, `/routers/`, `/accessories/`) in the same sitemap.
`/spec/` and `/tips/` sub-pages are deduplicated to their parent slug —
they're confirmation pages for the same device, not separate candidates.
Scoped to the `/global/` international storefront only (not the much larger
and older `/cn/` locale — see docs/wave2/honor.md's stale-catalogue caveat).
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
_PHONE_PATH_RE = re.compile(r"/global/phones/([a-z0-9-]+)/?(spec|tips)?/?$")


def _slug_to_candidate(slug: str) -> str | None:
    # "honor-magic-v6" -> "Honor Magic V6"; "honor-600-pro" -> "Honor 600 Pro"
    parts = slug.split("-")
    if not parts or parts[0] != "honor":
        return None
    words = ["Honor"]
    for p in parts[1:]:
        if p == "v" or (words and words[-1].lower().startswith("magic") and re.match(r"^v?\d+$", p)):
            words.append(p.upper() if p == "v" else p)
        elif p.isdigit():
            words.append(p)
        else:
            words.append(p.capitalize())
    candidate = " ".join(words)
    # collapse "Magic V 6" -> "Magic V6" (adjacent letter+digit split by the hyphen)
    candidate = re.sub(r"\bV (\d+)", r"V\1", candidate)
    return candidate


class HonorSitemapDiscoveryAdapter(DiscoveryAdapter):
    manufacturer = "honor"
    source_name = "honor_global_sitemap"
    source_role = DISCOVERY
    validation_state = LIVE_VALIDATED

    REGIONS = {
        "global": "https://www.honor.com/global/sitemap.xml",
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
                m = _PHONE_PATH_RE.search(loc)
                if not m:
                    continue
                slug = m.group(1)
                if slug == "phones" or not slug:
                    continue  # the /global/phones/ index page itself
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
                    canonical_url=f"https://www.honor.com/global/phones/{slug}/",
                    region=region,
                    candidate_identifier=candidate,
                    raw_reference=slug,
                    source_metadata={"origin": "sitemap_slug"},
                ))

        metrics.candidates_found = len(results)
        return results, metrics
