"""Per-OEM validator unit tests: fixtures/wave1/{oem}_valid.json must all
pass VALID, fixtures/wave1/{oem}_invalid.json must never pass VALID."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("oem", sorted(VALIDATORS))
def test_valid_fixtures_pass(oem):
    validate = VALIDATORS[oem]
    cases = _load(f"{oem}_valid.json")
    assert cases, f"no valid fixtures for {oem}"
    for case in cases:
        outcome = validate(case["text"])
        assert outcome.outcome == VALID, f"{oem}: {case['text']!r} should be VALID, got {outcome.outcome} ({outcome.reason})"


@pytest.mark.parametrize("oem", sorted(VALIDATORS))
def test_invalid_fixtures_never_pass(oem):
    validate = VALIDATORS[oem]
    cases = _load(f"{oem}_invalid.json")
    assert cases, f"no invalid fixtures for {oem}"
    for case in cases:
        outcome = validate(case["text"])
        assert outcome.outcome != VALID, (
            f"{oem}: known-bad {case['text']!r} was accepted as VALID "
            f"(expected reason family: {case['reason']})"
        )
