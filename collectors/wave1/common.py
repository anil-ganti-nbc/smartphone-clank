"""
Shared rejection heuristics for Wave 1 OEM validators.

These are intentionally coarse and shared across OEMs — they catch the *shape*
of the August 2026 garbage (sentences, nav/cookie/promo chrome, non-phone
product lines) before an OEM validator even gets to its own identifier regex.
Each OEM validator still owns its own strict identifier grammar; this module
only pre-filters obviously-not-a-model-number input so that logic isn't
duplicated four times.
"""

from __future__ import annotations

import re

from collectors.wave1.validator import (
    REASON_AUDIO_PRODUCT,
    REASON_CASE,
    REASON_CHARGER,
    REASON_CONTAINS_SENTENCE,
    REASON_COOKIE_TEXT,
    REASON_EMPTY,
    REASON_KNOWN_ACCESSORY,
    REASON_NAVIGATION_TEXT,
    REASON_PROMOTION_TEXT,
    REASON_SOFTWARE_NAME,
    REASON_TABLET_NOT_PHONE,
    REASON_TOO_LONG,
    REASON_WATCH_NOT_PHONE,
)

MAX_CANDIDATE_LENGTH = 40

_WATCH_WORDS = ("watch",)
_TABLET_WORDS = ("tablet", "pad")
_AUDIO_WORDS = ("buds", "earphone", "earbud", "headphone", "ear (", " ear ", "ear)")
_CHARGER_WORDS = ("charger", "charging", "adapter", "power brick", "hypercharge combo", "supervooc charger")
_CASE_WORDS = ("case", "cover", "bumper", "sleeve")
_SOFTWARE_WORDS = ("os ", "oxygenos", "coloros", "hyperos", "miui", "android 1", "nothing os")
_NAV_WORDS = ("skip to main content", "shop the collection", "compare all", "shop now", "shop the", "explore the")
_COOKIE_WORDS = ("cookie", "cookies")
_PROMO_WORDS = (
    "exclusive offer", "trade in", "free case", "sign up", "newsletter",
    "get 10%", "save big", "receive an", "buy pixel", "pre-order",
)
_SENTENCE_STOPWORDS = {
    "and", "the", "with", "your", "you", "for", "to", "a", "is", "are",
    "built", "designed", "so", "focus", "every", "single", "day", "on",
    "today", "now", "browsing", "enhance", "experience", "site", "by",
    "continuing", "agree", "our", "use", "of", "also", "available", "see",
    "sold", "separately", "required", "receive", "when", "trade", "current",
    "phone.", "phones.", "get", "free", "select", "accessories.",
}


def _contains_any(text_lower: str, words: tuple[str, ...]) -> bool:
    return any(w in text_lower for w in words)


def pre_filter(candidate: str) -> tuple[bool, str | None]:
    """
    Returns (should_reject, reason). If should_reject is False, the caller's
    OEM-specific identifier grammar still has the final say — this only
    rejects, it never confirms VALID.
    """
    text = (candidate or "").strip()
    if not text:
        return True, REASON_EMPTY
    if len(text) > MAX_CANDIDATE_LENGTH:
        return True, REASON_TOO_LONG

    lower = text.lower()

    if _contains_any(lower, _COOKIE_WORDS):
        return True, REASON_COOKIE_TEXT
    if _contains_any(lower, _PROMO_WORDS):
        return True, REASON_PROMOTION_TEXT
    if _contains_any(lower, _NAV_WORDS):
        return True, REASON_NAVIGATION_TEXT
    if _contains_any(lower, _WATCH_WORDS):
        return True, REASON_WATCH_NOT_PHONE
    if _contains_any(lower, _TABLET_WORDS):
        return True, REASON_TABLET_NOT_PHONE
    if _contains_any(lower, _AUDIO_WORDS):
        return True, REASON_AUDIO_PRODUCT
    if _contains_any(lower, _CHARGER_WORDS):
        return True, REASON_CHARGER
    if _contains_any(lower, _CASE_WORDS):
        return True, REASON_CASE
    if _contains_any(lower, _SOFTWARE_WORDS):
        return True, REASON_SOFTWARE_NAME

    words = re.findall(r"[A-Za-z']+", lower)
    stopword_hits = sum(1 for w in words if w in _SENTENCE_STOPWORDS)
    if stopword_hits >= 2 or len(words) > 6:
        return True, REASON_CONTAINS_SENTENCE

    return False, None
