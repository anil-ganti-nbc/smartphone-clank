"""
Shared validator contract for Wave 1 OEM-specific validators.

Every OEM validator (collectors/wave1/<oem>/model_validator.py) implements a
function of this shape:

    def validate(candidate_identifier: str, *, context: dict | None = None) -> ValidationOutcome

Rejection over false acceptance, always. See docs/wave1/*.md for the identifier
format each OEM validator is written against, and fixtures/wave1/*_invalid.*
for the corpus every validator is tested against (test_v038_pollution_cannot_recur).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

VALID = "VALID"
INVALID = "INVALID"
AMBIGUOUS = "AMBIGUOUS"
OUTCOMES = {VALID, INVALID, AMBIGUOUS}

# Canonical rejection reasons (spec section 12). OEM validators should use
# these where they apply rather than inventing new strings, so audit queries
# across OEMs stay comparable.
REASON_MARKETING_TEXT = "marketing_text"
REASON_TOO_LONG = "too_long"
REASON_CONTAINS_SENTENCE = "contains_sentence"
REASON_INVALID_PREFIX = "invalid_prefix"
REASON_INVALID_LENGTH = "invalid_length"
REASON_KNOWN_ACCESSORY = "known_accessory"
REASON_TABLET_NOT_PHONE = "tablet_not_phone"
REASON_WATCH_NOT_PHONE = "watch_not_phone"
REASON_AUDIO_PRODUCT = "audio_product"
REASON_CHARGER = "charger"
REASON_CASE = "case"
REASON_SOFTWARE_NAME = "software_name"
REASON_FAMILY_NAME_WITHOUT_MODEL = "family_name_without_model"
REASON_NAVIGATION_TEXT = "navigation_text"
REASON_COOKIE_TEXT = "cookie_text"
REASON_PROMOTION_TEXT = "promotion_text"
REASON_EMPTY = "empty_field"
REASON_DUPLICATE = "duplicate_candidate"


@dataclass
class ValidationOutcome:
    outcome: str                      # VALID | INVALID | AMBIGUOUS
    candidate_identifier: str
    normalized_identifier: Optional[str] = None
    reason: Optional[str] = None      # required when outcome != VALID
    manufacturer: Optional[str] = None
    marketing_name: Optional[str] = None
    family: Optional[str] = None

    def __post_init__(self):
        assert self.outcome in OUTCOMES, f"invalid outcome: {self.outcome}"
        if self.outcome != VALID and not self.reason:
            raise ValueError("INVALID/AMBIGUOUS outcomes must carry a reason")
