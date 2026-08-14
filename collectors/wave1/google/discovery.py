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
from urllib.parse import urlsplit

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
_NON_PHONE_SLUGS = {"pixel_tag"}


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
    SITEMAPS = {
        "us": "https://store.google.com/sitemap/sitemap_us.xml",
    }

    @staticmethod
    def _unusable_response(resp) -> str | None:
        """Classify successful HTTP responses that are not catalogue pages."""
        host = (urlsplit(str(resp.url)).hostname or "").lower()
        text = resp.text
        if host == "consent.google.com" or "Before you continue" in text:
            return "consent_interstitial"
        lowered = text.lower()
        if "captcha" in lowered or "unusual traffic" in lowered:
            return "challenge_page"
        return None

    def _extract(self, text: str, *, region: str, source_url: str) -> list[DiscoveryResult]:
        results: list[DiscoveryResult] = []
        seen: set[str] = set()
        tree = HTMLParser(text)
        body_text = tree.body.text(separator="\n") if tree.body else text

        for slug in sorted(set(_SLUG_RE.findall(text))):
            if slug in _NON_PHONE_SLUGS or any(h in slug for h in _NON_PHONE_SLUG_HINTS):
                continue
            candidate = _slug_to_candidate(slug)
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            results.append(DiscoveryResult(
                manufacturer=self.manufacturer,
                source=self.source_name,
                source_url=source_url,
                canonical_url=f"https://store.google.com/{region}/product/{slug}",
                region=region,
                candidate_identifier=candidate,
                raw_reference=slug,
                source_metadata={"origin": "product_slug"},
            ))

        # XML sitemap fallback has no teaser prose; this loop is harmless there.
        for line in (body_text or "").splitlines():
            low = line.lower()
            if not any(w in low for w in _LAUNCH_WORDS):
                continue
            match = _TEASER_RE.search(line)
            if not match:
                continue
            candidate = f"Pixel {match.group(1)}"
            if candidate in seen:
                continue
            seen.add(candidate)
            results.append(DiscoveryResult(
                manufacturer=self.manufacturer,
                source=self.source_name,
                source_url=source_url,
                region=region,
                candidate_identifier=candidate,
                raw_reference=line.strip(),
                source_metadata={"origin": "launch_teaser_text"},
            ))
        return results

    def discover(self) -> tuple[list[DiscoveryResult], AdapterMetrics]:
        metrics = AdapterMetrics()
        results: list[DiscoveryResult] = []
        seen: set[tuple[str, str]] = set()

        for region, url in self.REGIONS.items():
            resp = self._get(url, metrics)
            region_results: list[DiscoveryResult] = []
            if resp is not None:
                issue = self._unusable_response(resp)
                if issue:
                    metrics.errors.append(
                        f"unusable_response:{issue}:requested={url}:final_host={urlsplit(str(resp.url)).hostname}"
                    )
                else:
                    region_results = self._extract(resp.text, region=region, source_url=url)
                    if not region_results:
                        metrics.errors.append(f"unexpected_zero:category_parser:{region}")

            # The official per-region sitemap is the already-qualified
            # monitoring source. It recovers current product slugs without
            # cookies or browser automation, while the retained error keeps
            # source health degraded because teaser discovery is unavailable.
            if not region_results:
                sitemap_url = self.SITEMAPS[region]
                sitemap = self._get(sitemap_url, metrics)
                if sitemap is not None:
                    sitemap_issue = self._unusable_response(sitemap)
                    if sitemap_issue:
                        metrics.errors.append(
                            f"unusable_response:{sitemap_issue}:requested={sitemap_url}:"
                            f"final_host={urlsplit(str(sitemap.url)).hostname}"
                        )
                    else:
                        region_results = self._extract(
                            sitemap.text, region=region, source_url=sitemap_url
                        )
                        if not region_results:
                            metrics.errors.append(f"unexpected_zero:sitemap_parser:{region}")

            for result in region_results:
                key = (region, result.candidate_identifier or "")
                if key not in seen:
                    seen.add(key)
                    results.append(result)

        metrics.candidates_found = len(results)
        return results, metrics
