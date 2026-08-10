"""
OnePlus strict model validator.

Identifier grammar (see docs/wave1/oneplus_recon.md):
  Internal code:   CPH followed by exactly 4 digits (region variants share a
                   marketing name but differ in the last 1-2 digits, e.g.
                   CPH2649/2653/2655 for one device — all are separately VALID,
                   entity resolution decides if they're the same device).
  China variant:   PLK followed by exactly 4 digits.
  Marketing name:  OnePlus <gen>[R|T]?  |  OnePlus Open  |  OnePlus Nord <n>[...]
  NOT valid:       bare "OnePlus", "ONEPLUSSHOP"-style nav chrome, Watch/Pad/
                   Buds/Charger/Case/OxygenOS strings.
"""

from __future__ import annotations

import re

from collectors.wave1.common import pre_filter
from collectors.wave1.validator import (
    AMBIGUOUS,
    INVALID,
    VALID,
    REASON_FAMILY_NAME_WITHOUT_MODEL,
    REASON_INVALID_LENGTH,
    REASON_INVALID_PREFIX,
    ValidationOutcome,
)

_INTERNAL_RE = re.compile(r"^(CPH|PLK)(\d+)$")
_MARKETING_RE = re.compile(r"^OnePlus (\d{1,2}[RT]?( Pro)?|Open|Nord( [A-Za-z0-9-]+)?)$")


def validate(candidate_identifier: str, *, context: dict | None = None) -> ValidationOutcome:
    text = (candidate_identifier or "").strip()

    reject, reason = pre_filter(text)
    if reject:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=reason)

    m = _INTERNAL_RE.match(text)
    if m:
        prefix, digits = m.group(1), m.group(2)
        if len(digits) != 4:
            return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_INVALID_LENGTH)
        return ValidationOutcome(
            outcome=VALID,
            candidate_identifier=text,
            normalized_identifier=text.upper(),
            manufacturer="oneplus",
            marketing_name=None,
            family="OnePlus",
        )

    if text.lower() == "oneplus":
        return ValidationOutcome(
            outcome=INVALID, candidate_identifier=text, reason=REASON_FAMILY_NAME_WITHOUT_MODEL
        )

    m = _MARKETING_RE.match(text)
    if m:
        return ValidationOutcome(
            outcome=VALID,
            candidate_identifier=text,
            normalized_identifier=text,
            manufacturer="oneplus",
            marketing_name=text,
            family="OnePlus",
        )

    if not text.lower().startswith("oneplus"):
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_INVALID_PREFIX)

    return ValidationOutcome(outcome=AMBIGUOUS, candidate_identifier=text, reason="unrecognized_oneplus_format")
