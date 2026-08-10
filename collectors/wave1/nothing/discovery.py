"""
Nothing (+ CMF by Nothing) discovery adapter — Shopify products sitemap.

Per docs/wave1/nothing_recon.md: `nothing.tech/sitemap/products/1.xml` is
LIVE_VALIDATED, official, and includes region-exclusive devices (CMF Phone 1,
India-only). The same sitemap mixes in accessories/apparel/audio under
phone-shaped slugs (`phone-1-case`, `spigen-*-phone-3*`, `nothing-hoodie`) —
the denylist below is applied to the *raw slug* before any conversion, so an
accessory slug can never be reshaped into a false phone candidate.
"""

from __future__ import annotations

from xml.etree import ElementTree

from collectors.wave1.adapter import (
    DISCOVERY,
    LIVE_VALIDATED,
    AdapterMetrics,
    DiscoveryAdapter,
    DiscoveryResult,
)

_DENYLIST_SUBSTRINGS = (
    "-case", "screen-protector", "-drop", "-upgrade", "spigen-",
    "-ear", "headphone", "cmf-buds", "cmf-watch", "cmf-power", "cmf-clip",
    "cmf-neckband", "hoodie", "tracksuit", "overall", "accidental-damage",
    "gift-card", "copy-of-",
)

_XML_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _slug_to_candidate(slug: str) -> str | None:
    slug = slug.lower()
    if slug.startswith("cmf-phone-"):
        rest = slug[len("cmf-phone-"):]
        return f"CMF Phone {rest}" if rest.isdigit() else None
    if slug.startswith("phone-"):
        rest = slug[len("phone-"):]
        if not rest:
            return None
        parts = rest.split("-")
        num = parts[0]
        if not num or not num[0].isdigit():
            return None
        out = f"Phone ({num})"
        if len(parts) > 1 and parts[1] in ("plus", "pro", "lite"):
            out += " " + parts[1].capitalize()
        return out
    return None


class NothingSitemapDiscoveryAdapter(DiscoveryAdapter):
    manufacturer = "nothing"
    source_name = "nothing_products_sitemap"
    source_role = DISCOVERY
    validation_state = LIVE_VALIDATED

    REGIONS = {
        "uk": "https://nothing.tech/sitemap/products/1.xml",
        "us": "https://us.nothing.tech/sitemap/products/1.xml",
        "in": "https://in.nothing.tech/sitemap/products/1.xml",
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
                if "/products/" not in loc:
                    continue
                slug = loc.rsplit("/products/", 1)[1].strip("/")
                if not slug or "/" in slug:
                    continue
                if any(bad in slug for bad in _DENYLIST_SUBSTRINGS):
                    continue
                candidate = _slug_to_candidate(slug)
                if not candidate:
                    continue
                key = (region, candidate)
                if key in seen:
                    continue
                seen.add(key)
                results.append(DiscoveryResult(
                    manufacturer="cmf" if candidate.startswith("CMF") else self.manufacturer,
                    source=self.source_name,
                    source_url=url,
                    canonical_url=loc,
                    region=region,
                    candidate_identifier=candidate,
                    raw_reference=slug,
                    source_metadata={"origin": "sitemap_slug", "parent_brand": "Nothing" if candidate.startswith("CMF") else None},
                ))

        metrics.candidates_found = len(results)
        return results, metrics
