"""
test_v038_pollution_cannot_recur — release-blocking, permanent.

Proves the August 2026 contamination (docs/V038_PRODUCTION_REPORT_INVESTIGATION.md,
73 garbage rows from google_support/oneplus_support/nothing_support) cannot
recur through the Wave 1 validators.

Two independent proofs:

1. Replay the *actual old regex* (collectors/generic_support.py::OEM_CONFIG)
   against synthetic marketing pages built to match the real page shapes it
   targeted (fixtures/wave1/{google,oneplus}_marketing_page.html), confirming
   it really does extract garbage — then feed every extracted string through
   the new strict validator and assert none of it is accepted.

2. Feed the full negative fixture corpus (fixtures/wave1/*_invalid.json,
   reconstructed from the incident report's quoted examples — see
   fixtures/wave1/README.md) through each OEM's new validator.

Both must show: 0 VALID outcomes, rejection count > 0.

Scope note: this proves the validator layer rejects the incident's garbage
shapes. It does not yet prove 0 Device/Evidence/confidence/alert rows at the
database layer, because no Wave 1 adapter is wired into the shared
resolver/evidence/confidence pipeline yet (that requires collectors/wave1/*
adapters + a staging-safe bridge into entity_resolution, which is later Wave 1
work — see docs/wave1/WAVE1_REPORT.md). Once that bridge exists, extend this
test with a staging-DB assertion (0 devices, 0 evidence, 0 confidence_ledger
rows, 0 alerts) for the same inputs, per spec section 43. This test must not
be weakened or deleted to make that extension easier.
"""

from __future__ import annotations

import json
from pathlib import Path

from selectolax.parser import HTMLParser

from collectors.generic_support import OEM_CONFIG
from collectors.wave1.google.model_validator import validate as validate_google
from collectors.wave1.nothing.model_validator import validate as validate_nothing
from collectors.wave1.oneplus.model_validator import validate as validate_oneplus
from collectors.wave1.validator import VALID
from collectors.wave1.xiaomi.model_validator import validate as validate_xiaomi

FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures" / "wave1"

VALIDATORS = {
    "google": validate_google,
    "oneplus": validate_oneplus,
    "nothing": validate_nothing,
    "xiaomi": validate_xiaomi,
}

MARKETING_PAGES = ["google", "oneplus"]  # fixtures exist for these two


def _extract_with_old_regex(oem: str, html: str) -> list[str]:
    pattern = OEM_CONFIG[oem]["pattern"]
    tree = HTMLParser(html)
    text = tree.body.text() if tree.body else html
    return [m.strip() for m in pattern.findall(text)]


def test_old_regex_still_produces_garbage_on_fixture_pages():
    """Sanity check the fixture is realistic: the old code must still extract
    garbage from it, otherwise this test would trivially pass for the wrong
    reason (fixture too tame, not the validator doing real work)."""
    total_extracted = 0
    for oem in MARKETING_PAGES:
        html = (FIXTURES / f"{oem}_marketing_page.html").read_text(encoding="utf-8")
        extracted = _extract_with_old_regex(oem, html)
        assert extracted, f"fixture for {oem} produced no candidates at all — fixture is not realistic"
        total_extracted += len(extracted)
    assert total_extracted > 0



# The old regex mixes real model names in with garbage on the same page (that
# unpredictability is exactly why it was replaced). These are the strings
# extracted from fixtures/wave1/{google,oneplus}_marketing_page.html by
# collectors/generic_support.py's actual regex (verified in
# test_old_regex_still_produces_garbage_on_fixture_pages) that happen to be
# genuine, well-formed model/marketing names — the new validator is *correct*
# to accept these; a validator that rejected them too would be useless, not
# safe. Everything else the old regex extracts from those fixtures is
# incident-shaped garbage (sentences, nav/promo text, accessories) and must
# never validate.
KNOWN_GOOD_AMONG_OLD_REGEX_OUTPUT = {
    ("google", "Pixel 9 Pro XL"),
    ("google", "Pixel 9a"),
    ("oneplus", "OnePlus 13"),
    ("oneplus", "OnePlus 12"),
}


def test_old_regex_garbage_rejected_by_new_validators():
    unexpected_accepts = []
    expected_accepts_seen = set()
    rejections = []
    for oem in MARKETING_PAGES:
        html = (FIXTURES / f"{oem}_marketing_page.html").read_text(encoding="utf-8")
        candidates = _extract_with_old_regex(oem, html)
        validate = VALIDATORS[oem]
        for candidate in candidates:
            outcome = validate(candidate)
            key = (oem, candidate)
            if outcome.outcome == VALID:
                if key in KNOWN_GOOD_AMONG_OLD_REGEX_OUTPUT:
                    expected_accepts_seen.add(key)
                else:
                    unexpected_accepts.append(key)
            else:
                rejections.append((oem, candidate, outcome.reason))

    assert unexpected_accepts == [], (
        "old-regex garbage was accepted as VALID by a Wave 1 validator "
        f"(would recreate the August 2026 incident): {unexpected_accepts}"
    )
    assert expected_accepts_seen == KNOWN_GOOD_AMONG_OLD_REGEX_OUTPUT, (
        "the genuine model names embedded in the fixture pages should still "
        f"validate — got {expected_accepts_seen}, expected {KNOWN_GOOD_AMONG_OLD_REGEX_OUTPUT}"
    )
    assert len(rejections) > 0


def test_negative_fixture_corpus_rejected_by_every_oem():
    total_rejections = 0
    accepted = []
    for oem, validate in VALIDATORS.items():
        cases = json.loads((FIXTURES / f"{oem}_invalid.json").read_text(encoding="utf-8"))
        assert cases
        for case in cases:
            outcome = validate(case["text"])
            if outcome.outcome == VALID:
                accepted.append((oem, case["text"]))
            else:
                total_rejections += 1

    assert accepted == [], f"known-bad candidates were accepted as VALID: {accepted}"
    assert total_rejections > 0


def test_zero_devices_zero_evidence_zero_confidence_zero_alerts_at_validator_boundary():
    """
    The concrete spec-43 assertion, applied at the layer that currently
    exists: for the full incident-derived corpus, the number of candidates
    that would reach device/evidence/confidence/alert creation (i.e. VALID
    outcomes) is exactly zero, and every rejected candidate is inspectable
    (has a reason recorded) rather than silently dropped.
    """
    zero_valid = 0
    rejection_records = 0
    for oem, validate in VALIDATORS.items():
        cases = json.loads((FIXTURES / f"{oem}_invalid.json").read_text(encoding="utf-8"))
        for case in cases:
            outcome = validate(case["text"])
            assert outcome.candidate_identifier == case["text"]
            if outcome.outcome == VALID:
                zero_valid += 1
            else:
                assert outcome.reason, "rejected candidate must carry an inspectable reason"
                rejection_records += 1

    assert zero_valid == 0, "0 Device rows / 0 Evidence rows / 0 confidence entries / 0 newsroom alerts requires 0 VALID outcomes"
    assert rejection_records > 0
