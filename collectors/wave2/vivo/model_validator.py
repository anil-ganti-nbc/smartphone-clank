"""
Vivo strict model validator.

Identifier grammar (see docs/wave2/vivo.md): a series letter (V/X/Y/S)
followed by a 1-3 digit model number, optional letter suffix, optional
Pro/Ultra/Plus qualifier, optional "5G" tag.

Examples VALID:   V21, V23 5G, X80 Pro, X100 Ultra, Y72
NOT valid:        bare series letter, "iQOO ..." (separate brand/domain —
                   explicitly not merged into Vivo, see docs/wave2/vivo.md),
                   accessory/audio/wearable strings, sentences.
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

_MODEL_RE = re.compile(
    r"^([VXYS])(\d{1,3})([A-Z]{1,2})?"
    r"( Pro| Ultra| Plus)?"
    r"( 5G)?$",
    re.IGNORECASE,
)


def validate(candidate_identifier: str, *, context: dict | None = None) -> ValidationOutcome:
    text = (candidate_identifier or "").strip()

    reject, reason = pre_filter(text)
    if reject:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=reason)

    if text.lower().startswith("iqoo"):
        # iQOO is a separate brand/domain (iqoo.com) not naturally exposed by
        # vivo.com's sitemap — see docs/wave2/vivo.md. Never silently treat
        # it as a Vivo identity.
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason="iqoo_not_vivo")

    if text.upper() in {"V", "X", "Y", "S"}:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_FAMILY_NAME_WITHOUT_MODEL)

    m = _MODEL_RE.match(text)
    if m:
        return ValidationOutcome(
            outcome=VALID,
            candidate_identifier=text,
            normalized_identifier=text.upper(),
            manufacturer="vivo",
            marketing_name=text,
            family=m.group(1).upper() + "-series",
        )

    return ValidationOutcome(outcome=AMBIGUOUS, candidate_identifier=text, reason="unrecognized_vivo_format") \
        if re.match(r"^[VXYS]", text, re.IGNORECASE) \
        else ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_INVALID_PREFIX)
