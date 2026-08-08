"""
Samsung Support / Model page monitor.

Samsung publishes model numbers on support pages and download centers.
We monitor known entry points and look for new SM- model numbers.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from selectolax.parser import HTMLParser

from collectors.base import BaseCollector
from models.schemas import Discovery, Manufacturer, SourceType

logger = logging.getLogger("clank.collectors.samsung_support")


class SamsungSupportCollector(BaseCollector):
    name = "samsung_support"
    source_type = SourceType.SUPPORT_PAGE

    # Public pages that often list or reference model numbers
    TARGETS = [
        "https://www.samsung.com/in/support/model/",
        "https://www.samsung.com/us/support/",
        "https://www.samsung.com/uk/support/model/",
        # Download center style pages sometimes expose models
        "https://www.samsung.com/in/support/mobile-devices/",
    ]

    MODEL_RE = re.compile(r"\b(SM-[A-Z0-9]{4,10})\b", re.IGNORECASE)

    def collect(self) -> list[Discovery]:
        discoveries: list[Discovery] = []
        seen_models: set[str] = set()

        for url in self.TARGETS:
            try:
                resp = self.fetch(url)
                hash_ = self.content_hash(resp.text)
                tree = HTMLParser(resp.text)
                text = tree.body.text() if tree.body else resp.text

                matches = self.MODEL_RE.findall(text)
                for m in matches:
                    model = m.upper()
                    if model in seen_models:
                        continue
                    seen_models.add(model)

                    discoveries.append(
                        Discovery(
                            manufacturer=Manufacturer.SAMSUNG,
                            model_number=model,
                            source=self.name,
                            source_type=self.source_type,
                            url=url,
                            content_hash=hash_,
                            raw={"page": url, "matched": model},
                        )
                    )
                logger.info(f"[{self.name}] {url} → {len(matches)} model mentions")
            except Exception as e:
                logger.warning(f"[{self.name}] failed on {url}: {e}")

        return discoveries
