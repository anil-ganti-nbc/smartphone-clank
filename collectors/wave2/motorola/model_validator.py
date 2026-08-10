"""
Motorola strict model validator.

Identifier grammar (see docs/wave2/motorola.md): a family name (Razr, Edge,
Moto G, Moto E) optionally followed by a qualifier (Plus/Ultra/Play/Power/
Stylus/Fold), an optional "5G" tag, and an optional 4-digit model year or
"Gen N" suffix.

Examples VALID:   Razr, Razr Plus, Razr Ultra 2026, Edge 2026, Moto G Power
                   2026, Moto G Stylus 5G Gen 4
NOT valid:        bare "Moto", tablet/wearable/accessory strings, sentences.
"""

from __future__ import annotations

import re

from collectors.wave1.common import pre_filter
from collectors.wave1.validator import (
    AMBIGUOUS,
    INVALID,
    VALID,
    REASON_INVALID_PREFIX,
    ValidationOutcome,
)

_FAMILY_RE = re.compile(
    r"^(Razr|Edge|Moto G|Moto E)"
    r"( Plus| Ultra| Play| Power| Stylus| Fold)?"
    r"( 5G)?"
    r"( \d{4})?"
    r"( Gen \d)?$",
    re.IGNORECASE,
)


def validate(candidate_identifier: str, *, context: dict | None = None) -> ValidationOutcome:
    text = (candidate_identifier or "").strip()

    reject, reason = pre_filter(text)
    if reject:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=reason)

    m = _FAMILY_RE.match(text)
    if m:
        return ValidationOutcome(
            outcome=VALID,
            candidate_identifier=text,
            normalized_identifier=text,
            manufacturer="motorola",
            marketing_name=text,
            family=m.group(1).title(),
        )

    low = text.lower()
    if low.startswith(("razr", "edge", "moto g", "moto e", "moto")):
        # Recognizable family prefix, unfamiliar suffix shape — prefer
        # AMBIGUOUS over a false accept of a naming pattern we haven't seen.
        return ValidationOutcome(outcome=AMBIGUOUS, candidate_identifier=text, reason="unrecognized_motorola_format")

    return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_INVALID_PREFIX)
