"""
Google / Pixel strict model validator.

Identifier grammar (see docs/wave1/google_recon.md for source evidence):
  Marketing name:  Pixel <gen>[a]?( Pro( XL| Fold)?)?
                   gen is 1-2 digits, observed range so far 6-11.
  Examples VALID:  Pixel 9, Pixel 9 Pro, Pixel 9 Pro XL, Pixel 9a, Pixel 9 Pro Fold
  NOT valid:       bare "Pixel", any sentence/marketing prose, Watch/Tablet/
                   Buds/Charger/Case/Android-version strings (all non-phone
                   Google products that share the "Pixel"/"Android" prefix).
"""

from __future__ import annotations

import re

from collectors.wave1.common import pre_filter
from collectors.wave1.validator import (
    AMBIGUOUS,
    INVALID,
    VALID,
    REASON_FAMILY_NAME_WITHOUT_MODEL,
    REASON_INVALID_PREFIX,
    ValidationOutcome,
)

_MARKETING_RE = re.compile(
    r"^Pixel (\d{1,2})(a)?( Pro( XL| Fold)?)?$"
)


def validate(candidate_identifier: str, *, context: dict | None = None) -> ValidationOutcome:
    text = (candidate_identifier or "").strip()

    reject, reason = pre_filter(text)
    if reject:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=reason)

    if text.lower() == "pixel":
        return ValidationOutcome(
            outcome=INVALID, candidate_identifier=text, reason=REASON_FAMILY_NAME_WITHOUT_MODEL
        )

    m = _MARKETING_RE.match(text)
    if m:
        gen = int(m.group(1))
        if not (1 <= gen <= 20):
            return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason="invalid_generation")
        return ValidationOutcome(
            outcome=VALID,
            candidate_identifier=text,
            normalized_identifier=text,
            manufacturer="google",
            marketing_name=text,
            family="Pixel",
        )

    if not text.lower().startswith("pixel"):
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_INVALID_PREFIX)

    # Starts with "Pixel" but doesn't match the marketing grammar — could be a
    # new naming scheme (e.g. a future "Pixel 10 Ultra") we haven't seen yet.
    # Prefer AMBIGUOUS over false-accepting an unfamiliar shape.
    return ValidationOutcome(outcome=AMBIGUOUS, candidate_identifier=text, reason="unrecognized_pixel_format")
