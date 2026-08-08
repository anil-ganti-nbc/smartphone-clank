"""
Strict Samsung model parser and category classifier.
Deterministic rules from knowledge/data/samsung_model_rules.yaml.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class ModelValidation:
    raw_value: str
    canonical_model: Optional[str] = None
    suffixes: list[str] = field(default_factory=list)
    valid: bool = False
    category_hint: Optional[str] = None
    series_hint: Optional[str] = None
    region_hint: Optional[str] = None
    validation_confidence: float = 0.0
    matched_rule: Optional[str] = None
    reject_reason: Optional[str] = None
    family_key: Optional[str] = None


class SamsungModelValidator:
    def __init__(self, rules_path: str | Path = "knowledge/data/samsung_model_rules.yaml"):
        path = Path(rules_path)
        self.rules: dict[str, Any] = {}
        if path.exists():
            with open(path, encoding="utf-8") as f:
                self.rules = yaml.safe_load(f) or {}
        self.prefixes = self.rules.get("series_prefixes") or {}
        self.suffix_hints = self.rules.get("suffix_hints") or {}
        self.alert_categories = set(self.rules.get("alert_categories") or [])
        self.exclude_categories = set(self.rules.get("exclude_categories") or [])
        self.reject_patterns = [re.compile(p) for p in self.rules.get("reject_patterns") or []]
        canon = self.rules.get("canonical_regex") or r"(?i)^(SM-[A-Z][0-9]{2,4})([A-Z0-9]*)$"
        self.canonical_re = re.compile(canon)
        # Broad finder for extraction
        self.find_re = re.compile(r"\b(SM-[A-Z0-9]{3,16})\b", re.I)

    def find_candidates(self, text: str) -> list[str]:
        return list(dict.fromkeys(m.group(1).upper() for m in self.find_re.finditer(text or "")))

    def validate(self, raw: str) -> ModelValidation:
        raw = (raw or "").strip().upper().replace(" ", "")
        result = ModelValidation(raw_value=raw)

        for pat in self.reject_patterns:
            if pat.search(raw):
                result.reject_reason = f"matched_reject_pattern:{pat.pattern}"
                return result

        # Strip slash forms: SM-S957B/DS → SM-S957B + DS
        parts = re.split(r"[/,_]", raw)
        primary = parts[0]
        extra_suffixes = [p for p in parts[1:] if p]

        m = self.canonical_re.match(primary)
        if not m:
            # try without forcing series letter class
            m2 = re.match(r"(?i)^(SM-[A-Z0-9]{3,8})([A-Z0-9]*)$", primary)
            if not m2:
                result.reject_reason = "no_canonical_match"
                return result
            base, rest = m2.group(1).upper(), m2.group(2).upper()
        else:
            base, rest = m.group(1).upper(), m.group(2).upper()

        # Identify series prefix (SM-X)
        series_key = None
        for pfx in sorted(self.prefixes.keys(), key=len, reverse=True):
            if base.startswith(pfx.upper()) or primary.startswith(pfx.upper()):
                series_key = pfx
                break
        if not series_key:
            # derive SM- + first letter after SM-
            if primary.startswith("SM-") and len(primary) > 3:
                series_key = "SM-" + primary[3]
            else:
                result.reject_reason = "unknown_series"
                return result

        meta = self.prefixes.get(series_key) or self.prefixes.get(series_key.upper()) or {}
        category = meta.get("category") or "unknown"

        if category in self.exclude_categories:
            result.reject_reason = f"excluded_category:{category}"
            result.category_hint = category
            return result

        suffixes: list[str] = []
        region_hint = None
        # Parse rest as compound suffix
        rest_full = rest
        # known multi-char first
        for multi in ("U1", "DS"):
            if rest_full.startswith(multi):
                suffixes.append(multi)
                rest_full = rest_full[len(multi):]
                hint = self.suffix_hints.get(multi) or {}
                if hint.get("region_hint") and not region_hint:
                    region_hint = hint["region_hint"]
        # single-char cascade from configured hints
        i = 0
        while i < len(rest_full):
            ch = rest_full[i]
            suffixes.append(ch)
            hint = self.suffix_hints.get(ch) or {}
            if hint.get("region_hint") and not region_hint:
                region_hint = hint["region_hint"]
            i += 1
        suffixes.extend(extra_suffixes)

        # Family key: digits portion of base
        digits = re.sub(r"[^0-9]", "", base)
        family_key = f"{series_key.replace('-', '')}{digits}" if digits else base.replace("-", "")

        # Keep first single-letter regional suffix on canonical model (SM-S928U)
        canonical = base
        if suffixes and len(suffixes[0]) == 1 and suffixes[0] in self.suffix_hints:
            hint = self.suffix_hints.get(suffixes[0]) or {}
            if hint.get("region_hint"):
                canonical = base + suffixes[0]
        result.canonical_model = canonical
        result.suffixes = suffixes
        result.valid = True
        result.category_hint = category
        result.series_hint = meta.get("series_hint")
        result.region_hint = region_hint
        result.validation_confidence = float(
            (self.rules.get("validation_confidence") or {}).get("exact_prefix_match", 0.95)
        )
        result.matched_rule = f"prefix:{series_key}"
        result.family_key = family_key
        return result

    def is_alert_eligible(self, v: ModelValidation) -> bool:
        return bool(v.valid and v.category_hint in self.alert_categories)
