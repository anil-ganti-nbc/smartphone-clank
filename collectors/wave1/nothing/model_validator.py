"""
Nothing (and CMF by Nothing) strict model validator.

Identifier grammar (see docs/wave1/nothing_recon.md):
  Marketing name:  Phone (<n>[a])( Plus)?     e.g. Phone (1), Phone (2a), Phone (2a) Plus
  CMF:             CMF Phone <n>              e.g. CMF Phone 1
                   CMF is treated as manufacturer="cmf" with family/parent_brand
                   "Nothing" recorded in source_metadata — spec section 16 says
                   not to finalize this schema decision in Wave 1, so this is
                   deliberately just a tag, not a foreign-key relationship.
  NOT valid:       bare "Phone", bare "Nothing", "Phone (n) Case"/accessory
                   variants, Nothing Ear/Buds (audio), CMF Watch (watch),
                   Nothing OS (software).
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

_NOTHING_RE = re.compile(r"^Phone \((\d)([a-z]?)\)( Plus| Pro| Lite)?$")
_CMF_RE = re.compile(r"^CMF Phone (\d)$")


def validate(candidate_identifier: str, *, context: dict | None = None) -> ValidationOutcome:
    text = (candidate_identifier or "").strip()

    reject, reason = pre_filter(text)
    if reject:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=reason)

    m = _CMF_RE.match(text)
    if m:
        return ValidationOutcome(
            outcome=VALID,
            candidate_identifier=text,
            normalized_identifier=text,
            manufacturer="cmf",
            marketing_name=text,
            family="CMF Phone",
        )

    m = _NOTHING_RE.match(text)
    if m:
        return ValidationOutcome(
            outcome=VALID,
            candidate_identifier=text,
            normalized_identifier=text,
            manufacturer="nothing",
            marketing_name=text,
            family="Nothing Phone",
        )

    if text.lower() in ("phone", "nothing", "cmf"):
        return ValidationOutcome(
            outcome=INVALID, candidate_identifier=text, reason=REASON_FAMILY_NAME_WITHOUT_MODEL
        )

    if not (text.lower().startswith("phone") or text.lower().startswith("cmf") or text.lower().startswith("nothing")):
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_INVALID_PREFIX)

    return ValidationOutcome(outcome=AMBIGUOUS, candidate_identifier=text, reason="unrecognized_nothing_format")
