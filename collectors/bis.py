"""
BIS (Bureau of Indian Standards) collector.

BIS publishes registration numbers for mobile phones.
Public search: https://www.bis.gov.in/  or the CRS portal.
Note: The official portals change frequently and often use heavy JS / CAPTCHA.
v0.1 implements a respectful skeleton that can be extended once a stable
public endpoint is confirmed. We do not bypass protections.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from collectors.base import BaseCollector
from models.schemas import Discovery, Manufacturer, SourceType

logger = logging.getLogger("clank.collectors.bis")


class BISCollector(BaseCollector):
    name = "bis"
    source_type = SourceType.CERTIFICATION

    # Placeholder — replace with a working public search endpoint when stable
    # Current known entry: https://www.manakonline.in/ or CRS search
    BASE_URL = "https://www.bis.gov.in/"

    # Very conservative model patterns for Indian market phones
    MODEL_PATTERNS = {
        Manufacturer.SAMSUNG: re.compile(r"\b(SM-[A-Z0-9]{4,10})\b", re.I),
        Manufacturer.XIAOMI: re.compile(r"\b(M\d{4}[A-Z0-9]{2,6}|22\d{2}[A-Z0-9]+)\b", re.I),
        Manufacturer.ONEPLUS: re.compile(r"\b(CPH\d{4}|LE\d{4})\b", re.I),
        Manufacturer.NOTHING: re.compile(r"\b(A0\d{2}|A1\d{2})\b", re.I),
        Manufacturer.GOOGLE: re.compile(r"\b(G[A-Z0-9]{6,12})\b", re.I),
    }

    def __init__(self, manufacturers: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.manufacturers = [Manufacturer(m) for m in (manufacturers or list(self.MODEL_PATTERNS.keys()))]

    def collect(self) -> list[Discovery]:
        """
        v0.1: Soft implementation.
        Real BIS searches usually require form POSTs + session cookies + sometimes CAPTCHA.
        We log the attempt and return empty rather than produce false positives.
        Future versions can add a stable public RSS / open data feed if BIS provides one.
        """
        logger.info(f"[{self.name}] BIS public search is currently JS/form-heavy. "
                    "Collector is active but returns empty until a stable endpoint is available.")
        # Intentionally empty for accuracy. Do not invent data.
        return []
