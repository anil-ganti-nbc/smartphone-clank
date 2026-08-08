"""
Bluetooth SIG collector.

Public search: https://launchstudio.bluetooth.com/
We query recent listings for known manufacturer keywords.
Note: The site is JS-heavy; we use a simple HTTP approach first.
If it fails, the collector logs and returns empty (accuracy > force).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from selectolax.parser import HTMLParser

from collectors.base import BaseCollector
from models.schemas import Discovery, Manufacturer, SourceType

logger = logging.getLogger("clank.collectors.bluetooth_sig")

# Manufacturer search terms that appear in Bluetooth listings
MFR_QUERIES = {
    Manufacturer.SAMSUNG: ["Samsung", "SM-"],
    Manufacturer.GOOGLE: ["Google", "Pixel"],
    Manufacturer.ONEPLUS: ["OnePlus", "ONEPLUS"],
    Manufacturer.NOTHING: ["Nothing", "A063", "A142"],
    Manufacturer.XIAOMI: ["Xiaomi", "Redmi", "POCO"],
}


class BluetoothSIGCollector(BaseCollector):
    name = "bluetooth_sig"
    source_type = SourceType.CERTIFICATION

    BASE = "https://launchstudio.bluetooth.com"
    # Public listing search (may change; keep configurable later)
    SEARCH_URL = "https://launchstudio.bluetooth.com/Listings/Search"

    def __init__(self, manufacturers: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.manufacturers = [Manufacturer(m) for m in (manufacturers or [])]

    def _parse_listing_page(self, html: str, mfr: Manufacturer) -> list[Discovery]:
        discoveries = []
        tree = HTMLParser(html)

        # The page structure changes; we look for common patterns
        # Model numbers often appear in table cells or links
        text = tree.body.text() if tree.body else html

        # Conservative model extraction — only high-confidence patterns
        patterns = {
            Manufacturer.SAMSUNG: r"\b(SM-[A-Z0-9]{4,8})\b",
            Manufacturer.GOOGLE: r"\b(G[A-Z0-9]{4,10}|Pixel\s?\d+[a-zA-Z\s]*)\b",
            Manufacturer.ONEPLUS: r"\b(CPH\d{4}|ONEPLUS\s?[A-Z0-9]+|LE\d{4})\b",
            Manufacturer.NOTHING: r"\b(A0\d{2}|A1\d{2}|Nothing\sPhone\s?\(?\d\)?)\b",
            Manufacturer.XIAOMI: r"\b(M\d{4}[A-Z0-9]+|22\d{2}[A-Z0-9]+|Redmi\s[A-Z0-9\s]+)\b",
        }

        pattern = patterns.get(mfr)
        if not pattern:
            return []

        found = set(re.findall(pattern, text, re.IGNORECASE))
        for match in found:
            model = match.strip().upper()
            # Basic sanity
            if len(model) < 4:
                continue
            discoveries.append(
                Discovery(
                    manufacturer=mfr,
                    model_number=model,
                    source=self.name,
                    source_type=self.source_type,
                    url=self.SEARCH_URL,
                    content_hash=self.content_hash(f"{mfr.value}:{model}"),
                    raw={"matched_text": match, "source_page": "bluetooth_sig_search"},
                )
            )
        return discoveries

    def collect(self) -> list[Discovery]:
        all_discoveries: list[Discovery] = []

        for mfr in self.manufacturers:
            try:
                # Soft attempt — many listings require auth or JS now.
                # We still try a lightweight GET and parse whatever public content exists.
                resp = self.fetch(self.SEARCH_URL)
                found = self._parse_listing_page(resp.text, mfr)
                all_discoveries.extend(found)
                logger.info(f"[{self.name}] {mfr.value}: {len(found)} candidates from page")
            except Exception as e:
                logger.warning(f"[{self.name}] {mfr.value} fetch failed (expected on JS sites): {e}")
                # Do not raise — accuracy over force. Empty is better than wrong.

        # Deduplicate by model
        seen = set()
        unique = []
        for d in all_discoveries:
            key = (d.manufacturer, d.model_number)
            if key not in seen:
                seen.add(key)
                unique.append(d)
        return unique
