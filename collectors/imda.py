"""
IMDA (Singapore) certification collector skeleton.
"""

from __future__ import annotations

import logging
from collectors.base import BaseCollector
from models.schemas import Discovery, SourceType

logger = logging.getLogger("clank.collectors.imda")


class IMDACollector(BaseCollector):
    name = "imda"
    source_type = SourceType.CERTIFICATION

    def collect(self) -> list[Discovery]:
        logger.info(f"[{self.name}] IMDA portal requires interactive search. Returning empty for accuracy.")
        return []
