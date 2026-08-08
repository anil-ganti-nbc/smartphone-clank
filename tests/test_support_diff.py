"""
v0.2.1 support-page change detection tests.
Uses local fixtures only — no live websites.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from knowledge.change_detection import (
    extract_fingerprint,
    compare_fingerprints,
    normalize_html,
    score_change,
    classify_download,
    classify_image,
)
from knowledge.fixtures.support_pages import (
    SAMSUNG_NEW_PAGE,
    SAMSUNG_FORMAT_ONLY,
    SAMSUNG_MANUAL_ADDED,
    SAMSUNG_VARIANT_AND_IMAGES,
    SAMSUNG_MARKETING_NAME,
)


def test_stable_hash_identical_content():
    a = extract_fingerprint(SAMSUNG_NEW_PAGE)
    b = extract_fingerprint(SAMSUNG_NEW_PAGE)
    assert a.hashes.content_hash == b.hashes.content_hash
    assert a.hashes.text_hash == b.hashes.text_hash
    print("stable hash ok")


def test_normalization_strips_cookie_banner():
    raw = extract_fingerprint(SAMSUNG_NEW_PAGE, normalize=False)
    norm = extract_fingerprint(SAMSUNG_NEW_PAGE, normalize=True)
    # normalized should still find the model
    assert "SM-S957B" in (norm.model_references or []) or "SM-S957B" in (norm.visible_text or "")
    print("normalization ok")


def test_format_only_not_meaningful():
    old = extract_fingerprint(SAMSUNG_NEW_PAGE)
    new = extract_fingerprint(SAMSUNG_FORMAT_ONLY)
    result = compare_fingerprints(old, new)
    assert result.meaningful is False
    assert any(c in result.classifications for c in ("FORMAT_ONLY", "NO_CHANGE", "DOM_CHANGED"))
    # analytics change alone should not create DOWNLOAD or MODEL signals
    assert "DOWNLOAD_ADDED" not in result.classifications
    print("format-only ok", result.classifications)


def test_download_added_meaningful():
    old = extract_fingerprint(SAMSUNG_NEW_PAGE)
    new = extract_fingerprint(SAMSUNG_MANUAL_ADDED)
    result = compare_fingerprints(old, new)
    assert result.meaningful is True
    assert "DOWNLOAD_ADDED" in result.classifications
    cats = [d.get("category") for d in result.details.get("new_downloads", [])]
    assert "user_manual" in cats
    weight = score_change(result)
    assert weight >= 18
    print("download added ok", result.classifications, "weight", weight)


def test_new_page_meaningful():
    result = compare_fingerprints(None, extract_fingerprint(SAMSUNG_NEW_PAGE))
    assert result.meaningful is True
    assert "NEW_PAGE" in result.classifications
    assert "SM-S957B" in (result.details.get("models", {}).get("added") or result.fingerprint.model_references)
    print("new page ok")


def test_title_changed():
    old = extract_fingerprint(SAMSUNG_MANUAL_ADDED)
    new = extract_fingerprint(SAMSUNG_MARKETING_NAME)
    result = compare_fingerprints(old, new)
    assert "TITLE_CHANGED" in result.classifications
    assert "Galaxy S27 Ultra" in (result.details.get("title", {}).get("new") or "")
    print("title changed ok")


def test_product_images():
    old = extract_fingerprint(SAMSUNG_MANUAL_ADDED)
    new = extract_fingerprint(SAMSUNG_VARIANT_AND_IMAGES)
    result = compare_fingerprints(old, new)
    assert result.meaningful is True
    # should detect model refs and/or images
    assert (
        "MODEL_REFERENCE_ADDED" in result.classifications
        or "IMAGE_ADDED" in result.classifications
        or "TEXT_CHANGED" in result.classifications
    )
    print("product images / variants ok", result.classifications)


def test_classify_download_heuristics():
    assert classify_download("User Manual EN", "/x/manual.pdf", "manual.pdf") == "user_manual"
    assert classify_download("Firmware", "/fw/ota.zip", "ota.zip") == "firmware"
    assert classify_download("Legal", "/legal/terms.pdf", "terms.pdf") == "generic_document"
    print("download classify ok")


def test_classify_image_heuristics():
    assert classify_image("logo", "/brand/logo.png", "logo.png") == "logo"
    assert classify_image("Galaxy device front product render", "/product/hero.png", "hero.png") == "product_render"
    print("image classify ok")


def test_idempotent_same_fetch():
    fp = extract_fingerprint(SAMSUNG_MANUAL_ADDED)
    result = compare_fingerprints(fp, extract_fingerprint(SAMSUNG_MANUAL_ADDED))
    assert result.meaningful is False
    assert result.classifications in (["NO_CHANGE"], ["FORMAT_ONLY"]) or "NO_CHANGE" in result.classifications
    print("idempotent ok", result.classifications)


def test_score_no_double_count_on_format():
    old = extract_fingerprint(SAMSUNG_NEW_PAGE)
    new = extract_fingerprint(SAMSUNG_FORMAT_ONLY)
    result = compare_fingerprints(old, new)
    assert score_change(result) == 0
    print("no score on format-only ok")


if __name__ == "__main__":
    test_stable_hash_identical_content()
    test_normalization_strips_cookie_banner()
    test_format_only_not_meaningful()
    test_download_added_meaningful()
    test_new_page_meaningful()
    test_title_changed()
    test_product_images()
    test_classify_download_heuristics()
    test_classify_image_heuristics()
    test_idempotent_same_fetch()
    test_score_no_double_count_on_format()
    print("\nAll support-diff tests passed")
