"""
TDRA (UAE) certification collector skeleton.
Public portal exists but is form-driven. Accuracy-first: empty until stable endpoint.
"""

from __future__ import annotations

import logging
from collectors.base import BaseCollector
from models.schemas import Discovery, SourceType

logger = logging.getLogger("clank.collectors.tdra")


class TDRACollector(BaseCollector):
    name = "tdra"
    source_type = SourceType.CERTIFICATION

    def collect(self) -> list[Discovery]:
        logger.info(f"[{self.name}] TDRA portal is form-based. Returning empty for accuracy.")
        return []
