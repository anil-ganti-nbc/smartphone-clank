"""
Honor strict model validator.

Identifier grammar (see docs/wave2/honor.md): "Honor" prefix followed by
either "Magic" + generation (+ optional "V" fold tag) + optional "Pro"/
"Ultra", or a bare numeric series + optional "Pro"/regional-variant suffix.

Examples VALID:   Honor Magic V6, Honor Magic8 Pro, Honor 600, Honor 600 Pro
NOT valid:        bare "Honor", laptop/tablet/wearable/audio/router strings,
                   sentences.
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

_MAGIC_RE = re.compile(r"^Honor Magic ?V?(\d{1,2})( Pro| Ultra)?$", re.IGNORECASE)
_NUMBERED_RE = re.compile(r"^Honor (\d{2,4})( Pro| Ultra)?$", re.IGNORECASE)


def validate(candidate_identifier: str, *, context: dict | None = None) -> ValidationOutcome:
    text = (candidate_identifier or "").strip()

    reject, reason = pre_filter(text)
    if reject:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=reason)

    if text.lower() == "honor":
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_FAMILY_NAME_WITHOUT_MODEL)

    for rx in (_MAGIC_RE, _NUMBERED_RE):
        if rx.match(text):
            return ValidationOutcome(
                outcome=VALID,
                candidate_identifier=text,
                normalized_identifier=text,
                manufacturer="honor",
                marketing_name=text,
                family="Magic" if rx is _MAGIC_RE else "Numbered",
            )

    if text.lower().startswith("honor"):
        return ValidationOutcome(outcome=AMBIGUOUS, candidate_identifier=text, reason="unrecognized_honor_format")

    return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_INVALID_PREFIX)
