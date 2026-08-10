"""
Oppo strict model validator.

Identifier grammar (see docs/wave2/oppo.md): a series prefix (Find X, Find N,
Reno, A) followed by a model number and optional qualifier suffix
(Pro/Ultra/Max/Flip/F) and optional "5G" tag.

Examples VALID:   Find X9 Ultra, Find N6, Reno16 Pro, A6 Pro 5G
NOT valid:        bare "Find" / "Reno" / "A", accessory/audio/wearable
                   strings, sentences.
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

_SERIES_RE = re.compile(
    r"^(Find X|Find N|Reno|A)(\d{1,3})"
    r"( Pro| Ultra| Max| Flip| F)?"
    r"( 5G| 4G)?$",
    re.IGNORECASE,
)

_BARE_SERIES = {"find", "find x", "find n", "reno", "a"}


def validate(candidate_identifier: str, *, context: dict | None = None) -> ValidationOutcome:
    text = (candidate_identifier or "").strip()

    reject, reason = pre_filter(text)
    if reject:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=reason)

    if text.lower() in _BARE_SERIES:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_FAMILY_NAME_WITHOUT_MODEL)

    m = _SERIES_RE.match(text)
    if m:
        return ValidationOutcome(
            outcome=VALID,
            candidate_identifier=text,
            normalized_identifier=text,
            manufacturer="oppo",
            marketing_name=text,
            family=m.group(1).title(),
        )

    low = text.lower()
    if low.startswith(("find", "reno", "oppo a")):
        return ValidationOutcome(outcome=AMBIGUOUS, candidate_identifier=text, reason="unrecognized_oppo_format")

    return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_INVALID_PREFIX)
