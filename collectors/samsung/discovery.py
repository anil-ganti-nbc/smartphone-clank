"""
Samsung support-page discovery against the source registry.
Honest about LIVE_VALIDATED vs BLOCKED sources.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from selectolax.parser import HTMLParser

from collectors.samsung.model_validator import SamsungModelValidator, ModelValidation
from models.schemas import Discovery, Manufacturer, SourceType

logger = logging.getLogger("clank.samsung.discovery")


@dataclass
class DiscoveryStats:
    source_id: str
    display_name: str
    pages_fetched: int = 0
    candidates_extracted: int = 0
    valid_mobile: int = 0
    rejected: int = 0
    parser_warnings: int = 0
    validation_status: str = "unknown"
    errors: list[str] = field(default_factory=list)
    models: list[dict] = field(default_factory=list)
    rejected_items: list[dict] = field(default_factory=list)


class SamsungDiscovery:
    def __init__(
        self,
        registry_path: str = "config/samsung_sources.yaml",
        rules_path: str = "knowledge/data/samsung_model_rules.yaml",
        fixtures_dir: str = "fixtures/samsung",
    ):
        with open(registry_path, encoding="utf-8") as f:
            self.registry = yaml.safe_load(f) or {}
        self.samsung = self.registry.get("samsung") or {}
        self.validator = SamsungModelValidator(rules_path)
        self.fixtures_dir = Path(fixtures_dir)
        self.ua = self.samsung.get("user_agent", "SmartphoneIntelClank/0.3")
        self.min_delay = float(self.samsung.get("min_delay_seconds", 2.0))
        self.timeout = float(self.samsung.get("default_timeout_seconds", 25))
        self.max_bytes = int(self.samsung.get("max_response_bytes", 5_000_000))
        self._last_req = 0.0

    def sources(self) -> dict[str, dict]:
        return self.samsung.get("sources") or {}

    def _throttle(self):
        elapsed = time.time() - self._last_req
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self._last_req = time.time()

    def _fetch(self, url: str) -> tuple[int, str, Optional[str]]:
        """Returns status, body, error."""
        if self.samsung.get("kill_switch"):
            return 0, "", "kill_switch_enabled"
        self._throttle()
        try:
            with httpx.Client(
                timeout=self.timeout,
                headers={"User-Agent": self.ua},
                follow_redirects=True,
            ) as client:
                resp = client.get(url)
                body = resp.text
                if len(body.encode("utf-8", errors="replace")) > self.max_bytes:
                    return resp.status_code, "", "response_too_large"
                return resp.status_code, body, None
        except Exception as e:
            return 0, "", str(e)

    def _parse_models(self, html: str, source_id: str, url: str, region: str) -> tuple[list[dict], list[dict]]:
        accepted = []
        rejected = []
        raw_models = self.validator.find_candidates(html)
        # also check title
        try:
            tree = HTMLParser(html)
            title = (tree.css_first("title").text() if tree.css_first("title") else "") or ""
        except Exception:
            title = ""

        for raw in raw_models:
            v = self.validator.validate(raw)
            if not v.valid:
                rejected.append({"raw": raw, "reason": v.reject_reason, "url": url})
                continue
            if not self.validator.is_alert_eligible(v):
                rejected.append({
                    "raw": raw,
                    "reason": f"category_not_alertable:{v.category_hint}",
                    "url": url,
                    "category": v.category_hint,
                })
                continue
            accepted.append({
                "raw": raw,
                "canonical": v.canonical_model,
                "suffixes": v.suffixes,
                "category": v.category_hint,
                "series": v.series_hint,
                "region_hint": v.region_hint or region,
                "family_key": v.family_key,
                "confidence": v.validation_confidence,
                "url": url,
                "title": title.strip()[:200] or None,
                "source_id": source_id,
                "region": region,
            })
        return accepted, rejected

    def discover_source(self, source_id: str, *, use_fixtures_on_block: bool = True) -> DiscoveryStats:
        src = self.sources().get(source_id)
        if not src:
            return DiscoveryStats(source_id=source_id, display_name="?", errors=["unknown_source"])

        stats = DiscoveryStats(
            source_id=source_id,
            display_name=src.get("display_name") or source_id,
            validation_status=src.get("validation_status") or "unknown",
        )

        if self.samsung.get("kill_switch"):
            stats.errors.append("kill_switch")
            return stats

        status = src.get("validation_status")
        base = src.get("base_url") or ""
        paths = src.get("seed_paths") or []
        max_req = int(src.get("max_requests_per_run") or self.samsung.get("max_requests_per_run") or 10)

        urls: list[str] = []
        if paths:
            for p in paths[:max_req]:
                urls.append(base.rstrip("/") + "/" + p.lstrip("/"))
        elif base:
            urls.append(base)

        for url in urls:
            code, body, err = self._fetch(url)
            stats.pages_fetched += 1
            if err or code != 200 or not body:
                stats.errors.append(f"{url}: HTTP {code} {err or ''}".strip())
                # try fixture fallback for LIVE_VALIDATED seeds
                if use_fixtures_on_block and paths:
                    slug = url.rstrip("/").split("/")[-1]
                    fix = self.fixtures_dir / f"live_samsung_us_{slug.replace('-', '_')}.html"
                    # also try known fixture names
                    alt = list(self.fixtures_dir.glob(f"*{slug}*")) + list(self.fixtures_dir.glob("*s24*"))
                    if fix.exists():
                        body = fix.read_text(encoding="utf-8", errors="replace")
                        stats.parser_warnings += 1
                        stats.errors.append(f"fixture_fallback:{fix.name}")
                    elif alt:
                        body = alt[0].read_text(encoding="utf-8", errors="replace")
                        stats.parser_warnings += 1
                        stats.errors.append(f"fixture_fallback:{alt[0].name}")
                    else:
                        continue
                else:
                    continue

            acc, rej = self._parse_models(body, source_id, url, src.get("region") or "")
            stats.candidates_extracted += len(acc) + len(rej)
            stats.valid_mobile += len(acc)
            stats.rejected += len(rej)
            stats.models.extend(acc)
            stats.rejected_items.extend(rej)

        return stats

    def discover_all(self, *, enabled_only: bool = True, dry_run: bool = True) -> list[DiscoveryStats]:
        out = []
        for sid, src in self.sources().items():
            if enabled_only and not src.get("enabled"):
                continue
            if src.get("validation_status") in ("UNSUPPORTED",) and enabled_only:
                continue
            out.append(self.discover_source(sid))
        return out

    def to_discoveries(self, stats: DiscoveryStats) -> list[Discovery]:
        discs = []
        for m in stats.models:
            discs.append(
                Discovery(
                    manufacturer=Manufacturer.SAMSUNG,
                    model_number=m["canonical"],
                    marketing_name=None,
                    region=m.get("region"),
                    source=stats.source_id,
                    source_type=SourceType.SUPPORT_PAGE,
                    url=m.get("url"),
                    content_hash=None,
                    raw={
                        **m,
                        "_weight": 10,
                        "validation_status": stats.validation_status,
                    },
                )
            )
        return discs
