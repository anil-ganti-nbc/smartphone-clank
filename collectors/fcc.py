"""
FCC collector skeleton.
FCC has public equipment authorization search, but rate limits are strict.
Disabled by default in config.
"""

from __future__ import annotations

import logging
from collectors.base import BaseCollector
from models.schemas import Discovery, SourceType

logger = logging.getLogger("clank.collectors.fcc")


class FCCCollector(BaseCollector):
    name = "fcc"
    source_type = SourceType.CERTIFICATION

    def collect(self) -> list[Discovery]:
        logger.info(f"[{self.name}] FCC collector disabled / skeleton. Enable only with careful rate limits.")
        return []
