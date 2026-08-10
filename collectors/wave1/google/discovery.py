"""
Google/Pixel discovery adapter — store.google.com/category/phones.

Per docs/wave1/google_recon.md: LIVE_VALIDATED, server-rendered, robots.txt-allowed,
and demonstrated a real unlisted-device teaser ("Pixel 11") during recon. Two
independent signals, both structural (never blanket text regex):
  1. `/product/{slug}` anchor hrefs -> known/current lineup slugs.
  2. Teaser lines containing launch-intent language ("Pre-order", "Coming soon",
     "Sign up", "Be the first") that also contain a "Pixel N series"-shaped
     phrase -> low-confidence pre-release candidate.
"""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser

from collectors.wave1.adapter import (
    DISCOVERY,
    LIVE_VALIDATED,
    AdapterMetrics,
    DiscoveryAdapter,
    DiscoveryResult,
)

_SLUG_RE = re.compile(r"/product/([a-z0-9_]+)")
_TEASER_RE = re.compile(r"Pixel\s+(\d{1,2})\s+series", re.I)
_LAUNCH_WORDS = ("pre-order", "coming soon", "sign up", "be the first")
_NON_PHONE_SLUG_HINTS = ("watch", "buds", "case", "charger", "tablet", "stand", "screen_protector")


def _slug_to_candidate(slug: str) -> str | None:
    slug = slug.lower()
    if not slug.startswith("pixel_"):
        return None
    parts = slug.split("_")[1:]
    if not parts:
        return None
    gen = parts[0]
    rest = parts[1:]
    out = f"Pixel {gen}"
    if rest and rest[0] == "pro":
        out += " Pro"
        rest = rest[1:]
        if rest and rest[0] == "xl":
            out += " XL"
        elif rest and rest[0] == "fold":
            out += " Fold"
    return out


class GoogleStoreDiscoveryAdapter(DiscoveryAdapter):
    manufacturer = "google"
    source_name = "google_store_category_phones"
    source_role = DISCOVERY
    validation_state = LIVE_VALIDATED

    REGIONS = {
        "us": "https://store.google.com/us/category/phones?hl=en-US",
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
            tree = HTMLParser(html)
            body_text = tree.body.text(separator="\n") if tree.body else html

            for slug in sorted(set(_SLUG_RE.findall(html))):
                if any(h in slug for h in _NON_PHONE_SLUG_HINTS):
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
                    canonical_url=f"https://store.google.com/{region}/product/{slug}",
                    region=region,
                    candidate_identifier=candidate,
                    raw_reference=slug,
                    source_metadata={"origin": "product_slug"},
                ))

            for line in (body_text or "").splitlines():
                low = line.lower()
                if not any(w in low for w in _LAUNCH_WORDS):
                    continue
                m = _TEASER_RE.search(line)
                if not m:
                    continue
                candidate = f"Pixel {m.group(1)}"
                key = (region, candidate)
                if key in seen:
                    continue
                seen.add(key)
                results.append(DiscoveryResult(
                    manufacturer=self.manufacturer,
                    source=self.source_name,
                    source_url=url,
                    region=region,
                    candidate_identifier=candidate,
                    raw_reference=line.strip(),
                    source_metadata={"origin": "launch_teaser_text"},
                ))

        metrics.candidates_found = len(results)
        return results, metrics
