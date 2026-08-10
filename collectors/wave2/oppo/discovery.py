"""
Oppo discovery adapter — global English storefront sitemap (direct URL list).

Per docs/wave2/oppo.md: LIVE_VALIDATED, official, `/en/smartphones/` is
path-isolated from every other product category (`/en/accessories/`,
`/en/tablets/`, `/en/wearables/`, `/en/audio/`, `/en/routers/`) in the same
sitemap. `/specs/` sub-pages are deduplicated to their parent slug — they're
confirmation pages for the same device, not separate candidates.
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
_PHONE_PATH_RE = re.compile(
    r"/en/smartphones/series-(find-x|find-n|reno|a)/([a-z0-9-]+)/?(specs)?/?$"
)

_FAMILY_DISPLAY = {"find-x": "Find X", "find-n": "Find N", "reno": "Reno", "a": "A"}

# Per-family: the exact glued letter-prefix a model number is expected to
# follow in the raw slug, once the leading "find-" (if any) is stripped.
# find-x8-pro  -> after stripping "find-", first token is "x8"  -> letter "x"
# find-n5      -> after stripping "find-", first token is "n5"  -> letter "n"
# reno13-pro   -> first token is "reno13"                       -> letter "reno"
# a5-pro-5g    -> first token is "a5"                            -> letter "a"
_FAMILY_LETTER = {"find-x": "x", "find-n": "n", "reno": "reno", "a": "a"}


def _slug_to_candidate(family_segment: str, slug: str) -> str | None:
    display = _FAMILY_DISPLAY.get(family_segment)
    letter = _FAMILY_LETTER.get(family_segment)
    if not display or letter is None:
        return None

    slug_tokens = slug.split("-")
    if family_segment.startswith("find-") and slug_tokens[:1] == ["find"]:
        slug_tokens = slug_tokens[1:]
    if not slug_tokens:
        return None

    first = slug_tokens[0]
    if not first.startswith(letter):
        return None
    number = first[len(letter):]
    if not number or not number[0].isdigit():
        return None  # family landing page or unrecognized shape — never guess

    words = []
    for tok in slug_tokens[1:]:
        if tok == "5g":
            words.append("5G")
        elif tok == "4g":
            words.append("4G")
        else:
            words.append(tok.capitalize())
    suffix = (" " + " ".join(words)) if words else ""
    return f"{display}{number}{suffix}"


class OppoSitemapDiscoveryAdapter(DiscoveryAdapter):
    manufacturer = "oppo"
    source_name = "oppo_global_sitemap"
    source_role = DISCOVERY
    validation_state = LIVE_VALIDATED

    REGIONS = {
        "global": "https://www.oppo.com/en/sitemap.xml",
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
                family_segment, slug, _specs = m.groups()
                candidate = _slug_to_candidate(family_segment, slug)
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
                    canonical_url=f"https://www.oppo.com/en/smartphones/series-{family_segment}/{slug}/",
                    region=region,
                    candidate_identifier=candidate,
                    raw_reference=f"{family_segment}/{slug}",
                    source_metadata={"origin": "sitemap_slug"},
                ))

        metrics.candidates_found = len(results)
        return results, metrics
