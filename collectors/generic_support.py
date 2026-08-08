"""
Generic OEM support page collector.
Used for Google, OnePlus, Nothing, Xiaomi support pages.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from selectolax.parser import HTMLParser

from collectors.base import BaseCollector
from models.schemas import Discovery, Manufacturer, SourceType

logger = logging.getLogger("clank.collectors.generic_support")


OEM_CONFIG = {
    "google": {
        "manufacturer": Manufacturer.GOOGLE,
        "urls": [
            "https://support.google.com/pixelphone/",
            "https://store.google.com/category/phones",
        ],
        "pattern": re.compile(r"\b(Pixel\s?(?:[0-9]+|a|Pro|Fold)[a-zA-Z0-9\s]*)\b", re.I),
    },
    "oneplus": {
        "manufacturer": Manufacturer.ONEPLUS,
        "urls": [
            "https://www.oneplus.com/support",
            "https://www.oneplus.com/in/support",
        ],
        "pattern": re.compile(r"\b(CPH\d{4}|ONEPLUS\s?[A-Z0-9]+|OnePlus\s?\d+[a-zA-Z\s]*)\b", re.I),
    },
    "nothing": {
        "manufacturer": Manufacturer.NOTHING,
        "urls": [
            "https://nothing.tech/pages/support",
            "https://nothing.tech/",
        ],
        "pattern": re.compile(r"\b(Nothing\sPhone\s?\(?\d\)?|A0\d{2}|A1\d{2})\b", re.I),
    },
    "xiaomi": {
        "manufacturer": Manufacturer.XIAOMI,
        "urls": [
            "https://www.mi.com/global/support/",
            "https://www.mi.com/in/support/",
        ],
        "pattern": re.compile(r"\b(Redmi\s[A-Z0-9\s]+|POCO\s[A-Z0-9\s]+|M\d{4}[A-Z0-9]+)\b", re.I),
    },
}


class GenericSupportCollector(BaseCollector):
    def __init__(self, oem: str, **kwargs):
        super().__init__(**kwargs)
        if oem not in OEM_CONFIG:
            raise ValueError(f"Unknown OEM for generic support: {oem}")
        self.oem = oem
        self.cfg = OEM_CONFIG[oem]
        self.name = f"{oem}_support"
        self.source_type = SourceType.SUPPORT_PAGE

    def collect(self) -> list[Discovery]:
        discoveries: list[Discovery] = []
        seen: set[str] = set()
        mfr: Manufacturer = self.cfg["manufacturer"]
        pattern: re.Pattern = self.cfg["pattern"]

        for url in self.cfg["urls"]:
            try:
                resp = self.fetch(url)
                hash_ = self.content_hash(resp.text)
                tree = HTMLParser(resp.text)
                text = tree.body.text() if tree.body else resp.text

                for match in pattern.findall(text):
                    model = match.strip()
                    key = model.upper()
                    if key in seen or len(model) < 3:
                        continue
                    seen.add(key)
                    discoveries.append(
                        Discovery(
                            manufacturer=mfr,
                            model_number=model,
                            source=self.name,
                            source_type=self.source_type,
                            url=url,
                            content_hash=hash_,
                            raw={"page": url},
                        )
                    )
                logger.info(f"[{self.name}] {url} → {len(discoveries)} so far")
            except Exception as e:
                logger.warning(f"[{self.name}] {url} failed: {e}")

        return discoveries
