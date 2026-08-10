"""
The integration bridge: Wave1 DiscoveryAdapter output -> the same normalized
Discovery type Samsung's collectors already emit, so it flows through the one
shared entity_resolution/evidence/confidence/alert pipeline (spec section 3-4:
no parallel OEM pipelines).

Deliberately narrow. This module does not resolve entities, does not touch
confidence, and does not decide alert eligibility — it only normalizes shape
and preserves provenance. Everything after Discovery is already shared code.
"""

from __future__ import annotations

from models.schemas import Discovery, Manufacturer, SourceType

from collectors.wave1.adapter import DiscoveryResult
from collectors.wave1.validator import VALID, ValidationOutcome

# Discovery.manufacturer is a strict enum (models/schemas.py) shared with
# Samsung. CMF is a real brand our Nothing adapter can surface (spec section
# 12/39 explicitly defers the CMF schema decision rather than requiring it
# solved here) — a candidate manufacturer outside this set is not silently
# coerced into an existing enum value or "unknown" (which could collide with
# a genuinely different unknown-manufacturer candidate later). It is instead
# rejected with an explicit, inspectable reason — see normalize_wave1_discovery.
_SUPPORTED_MANUFACTURERS = {m.value for m in Manufacturer}

UNSUPPORTED_MANUFACTURER = "unsupported_manufacturer_pending_schema_decision"


class UnsupportedManufacturerError(ValueError):
    """Raised when a candidate's manufacturer has no Manufacturer enum member yet."""


def normalize_wave1_discovery(candidate: DiscoveryResult, outcome: ValidationOutcome) -> Discovery:
    """
    Build a normalized Discovery from a VALID Wave1 candidate + its validation
    outcome. Callers must check `outcome.outcome == VALID` and
    `candidate.manufacturer in _SUPPORTED_MANUFACTURERS` before calling this —
    it raises rather than guessing if either precondition is violated, since a
    silent fallback here is exactly the class of mistake this project is
    trying to permanently rule out.
    """
    if outcome.outcome != VALID:
        raise ValueError(f"cannot normalize a non-VALID outcome: {outcome.outcome} ({outcome.reason})")
    manufacturer_str = (outcome.manufacturer or candidate.manufacturer or "").lower()
    if manufacturer_str not in _SUPPORTED_MANUFACTURERS:
        raise UnsupportedManufacturerError(manufacturer_str)

    identifier = outcome.normalized_identifier or outcome.candidate_identifier

    # Conservative, documented evidence weight (spec section 18): Wave1
    # sources are official storefront/sitemap pages, structurally the same
    # tier as Samsung's own support-page discovery, not a confirmed press
    # announcement — SourceType.OFFICIAL/"official_announcement" (weight 100
    # in config/config.yaml) would be a wildly aggressive first-sighting
    # weight for a single storefront page. SUPPORT_PAGE (weight 10, same as
    # Samsung's new-page baseline weight) is the conservative, consistent
    # choice until source-specific weights are deliberately tuned later.
    return Discovery(
        manufacturer=Manufacturer(manufacturer_str),
        model_number=identifier,
        marketing_name=outcome.marketing_name,
        codename=None,  # Wave1 sources do not expose codenames (see docs/wave1/*_recon.md) — never invented
        region=candidate.region,
        source=candidate.source,
        source_type=SourceType.SUPPORT_PAGE,
        url=candidate.canonical_url or candidate.source_url,
        published_at=None,  # unknown — Wave1 sources don't expose publish timestamps
        raw={
            "source_url": candidate.source_url,
            "canonical_url": candidate.canonical_url,
            "raw_reference": candidate.raw_reference,
            "source_metadata": candidate.source_metadata,
            "validator_family": outcome.family,
            "wave1": True,
        },
        content_hash=None,
        discovered_at=candidate.discovered_at,
    )
