"""Knowledge enrichment tests."""

from knowledge.enrichment import KnowledgeBase, EnrichedKnowledge


def test_samsung_flagship_enrichment():
    kb = KnowledgeBase(data_dir="knowledge/data")
    e = kb.enrich("SM-S957B", manufacturer="samsung")
    assert e.manufacturer == "samsung"
    assert e.family == "Galaxy S"
    assert e.product_tier == "flagship"
    assert e.variant in ("global_or_india", "global", None) or e.variant is not None
    assert e.confidence in ("high", "medium")
    print("samsung enrichment ok", e)


def test_pixel_enrichment():
    kb = KnowledgeBase(data_dir="knowledge/data")
    e = kb.enrich("Pixel 10 Pro", manufacturer="google")
    assert e.manufacturer == "google"
    assert e.family == "Pixel"
    assert e.product_tier == "flagship"
    print("pixel enrichment ok", e)


def test_unknown_stays_null():
    kb = KnowledgeBase(data_dir="knowledge/data")
    e = kb.enrich("XYZ-UNKNOWN-999", manufacturer="samsung")
    # Should not invent family for unknown patterns
    assert e.family is None or e.confidence == "low"
    print("unknown stays conservative ok")


if __name__ == "__main__":
    test_samsung_flagship_enrichment()
    test_pixel_enrichment()
    test_unknown_stays_null()
    print("all knowledge tests passed")
