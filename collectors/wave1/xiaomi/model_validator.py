"""
Xiaomi / Redmi / POCO strict model validator.

Identifier grammar (see docs/wave1/xiaomi_recon.md):
  Internal code:   M + 4 digits + letter + 1-4 alphanumeric chars
                   e.g. M2007J3SY (region/carrier variants share a marketing
                   name but differ in the code — each is separately VALID).
  Redmi marketing: Redmi (Note )?\\d+[A-Za-z]?( Pro)?(\\+)?
  POCO marketing:  POCO [A-Z]\\d+( Pro)?
  Xiaomi marketing:Xiaomi \\d+[A-Za-z]?( Pro| Ultra| T)*
  Brand is recorded distinctly (manufacturer=redmi|poco|xiaomi) rather than
  collapsed to one "xiaomi" bucket — spec section 17 requires this.
  NOT valid:       bare "Redmi"/"POCO"/"Xiaomi", accessory/tablet/watch/audio/
                   charger/software strings, malformed M-codes.
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
    REASON_TOO_LONG,
    ValidationOutcome,
)

_INTERNAL_RE = re.compile(r"^M(\d{4})([A-Z][0-9A-Z]{1,4})$")
_REDMI_RE = re.compile(r"^Redmi( Note)? \d{1,2}[A-Za-z]?( Pro)?\+?$")
_POCO_RE = re.compile(r"^POCO [A-Z]\d{1,2}( Pro)?$")
_XIAOMI_RE = re.compile(r"^Xiaomi \d{1,2}[A-Za-z]?( Pro| Ultra| T)*$")

_BARE_FAMILY = {"redmi", "poco", "xiaomi"}


def validate(candidate_identifier: str, *, context: dict | None = None) -> ValidationOutcome:
    text = (candidate_identifier or "").strip()

    reject, reason = pre_filter(text)
    if reject:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=reason)

    if text.lower() in _BARE_FAMILY:
        return ValidationOutcome(
            outcome=INVALID, candidate_identifier=text, reason=REASON_FAMILY_NAME_WITHOUT_MODEL
        )

    m = _INTERNAL_RE.match(text)
    if m:
        return ValidationOutcome(
            outcome=VALID,
            candidate_identifier=text,
            normalized_identifier=text.upper(),
            manufacturer="xiaomi",
            marketing_name=None,
            family=None,
        )
    if text.upper().startswith("M") and len(text) > 1 and text[1:].replace(" ", "").isalnum():
        # Looks like an attempted internal code but doesn't match the grammar
        # (too short/long/wrong shape) — reject explicitly rather than falling
        # through to AMBIGUOUS, since malformed M-codes are the incident's
        # exact failure mode ("M2007J3SY0000000000000000000000EXTRA").
        if len(text) > 12 or len(text) < 8:
            return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_INVALID_LENGTH)

    if _REDMI_RE.match(text):
        return ValidationOutcome(
            outcome=VALID, candidate_identifier=text, normalized_identifier=text,
            manufacturer="redmi", marketing_name=text, family="Redmi",
        )
    if _POCO_RE.match(text):
        return ValidationOutcome(
            outcome=VALID, candidate_identifier=text, normalized_identifier=text,
            manufacturer="poco", marketing_name=text, family="POCO",
        )
    if _XIAOMI_RE.match(text):
        return ValidationOutcome(
            outcome=VALID, candidate_identifier=text, normalized_identifier=text,
            manufacturer="xiaomi", marketing_name=text, family="Xiaomi",
        )

    lower = text.lower()
    if not (lower.startswith("redmi") or lower.startswith("poco") or lower.startswith("xiaomi") or text.upper().startswith("M")):
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_INVALID_PREFIX)

    return ValidationOutcome(outcome=AMBIGUOUS, candidate_identifier=text, reason="unrecognized_xiaomi_format")
