"""
Firmware / OTA collectors (skeletons + light implementations).

Samsung: public firmware sites exist (e.g. samfw, but we prefer official when possible).
Pixel: Google posts OTA pages.
Nothing: has public OTA listings sometimes.
"""

from __future__ import annotations

import logging
import re
from collectors.base import BaseCollector
from models.schemas import Discovery, Manufacturer, SourceType

logger = logging.getLogger("clank.collectors.firmware")


class SamsungFirmwareCollector(BaseCollector):
    name = "samsung_firmware"
    source_type = SourceType.FIRMWARE

    # Official-ish public references are limited; many community sites exist.
    # We stay on the safe side and do not scrape unofficial mirrors aggressively.
    TARGETS = [
        "https://www.samsung.com/us/support/",
    ]
    MODEL_RE = re.compile(r"\b(SM-[A-Z0-9]{4,10})\b", re.I)

    def collect(self) -> list[Discovery]:
        discoveries = []
        seen = set()
        for url in self.TARGETS:
            try:
                resp = self.fetch(url)
                for m in self.MODEL_RE.findall(resp.text):
                    model = m.upper()
                    if model not in seen:
                        seen.add(model)
                        discoveries.append(
                            Discovery(
                                manufacturer=Manufacturer.SAMSUNG,
                                model_number=model,
                                source=self.name,
                                source_type=self.source_type,
                                url=url,
                                content_hash=self.content_hash(model),
                            )
                        )
            except Exception as e:
                logger.warning(f"[{self.name}] {e}")
        return discoveries


class PixelOTACollector(BaseCollector):
    name = "pixel_ota"
    source_type = SourceType.OTA

    # Google occasionally publishes OTA notes; structure changes.
    TARGETS = [
        "https://developers.google.com/android/ota",
        "https://source.android.com/docs/setup/download/ota",
    ]

    def collect(self) -> list[Discovery]:
        logger.info(f"[{self.name}] Pixel OTA pages are documentation-focused. Light scan only.")
        discoveries = []
        # Conservative: only flag clear Pixel model mentions if present
        pattern = re.compile(r"\b(Pixel\s?(?:[0-9]+|a|Pro|Fold|Tablet)[a-zA-Z0-9\s]*)\b", re.I)
        for url in self.TARGETS:
            try:
                resp = self.fetch(url)
                for m in pattern.findall(resp.text):
                    discoveries.append(
                        Discovery(
                            manufacturer=Manufacturer.GOOGLE,
                            model_number=m.strip(),
                            source=self.name,
                            source_type=self.source_type,
                            url=url,
                            content_hash=self.content_hash(m),
                        )
                    )
            except Exception as e:
                logger.warning(f"[{self.name}] {e}")
        return discoveries


class NothingOTACollector(BaseCollector):
    name = "nothing_ota"
    source_type = SourceType.OTA

    def collect(self) -> list[Discovery]:
        logger.info(f"[{self.name}] Nothing OTA listings are sparse publicly. Returning empty.")
        return []
