"""
Knowledge Enrichment Layer.

Deterministic rules only. No AI, no web searches, no guessing.
Collectors stay dumb; this module turns raw model numbers into structured intelligence.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("clank.knowledge")


@dataclass
class EnrichedKnowledge:
    manufacturer: Optional[str] = None
    family: Optional[str] = None
    product_tier: Optional[str] = None          # flagship / midrange / budget / foldable
    variant: Optional[str] = None               # global / usa / korea / ...
    possible_launch_month: Optional[int] = None # 1-12
    expected_chipset_class: Optional[str] = None
    confidence: str = "low"                     # low / medium / high
    notes: list[str] = field(default_factory=list)
    raw_matches: dict[str, Any] = field(default_factory=dict)


class KnowledgeBase:
    def __init__(self, data_dir: str | Path = "knowledge/data"):
        self.data_dir = Path(data_dir)
        self.manufacturers: dict[str, dict] = {}
        self.codenames: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        mfr_path = self.data_dir / "manufacturers.yaml"
        code_path = self.data_dir / "codenames.yaml"
        if mfr_path.exists():
            with open(mfr_path, "r", encoding="utf-8") as f:
                self.manufacturers = yaml.safe_load(f) or {}
        if code_path.exists():
            with open(code_path, "r", encoding="utf-8") as f:
                self.codenames = yaml.safe_load(f) or {}
        logger.info(
            f"Knowledge base loaded: {len(self.manufacturers)} manufacturers, "
            f"{len(self.codenames)} codenames"
        )

    def reload(self) -> None:
        self._load()

    def get_manufacturer_profile(self, manufacturer: str) -> dict:
        return self.manufacturers.get(manufacturer.lower(), {})

    def enrich(
        self,
        model_number: str,
        manufacturer: Optional[str] = None,
        marketing_name: Optional[str] = None,
        codename: Optional[str] = None,
    ) -> EnrichedKnowledge:
        """
        Apply deterministic enrichment rules.
        Never invent — unknown fields stay null.
        """
        result = EnrichedKnowledge()
        model = (model_number or "").strip()
        mfr = (manufacturer or "").lower() or None

        # 1. Manufacturer resolution from model prefix if missing
        if not mfr:
            for key, profile in self.manufacturers.items():
                for prefix in profile.get("model_prefixes", []):
                    if model.upper().startswith(prefix.upper()):
                        mfr = key
                        result.notes.append(f"manufacturer inferred from prefix {prefix}")
                        break
                if mfr:
                    break

        result.manufacturer = mfr

        if not mfr or mfr not in self.manufacturers:
            result.confidence = "low"
            return result

        profile = self.manufacturers[mfr]

        # 2. Series / family / tier from patterns
        for rule in profile.get("series_patterns", []):
            pat = rule.get("pattern")
            if not pat:
                continue
            if re.search(pat, model, re.IGNORECASE) or (
                marketing_name and re.search(pat, marketing_name, re.IGNORECASE)
            ):
                result.family = rule.get("family")
                result.product_tier = rule.get("tier")
                if rule.get("variant_hint"):
                    result.variant = rule.get("variant_hint")
                result.raw_matches["series_pattern"] = pat
                break

        # 3. Regional variant from suffix
        suffixes = profile.get("regional_suffixes", {})
        cleaned = model.upper().replace("-", "").replace(" ", "")
        for suffix, meaning in suffixes.items():
            if cleaned.endswith(str(suffix).upper()) and len(cleaned) > len(str(suffix)) + 3:
                # Prefer digit-before-suffix heuristic (Samsung style)
                if cleaned[-len(str(suffix)) - 1].isdigit():
                    result.variant = meaning
                    result.raw_matches["regional_suffix"] = suffix
                    break

        # 4. Launch window from tier + manufacturer calendar
        if result.product_tier == "flagship" and profile.get("typical_flagship_launch_month"):
            result.possible_launch_month = profile["typical_flagship_launch_month"]
        elif result.product_tier and "foldable" in str(result.product_tier):
            result.possible_launch_month = profile.get("typical_foldable_launch_month")

        # 5. Chipset class (very conservative)
        if result.product_tier == "flagship":
            result.expected_chipset_class = "flagship"
        elif result.product_tier == "midrange":
            result.expected_chipset_class = "midrange"
        elif result.product_tier == "budget":
            result.expected_chipset_class = "entry"

        # 6. Codename lookup
        if codename:
            key = codename.lower().strip()
            if key in self.codenames:
                entry = self.codenames[key]
                if entry.get("manufacturer") and not result.manufacturer:
                    result.manufacturer = entry["manufacturer"]
                result.raw_matches["codename"] = key

        # 7. Confidence of enrichment itself
        signals = sum(
            1
            for v in [
                result.family,
                result.product_tier,
                result.variant,
                result.possible_launch_month,
            ]
            if v is not None
        )
        if signals >= 3:
            result.confidence = "high"
        elif signals >= 1:
            result.confidence = "medium"
        else:
            result.confidence = "low"

        return result
