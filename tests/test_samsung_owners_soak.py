"""samsung_us_owners_product (SOAK) collector + registry gating tests.

Offline only: HTTP is intercepted at BaseCollector.fetch level via fake
httpx responses. Covers healthy fetch, parser success, empty result,
duplicate model collapse, per-page failure isolation, total transport
failure, idempotent rerun hashes, first-seen != novelty (via pipeline
semantics asserted elsewhere; here we pin discovery determinism), and the
registry rules that keep a soak source out of production scheduling.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from collectors import (
    SOAK_SAMSUNG_SOURCE_IDS,
    build_collectors,
    production_scope,
)
from collectors.samsung import SamsungModelValidator
from collectors.samsung_owners import SamsungOwnersCollector


PAGE_HTML_TEMPLATE = """
<html><body>
<h1>Galaxy {name} Support</h1>
<div class="product-specs">Model: SM-{num}U</div>
<script>window.DATA = {{ modelCode: 'SM-{num}X' }};</script>
</body></html>
"""


def _page(slug: str, num: str) -> str:
    return PAGE_HTML_TEMPLATE.format(name=slug.replace("-", " ").title(), num=num)


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


def _collector_with(pages: dict[str, str | Exception], monkeypatch) -> SamsungOwnersCollector:
    collector = SamsungOwnersCollector()

    def fake_fetch(url, *args, **kwargs):
        slug = url.rsplit("/", 1)[-1]
        if slug not in pages:
            return FakeResponse("<html><body>missing</body></html>", status_code=404)
        payload = pages[slug]
        if isinstance(payload, Exception):
            raise payload
        return FakeResponse(payload)

    monkeypatch.setattr(collector, "fetch", fake_fetch)
    return collector


# -- parsing -------------------------------------------------------------------

def test_model_parser_extracts_codes_from_static_html():
    # Uses the canonical SamsungModelValidator shared by all Samsung collectors,
    # not a local regex. The regex previously capped the suffix at 10 chars and
    # silently dropped current 11-char codes.
    validator = SamsungModelValidator()
    html = _page("galaxy-s26", "S261")
    assert validator.find_candidates(html) == ["SM-S261U", "SM-S261X"]


def test_current_11_char_suffix_parses():
    """Regression for DEFECT 2: SM-S928ULBEXAA has 11 chars after 'SM-'.
    The old ``{4,10}`` cap matched nothing on the live page."""
    validator = SamsungModelValidator()
    page = """
    <html><body>
      <script>window.modelCode = 'SM-S928ULBEXAA';</script>
      <div>Galaxy S24 Ultra Model Number: SM-S928ULBEXAA</div>
    </body></html>
    """
    assert validator.find_candidates(page) == ["SM-S928ULBEXAA"]


def test_case_insensitive_and_embedded_in_json():
    validator = SamsungModelValidator()
    blob = '{"models":["sm-s921u","SM-S928ULBEXAA"],"note":"see sm-g991b"}'
    assert validator.find_candidates(blob) == ["SM-S921U", "SM-S928ULBEXAA", "SM-G991B"]


def test_overlong_garbage_is_rejected():
    """An exhaustively long 'SM-' string must not be scraped as a model."""
    validator = SamsungModelValidator()
    junk = "SM-" + "A" * 40
    assert validator.find_candidates(junk) == []


def test_malformed_sm_text_is_rejected():
    validator = SamsungModelValidator()
    assert validator.find_candidates("SM- AB1 and SM-- and SMM-1234 and SM-12!") == []


def test_healthy_fetch_discovers_models_across_pages(monkeypatch):
    pages = {
        "galaxy-s24-ultra": _page("galaxy-s24-ultra", "S928"),
        "galaxy-s24": _page("galaxy-s24", "S921"),
    }
    # Remaining seed paths exist but carry no SM- codes.
    for slug in SamsungOwnersCollector.SEED_PATHS:
        pages.setdefault(slug, "<html><body>no codes here</body></html>")
    collector = _collector_with(pages, monkeypatch)

    discoveries = collector.collect()
    models = sorted(d.model_number for d in discoveries)
    assert models == ["SM-S921U", "SM-S921X", "SM-S928U", "SM-S928X"]
    assert all(d.source == "samsung_us_owners_product" for d in discoveries)
    assert all(d.manufacturer.value == "samsung" for d in discoveries)
    assert all(d.raw["slug"] for d in discoveries)


def test_empty_pages_yield_zero_discoveries_without_error(monkeypatch):
    pages = {slug: "<html><body>nothing</body></html>" for slug in SamsungOwnersCollector.SEED_PATHS}
    collector = _collector_with(pages, monkeypatch)
    assert collector.collect() == []


def test_duplicate_model_across_pages_is_collapsed(monkeypatch):
    shared = _page("shared-device", "F946")
    pages = {slug: shared for slug in SamsungOwnersCollector.SEED_PATHS}
    collector = _collector_with(pages, monkeypatch)
    discoveries = collector.collect()
    assert [d.model_number for d in discoveries] == ["SM-F946U", "SM-F946X"]


# -- failure isolation -------------------------------------------------------------

def test_single_page_failure_is_isolated(monkeypatch):
    pages = {
        "galaxy-s24-ultra": RuntimeError("boom"),
        "galaxy-s24": _page("galaxy-s24", "S921"),
    }
    for slug in SamsungOwnersCollector.SEED_PATHS:
        pages.setdefault(slug, "<html><body>x</body></html>")
    collector = _collector_with(pages, monkeypatch)
    discoveries = collector.collect()
    assert [d.model_number for d in discoveries] == ["SM-S921U", "SM-S921X"]


def test_total_transport_failure_raises_source_failure(monkeypatch):
    pages = {slug: RuntimeError("connection refused") for slug in SamsungOwnersCollector.SEED_PATHS}
    collector = _collector_with(pages, monkeypatch)
    with pytest.raises(RuntimeError, match="transport-level source failure"):
        collector.collect()


# -- idempotency -----------------------------------------------------------------

def test_stable_rerun_produces_identical_discovery_hashes(monkeypatch):
    pages = {
        slug: (_page("galaxy-s24", "S921") if slug == "galaxy-s24" else "<html></html>")
        for slug in SamsungOwnersCollector.SEED_PATHS
    }
    one = _collector_with(pages, monkeypatch).collect()
    two = _collector_with(pages, monkeypatch).collect()
    assert sorted(d.content_hash or "" for d in one) == sorted(d.content_hash or "" for d in two)


# -- registry gating ---------------------------------------------------------------

def test_soak_set_is_empty_after_canary_promotion():
    """samsung_us_owners_product left the soak stage on 2026-08-30 (32 clean
    repeat cycles). The generic soak mechanism stays available (empty set)
    for future sources."""
    assert SOAK_SAMSUNG_SOURCE_IDS == set()


def test_canary_source_is_in_production_scope():
    """CANARY means real production execution: production_scope() includes the
    source (LIVE_VALIDATED in samsung_sources.yaml + runnable implementation),
    so the per-source production timer can run it. This is the deliberate,
    reviewed scope expansion — never a config flip."""
    from config.settings import load_settings

    settings = load_settings("config/config.yaml")
    scope = production_scope(settings, project_root=ROOT)
    assert scope is not None
    assert "samsung_us_owners_product" in scope
    assert SOAK_SAMSUNG_SOURCE_IDS & scope == set()


def test_canary_never_implies_notification_authority():
    """The heart of the canary contract: production execution WITHOUT
    notification authority. alerts/source_maturity.py still classifies the
    source soak (fail-closed, absent from PRODUCTION_SOURCES) and the canary
    allowlist must never overlap the production registry — full production
    requires the separate, reviewed edit to that module (Fleet Law 8)."""
    from alerts.source_maturity import (
        MATURITY_SOAK,
        PRODUCTION_SOURCES,
        notifications_allowed,
        source_maturity,
    )

    from collectors import CANARY_SAMSUNG_SOURCE_IDS

    assert CANARY_SAMSUNG_SOURCE_IDS & PRODUCTION_SOURCES == set()
    assert source_maturity("samsung_us_owners_product") == MATURITY_SOAK
    assert notifications_allowed("samsung_us_owners_product") is False


def test_production_build_registers_canary_collector():
    """Default build_collectors() (production path) registers the canary
    collector with maturity='canary'. The flag itself grants no delivery
    authority — suppression lives in alerts/discord.py's maturity gate."""

    class _Settings:
        def get(self, key, *args, **kwargs):
            default = kwargs.get("default")
            if key == "collectors":
                return {}
            if key == "production":
                return {"samsung_only": True}
            return default

    registry = build_collectors(_Settings(), project_root=ROOT)
    canary = [c for c in registry if c.name == "samsung_us_owners_product"]
    assert len(canary) == 1
    assert getattr(canary[0], "maturity") == "canary"
    assert getattr(canary[0], "validation_status") == "LIVE_VALIDATED"
    assert getattr(canary[0], "capability") == "discovery"


def test_soak_route_no_longer_registers_promoted_source_as_soak():
    """include_soak=True no longer registers the promoted source as soak (its
    soak stage concluded); the source appears — via the canary block — as
    canary. The class-level default maturity stays the conservative 'soak'."""

    class _Settings:
        def get(self, key, *args, **kwargs):
            default = kwargs.get("default")
            if key == "collectors":
                return {}
            if key == "production":
                return {"samsung_only": True}
            return default

    registry = build_collectors(_Settings(), project_root=ROOT, include_soak=True)
    owners = [c for c in registry if c.name == "samsung_us_owners_product"]
    assert len(owners) == 1
    assert getattr(owners[0], "maturity") == "canary"
    assert SamsungOwnersCollector.maturity == "soak"


def test_maturity_policy_keeps_soak_notifications_suppressed():
    """Defense in depth: even if a soak source's discoveries were processed
    somewhere with a live webhook configured, alerts/source_maturity.py
    suppresses newsroom delivery."""
    from alerts.source_maturity import notifications_allowed

    assert notifications_allowed("samsung_us_owners_product") is False
