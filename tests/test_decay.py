"""Confidence decay tests."""

from datetime import datetime, timedelta
from entity_resolution.decay import ConfidenceDecay


class FakeEvidence:
    def __init__(self, original, first_seen, source_type="certification", decays=True):
        self.original_weight = original
        self.confidence_contribution = original
        self.first_seen = first_seen
        self.source_type = source_type
        self.decays = decays


def test_decay_schedule():
    decay = ConfidenceDecay()
    now = datetime.utcnow()

    fresh = FakeEvidence(20, now)
    assert decay.apply_to_evidence(fresh, now=now) == 20

    old30 = FakeEvidence(20, now - timedelta(days=35))
    assert decay.apply_to_evidence(old30, now=now) == 18  # 0.9 * 20

    old90 = FakeEvidence(20, now - timedelta(days=100))
    assert decay.apply_to_evidence(old90, now=now) == 15  # 0.75 * 20

    old180 = FakeEvidence(20, now - timedelta(days=200))
    assert decay.apply_to_evidence(old180, now=now) == 10  # 0.5 * 20

    print("decay schedule ok")


def test_official_never_decays():
    decay = ConfidenceDecay()
    now = datetime.utcnow()
    official = FakeEvidence(100, now - timedelta(days=400), source_type="official", decays=False)
    assert decay.apply_to_evidence(official, now=now) == 100
    print("official never decays ok")


if __name__ == "__main__":
    test_decay_schedule()
    test_official_never_decays()
    print("all decay tests passed")
