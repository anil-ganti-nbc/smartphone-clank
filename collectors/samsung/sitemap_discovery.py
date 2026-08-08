"""
Samsung US support sitemap discovery.

True discovery: learns product support URLs from public sitemap
without requiring pre-seeded product slugs.
v0.3.7: supports persistent URL selection + real HTTP metrics.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse
from xml.etree import ElementTree as ET

import httpx

from collectors.samsung.model_validator import SamsungModelValidator
from models.schemas import Discovery, Manufacturer, SourceType

logger = logging.getLogger("clank.samsung.sitemap")

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

PHONE_PATH_RE = re.compile(
    r"^/us/support/mobile/phones/(galaxy-[a-z0-9-]+|other-android-phones)/([a-z0-9][a-z0-9-]*)/?$",
    re.I,
)


@dataclass
class DiscoveredURL:
    url: str
    origin_type: str  # sitemap | link_graph | seed
    origin_source: str
    lastmod: Optional[str] = None
    series: Optional[str] = None
    product_slug: Optional[str] = None


@dataclass
class HttpMetrics:
    pages_requested: int = 0
    pages_fetched: int = 0
    bytes_downloaded: int = 0
    http_failures: int = 0
    timeouts: int = 0
    redirects: int = 0
    status_counts: dict = field(default_factory=dict)

    def note_status(self, code: int):
        key = str(code)
        self.status_counts[key] = self.status_counts.get(key, 0) + 1


@dataclass
class SitemapRunStats:
    source_id: str = "samsung_us_support_sitemap"
    pages_fetched: int = 0
    pages_requested: int = 0
    bytes_downloaded: int = 0
    http_failures: int = 0
    sitemap_urls: int = 0
    phone_product_urls: int = 0
    new_urls: int = 0
    models_extracted: int = 0
    valid_mobile: int = 0
    rejected: int = 0
    selected_urls: int = 0
    fetch_results: dict = field(default_factory=dict)
    status_counts: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    discoveries: list[dict] = field(default_factory=list)
    validation_status: str = "LIVE_VALIDATED"
    sitemap_body: str = ""
    parsed_urls: list = field(default_factory=list)


def normalize_url(url: str, strip_params: set[str] | None = None) -> str:
    strip = strip_params or {"cid", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}
    try:
        p = urlparse(url)
        from urllib.parse import parse_qs, urlencode
        q = parse_qs(p.query, keep_blank_values=False)
        q = {k: v for k, v in q.items() if k.lower() not in strip}
        path = p.path.rstrip("/") + ("/" if p.path.endswith("/") else "")
        return urlunparse((p.scheme, p.netloc.lower(), path, "", urlencode(q, doseq=True), ""))
    except Exception:
        return url


class SamsungSitemapDiscovery:
    INDEX_URL = "https://www.samsung.com/us/sitemap.xml"
    SUPPORT_SITEMAP_URL = "https://www.samsung.com/us/support_sitemap.xml"

    def __init__(
        self,
        *,
        user_agent: str = "SmartphoneIntelClank/0.3.7 (research; respectful)",
        min_delay: float = 2.0,
        timeout: float = 30.0,
        max_product_fetches: int = 60,
        fixtures_dir: str = "fixtures/samsung",
        known_urls: set[str] | None = None,
    ):
        self.ua = user_agent
        self.min_delay = min_delay
        self.timeout = timeout
        self.max_product_fetches = max_product_fetches
        self.fixtures_dir = Path(fixtures_dir)
        self.known_urls = known_urls or set()
        self.validator = SamsungModelValidator()
        self._last = 0.0
        self.http = HttpMetrics()

    def _throttle(self):
        elapsed = time.time() - self._last
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self._last = time.time()

    def _fetch(self, url: str, *, prefer_fixture: bool = False) -> tuple[int, str, Optional[str], int]:
        """Returns status, body, error, bytes_read."""
        if prefer_fixture:
            name = "live_samsung_us_support_sitemap.xml" if "support_sitemap" in url else None
            if name and (self.fixtures_dir / name).exists():
                body = (self.fixtures_dir / name).read_text(encoding="utf-8", errors="replace")
                b = len(body.encode("utf-8"))
                self.http.pages_requested += 1
                self.http.pages_fetched += 1
                self.http.bytes_downloaded += b
                self.http.note_status(200)
                return 200, body, None, b
        self._throttle()
        self.http.pages_requested += 1
        try:
            with httpx.Client(timeout=self.timeout, headers={"User-Agent": self.ua}, follow_redirects=True) as c:
                r = c.get(url)
                body = r.text or ""
                b = len(r.content or b"")
                self.http.note_status(r.status_code)
                if r.history:
                    self.http.redirects += len(r.history)
                if r.status_code == 200:
                    self.http.pages_fetched += 1
                    self.http.bytes_downloaded += b
                    return r.status_code, body, None, b
                self.http.http_failures += 1
                return r.status_code, body, None, b
        except httpx.TimeoutException as e:
            self.http.timeouts += 1
            self.http.http_failures += 1
            self.http.note_status(0)
            return 0, "", f"timeout:{e}", 0
        except Exception as e:
            self.http.http_failures += 1
            self.http.note_status(0)
            return 0, "", str(e), 0

    def parse_sitemap_urls(self, xml_text: str) -> list[DiscoveredURL]:
        out: list[DiscoveredURL] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning(f"sitemap parse error: {e}")
            return out

        for url_el in root.findall("sm:url", NS) or root.findall("url"):
            loc_el = url_el.find("sm:loc", NS) if url_el.find("sm:loc", NS) is not None else url_el.find("loc")
            if loc_el is None or not loc_el.text:
                continue
            loc = loc_el.text.strip()
            lastmod_el = url_el.find("sm:lastmod", NS)
            if lastmod_el is None:
                lastmod_el = url_el.find("lastmod")
            lastmod = lastmod_el.text.strip() if lastmod_el is not None and lastmod_el.text else None
            path = urlparse(loc).path
            m = PHONE_PATH_RE.match(path)
            if not m:
                continue
            series, slug = m.group(1), m.group(2)
            out.append(
                DiscoveredURL(
                    url=normalize_url(loc),
                    origin_type="sitemap",
                    origin_source="samsung_us_support_sitemap",
                    lastmod=lastmod,
                    series=series,
                    product_slug=slug,
                )
            )
        return out

    def load_sitemap(self, *, use_fixture_sitemap: bool = False) -> SitemapRunStats:
        stats = SitemapRunStats()
        code, body, err, nbytes = self._fetch(self.SUPPORT_SITEMAP_URL, prefer_fixture=use_fixture_sitemap)
        if code != 200 or not body:
            fix = self.fixtures_dir / "live_samsung_us_support_sitemap.xml"
            if fix.exists():
                body = fix.read_text(encoding="utf-8", errors="replace")
                stats.errors.append("sitemap_fixture_fallback")
            else:
                stats.errors.append(f"sitemap_fetch_failed:{code}:{err}")
                stats.validation_status = "UNAVAILABLE"
                stats.pages_requested = self.http.pages_requested
                stats.pages_fetched = self.http.pages_fetched
                stats.bytes_downloaded = self.http.bytes_downloaded
                stats.http_failures = self.http.http_failures
                stats.status_counts = dict(self.http.status_counts)
                return stats
        stats.sitemap_body = body
        urls = self.parse_sitemap_urls(body)
        stats.parsed_urls = urls
        stats.sitemap_urls = len(re.findall(r"<loc>", body))
        stats.phone_product_urls = len(urls)
        return stats

    def fetch_product_urls(
        self,
        targets: list[tuple[str, str, str | None, str | None]],
        stats: SitemapRunStats,
    ) -> SitemapRunStats:
        """
        targets: list of (url, normalized_url, product_slug, series)
        Mutates stats.discoveries and fetch_results.
        """
        stats.selected_urls = len(targets)
        for url, nurl, slug, series in targets:
            code, html, err, nbytes = self._fetch(url)
            result = "FETCH_HTTP_ERROR"
            models_found: list = []
            if code == 200 and html:
                raw_models = self.validator.find_candidates(html)
                stats.models_extracted += len(raw_models)
                accepted = []
                for raw in raw_models:
                    v = self.validator.validate(raw)
                    if v.valid and self.validator.is_alert_eligible(v):
                        accepted.append(v)
                    else:
                        stats.rejected += 1
                if accepted:
                    result = "FETCH_SUCCESS_MODEL_FOUND"
                    for v in accepted:
                        stats.valid_mobile += 1
                        models_found.append(v.canonical_model)
                        stats.discoveries.append({
                            "url": url,
                            "normalized_url": nurl,
                            "origin_type": "sitemap",
                            "origin_source": "samsung_us_support_sitemap",
                            "model": v.canonical_model,
                            "raw": v.raw_value,
                            "category": v.category_hint,
                            "series": v.series_hint or series,
                            "region_hint": v.region_hint,
                            "family_key": v.family_key,
                            "product_slug": slug,
                            "fetch_result": result,
                        })
                else:
                    result = "FETCH_SUCCESS_NO_MODEL"
            elif code == 403:
                result = "FETCH_BLOCKED"
            elif code == 0:
                result = "FETCH_HTTP_ERROR"
                if err and "timeout" in err:
                    result = "FETCH_HTTP_ERROR"
            else:
                result = "FETCH_HTTP_ERROR"
            stats.fetch_results[nurl] = {
                "url": url,
                "status": code,
                "result": result,
                "bytes": nbytes,
                "models": models_found,
                "error": err,
            }
            if code != 200:
                stats.errors.append(f"fetch_fail:{url}:{code}:{err or ''}")
        stats.pages_requested = self.http.pages_requested
        stats.pages_fetched = self.http.pages_fetched
        stats.bytes_downloaded = self.http.bytes_downloaded
        stats.http_failures = self.http.http_failures
        stats.status_counts = dict(self.http.status_counts)
        return stats

    def discover(
        self,
        *,
        fetch_products: bool = True,
        use_fixture_sitemap: bool = False,
        max_fetches: int | None = None,
    ) -> SitemapRunStats:
        """Legacy path: first-N without persistence (kept for CLI/fixtures)."""
        stats = self.load_sitemap(use_fixture_sitemap=use_fixture_sitemap)
        if stats.validation_status == "UNAVAILABLE":
            return stats
        max_f = max_fetches if max_fetches is not None else self.max_product_fetches
        urls = stats.parsed_urls
        novel = [u for u in urls if u.url.rstrip("/") not in {k.rstrip("/") for k in self.known_urls}]
        stats.new_urls = len(novel)
        if not fetch_products:
            return stats
        to_fetch = (novel[:max_f] if novel else urls[:max_f])
        targets = [
            (u.url, normalize_url(u.url).rstrip("/"), u.product_slug, u.series) for u in to_fetch
        ]
        return self.fetch_product_urls(targets, stats)

    def to_pipeline_discoveries(self, stats: SitemapRunStats) -> list[Discovery]:
        out = []
        seen = set()
        for d in stats.discoveries:
            model = d.get("model")
            if not model or model in seen:
                continue
            seen.add(model)
            out.append(
                Discovery(
                    manufacturer=Manufacturer.SAMSUNG,
                    model_number=model,
                    region="US",
                    source="samsung_us_support_sitemap",
                    source_type=SourceType.SUPPORT_PAGE,
                    url=d.get("url"),
                    raw={
                        **d,
                        "_weight": 10,
                        "origin_type": d.get("origin_type"),
                        "discovery": True,
                    },
                )
            )
        return out
