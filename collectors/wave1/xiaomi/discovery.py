"""
Xiaomi / Redmi / POCO discovery adapter — mi.com/global/sitemap/ (HTML, not XML).

Per docs/wave1/xiaomi_recon.md: no XML sitemap exists anywhere on mi.com despite
systematic path probing. `mi.com/global/sitemap/` is the best available surface
(recon classification: PROMISING, not LIVE_VALIDATED) — a hand-curated HTML page
mixing phones with chargers, mice, humidifiers, air conditioners, TVs, etc.
under the same `/product/{slug}/` path shape. No page found by recon exposes a
real model number, so this adapter only ever produces marketing-name
candidates and its adapter-level validation_state is EXPERIMENTAL (weakest of
the four OEMs) rather than LIVE_VALIDATED/LIVE_PARTIAL, pending the
declaration.html follow-up flagged in the recon doc.
"""

from __future__ import annotations

import re

from collectors.wave1.adapter import (
    DISCOVERY,
    EXPERIMENTAL,
    AdapterMetrics,
    DiscoveryAdapter,
    DiscoveryResult,
)

_PRODUCT_HREF_RE = re.compile(r'href="(?:https://www\.mi\.com)?(/global/product/([a-z0-9-]+)/?)"')

_NON_PHONE_DENYLIST = (
    "charger", "buds", "band", "watch", "earphone", "headphone",
    "humidifier", "air-conditioner", "purifier", "-tv", "router", "camera",
    "scooter", "vacuum", "kettle", "lamp", "bulb", "power-bank", "power-strip",
    "power-dock", "power-adapter", "cable", "hub", "adapter", "dock", "stand",
    "die-cast", "model-car", "wireless-charging", "backpack", "bag", "case",
    "screen-protector", "mouse", "keyboard", "monitor", "laptop", "tablet",
    "pad-", "-pad", "projector", "speaker", "robot", "fan", "cooker", "iron",
    "shaver", "toothbrush", "combo",
)


def _slug_to_candidate(slug: str) -> str | None:
    slug = slug.lower()
    parts = slug.split("-")
    if not parts:
        return None

    if parts[0] == "redmi":
        rest = parts[1:]
        if rest and rest[0] == "note":
            prefix, rest = "Redmi Note", rest[1:]
        else:
            prefix = "Redmi"
        if not rest or not any(ch.isdigit() for ch in rest[0]):
            return None
        num, tail = rest[0], rest[1:]
        out = f"{prefix} {num}"
        if "pro" in tail:
            out += " Pro"
        if "plus" in tail:
            out += "+"
        return out

    if parts[0] == "poco":
        rest = parts[1:]
        if not rest or not any(ch.isdigit() for ch in rest[0]):
            return None
        out = f"POCO {rest[0].upper()}"
        if len(rest) > 1 and rest[1] == "pro":
            out += " Pro"
        return out

    if parts[0] == "xiaomi":
        rest = parts[1:]
        if not rest or not any(ch.isdigit() for ch in rest[0]):
            return None
        out = f"Xiaomi {rest[0]}"
        for extra in rest[1:]:
            if extra == "pro":
                out += " Pro"
            elif extra == "ultra":
                out += " Ultra"
            elif extra == "t":
                out += " T"
        return out

    return None


class XiaomiSitemapDiscoveryAdapter(DiscoveryAdapter):
    manufacturer = "xiaomi"
    source_name = "xiaomi_global_html_sitemap"
    source_role = DISCOVERY
    validation_state = EXPERIMENTAL

    REGIONS = {
        "global": "https://www.mi.com/global/sitemap/",
    }

    def discover(self) -> tuple[list[DiscoveryResult], AdapterMetrics]:
        metrics = AdapterMetrics()
        results: list[DiscoveryResult] = []
        seen: set[tuple[str, str]] = set()

        for region, url in self.REGIONS.items():
            resp = self._get(url, metrics)
            if resp is None:
                continue
            html = resp.text

            for href, slug in _PRODUCT_HREF_RE.findall(html):
                if any(bad in slug for bad in _NON_PHONE_DENYLIST):
                    continue
                candidate = _slug_to_candidate(slug)
                if not candidate:
                    continue
                brand = "poco" if slug.startswith("poco") else "redmi" if slug.startswith("redmi") else "xiaomi"
                key = (region, candidate)
                if key in seen:
                    continue
                seen.add(key)
                results.append(DiscoveryResult(
                    manufacturer=brand,
                    source=self.source_name,
                    source_url=url,
                    canonical_url=f"https://www.mi.com{href}",
                    region=region,
                    candidate_identifier=candidate,
                    raw_reference=slug,
                    source_metadata={"origin": "sitemap_html_slug"},
                ))

        metrics.candidates_found = len(results)
        return results, metrics
