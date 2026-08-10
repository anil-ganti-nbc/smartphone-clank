"""
ASUS/ROG strict model validator.

Built for completeness per the Wave 2 qualification contract even though
this OEM's verdict is REJECT (ASUS publicly exited the smartphone business
as of early 2026 — see docs/wave2/asus_rog.md). If ASUS ever resumes, this
validator is ready; it exists mainly to prove the category-isolation
approach (see PC-hardware rejection below).

Identifier grammar: "Zenfone" or "ROG Phone" followed by a model number and
optional Pro/Ultra qualifier.

Examples VALID:   Zenfone 12 Ultra, Zenfone 9, ROG Phone 9, ROG Phone 9 Pro
NOT valid:        any ASUS laptop/motherboard/GPU/monitor/router model
                   string (mandatory rejection — this is ASUS's single
                   biggest pollution risk per the mission), sentences.
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
    REASON_PC_HARDWARE,
    ValidationOutcome,
)

_PHONE_RE = re.compile(r"^(Zenfone|ROG Phone) (\d{1,2})( Pro| Ultra)?$", re.IGNORECASE)

# Deliberately broad — ASUS's non-phone catalogue (laptops, motherboards,
# GPUs, monitors, routers, mini PCs) is the mission's specifically named
# pollution risk for this OEM.
_PC_HARDWARE_WORDS = (
    "laptop", "notebook", "vivobook", "zenbook", "chromebook", "rog strix",
    "rog zephyrus", "tuf gaming", "motherboard", "prime ", "rog crosshair",
    "rog maximus", "graphics card", "geforce", "radeon", "rtx ", " gtx ",
    "monitor", "proart display", "router", "rt-ax", "zenwifi", "mini pc",
    "nuc", "chromebox", "mouse", "keyboard", "headset",
)


def validate(candidate_identifier: str, *, context: dict | None = None) -> ValidationOutcome:
    text = (candidate_identifier or "").strip()

    reject, reason = pre_filter(text)
    if reject:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=reason)

    low = text.lower()
    if any(w in low for w in _PC_HARDWARE_WORDS):
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_PC_HARDWARE)

    if low in {"zenfone", "rog phone", "rog"}:
        return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_FAMILY_NAME_WITHOUT_MODEL)

    m = _PHONE_RE.match(text)
    if m:
        return ValidationOutcome(
            outcome=VALID,
            candidate_identifier=text,
            normalized_identifier=text,
            manufacturer="asus",
            marketing_name=text,
            family=m.group(1).title(),
        )

    if low.startswith(("zenfone", "rog phone")):
        return ValidationOutcome(outcome=AMBIGUOUS, candidate_identifier=text, reason="unrecognized_asus_format")

    return ValidationOutcome(outcome=INVALID, candidate_identifier=text, reason=REASON_INVALID_PREFIX)
