"""
Realme discovery adapter — regional sitemaps (direct URL list).

Per docs/wave2/realme.md: LIVE_VALIDATED, official, `/{cc}/{device-slug}`
pattern confirmed clean (no category prefix, no accessory/promo pollution
observed in the sitemap itself — that risk lives on landing pages, not
here). `/specs` sub-pages are deduplicated to their parent slug. Scoped to
a handful of high-value regions rather than all 50+ per-country sitemaps
to keep operational cost bounded — see docs/wave2/WAVE2_SOURCE_MATRIX.md
and BBK_SOURCE_COMPARISON.md.
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
_PHONE_PATH_RE = re.compile(r"/(in|eu)/(realme-[a-z0-9-]+)/?(specs)?/?$")

_GLUED_SERIES_RE = re.compile(r"^(gt|narzo|c)(\d+)$")


def _slug_to_candidate(slug: str) -> str | None:
    if not slug.startswith("realme-"):
        return None
    rest = slug[len("realme-"):]
    if not rest:
        return None
    tokens = rest.split("-")

    glued = _GLUED_SERIES_RE.match(tokens[0])
    if glued:
        tokens = [glued.group(1), glued.group(2)] + tokens[1:]

    words = []
    for tok in tokens:
        if tok == "5g":
            words.append("5G")
        elif tok == "4g":
            words.append("4G")
        elif tok == "gt":
            words.append("GT")
        else:
            words.append(tok.capitalize())
    return "realme " + " ".join(words)


class RealmeSitemapDiscoveryAdapter(DiscoveryAdapter):
    manufacturer = "realme"
    source_name = "realme_regional_sitemap"
    source_role = DISCOVERY
    validation_state = LIVE_VALIDATED

    REGIONS = {
        "in": "https://www.realme.com/sitemap-in.xml",
        "eu": "https://www.realme.com/sitemap-eu.xml",
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
                _cc, slug, _specs = m.groups()
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
                    canonical_url=f"https://www.realme.com/{region}/{slug}",
                    region=region,
                    candidate_identifier=candidate,
                    raw_reference=slug,
                    source_metadata={"origin": "sitemap_slug"},
                ))

        metrics.candidates_found = len(results)
        return results, metrics
