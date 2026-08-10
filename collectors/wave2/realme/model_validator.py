"""
Realme strict model validator.

Identifier grammar (see docs/wave2/realme.md): "realme" prefix followed by a
series token (a number, or GT/Narzo/C-series name), optional qualifier
(Pro/Ultra/Plus), optional "5G" tag. Mission flags Realme specifically for
long promotional strings — the shared pre_filter's sentence/promo/nav
heuristics carry the primary defensive weight here.

Examples VALID:   realme 16 5G, realme 16 Pro 5G, realme 16 Pro Plus 5G,
                   realme GT7, realme Narzo 70
NOT valid:        bare "realme", promotional sentences, accessory strings.
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

_NUMBERED_RE = re.compile(
    r"^realme (\d{1,3})( Pro( Plus)?| Ultra)?( 5G| 4G)?$", re.IGNORECASE
)
_NAMED_SERIES_RE = re.compile(
    r"^realme (GT|Narzo|C)\s?(\d{1,3})?([A-Za-z]{0,3})?( Pro)?( 5G)?$", re.IGNORECASE
)


def validate(candidate_identifier: str, *, context: dict | None = None) -> ValidationOutcome:
    text = (candidate_identifier or "").strip()

    reject, reason = pre_filter(text)
    if reject:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=reason)

    if text.lower() == "realme":
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_FAMILY_NAME_WITHOUT_MODEL)

    for rx, family in ((_NUMBERED_RE, "numbered"), (_NAMED_SERIES_RE, "named-series")):
        if rx.match(text):
            return ValidationOutcome(
                outcome=VALID,
                candidate_identifier=text,
                normalized_identifier=text,
                manufacturer="realme",
                marketing_name=text,
                family=family,
            )

    if text.lower().startswith("realme"):
        return ValidationOutcome(outcome=AMBIGUOUS, candidate_identifier=text, reason="unrecognized_realme_format")

    return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_INVALID_PREFIX)
