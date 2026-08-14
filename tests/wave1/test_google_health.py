from __future__ import annotations

from dataclasses import dataclass

from collectors.wave1.google.discovery import GoogleStoreDiscoveryAdapter


@dataclass
class Response:
    url: str
    text: str


VALID_CATEGORY = """
<html><body>
  <a href="/us/product/pixel_10">Pixel 10</a>
  <a href="/us/product/pixel_10_pro">Pixel 10 Pro</a>
</body></html>
"""

VALID_SITEMAP = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://store.google.com/us/product/pixel_10</loc></url>
  <url><loc>https://store.google.com/us/product/pixel_10_pro</loc></url>
</urlset>
"""


def adapter():
    return GoogleStoreDiscoveryAdapter(user_agent="test", min_delay=0)


def test_normal_catalogue_response_is_healthy(monkeypatch):
    source = adapter()
    monkeypatch.setattr(source, "_get", lambda url, metrics: Response(url, VALID_CATEGORY))
    results, metrics = source.discover()
    assert [r.candidate_identifier for r in results] == ["Pixel 10", "Pixel 10 Pro"]
    assert metrics.errors == []


def test_consent_redirect_uses_sitemap_and_remains_degraded(monkeypatch):
    source = adapter()
    responses = iter([
        Response("https://consent.google.com/ml?opaque=redacted", "<title>Before you continue</title>"),
        Response(source.SITEMAPS["us"], VALID_SITEMAP),
    ])
    monkeypatch.setattr(source, "_get", lambda url, metrics: next(responses))
    results, metrics = source.discover()
    assert [r.candidate_identifier for r in results] == ["Pixel 10", "Pixel 10 Pro"]
    assert any("unusable_response:consent_interstitial" in error for error in metrics.errors)
    assert all("opaque=" not in error for error in metrics.errors)


def test_valid_fetch_and_empty_fallback_is_unexpected_zero(monkeypatch):
    source = adapter()
    monkeypatch.setattr(source, "_get", lambda url, metrics: Response(url, "<html><body>no catalogue</body></html>"))
    results, metrics = source.discover()
    assert results == []
    assert any("unexpected_zero:category_parser" in error for error in metrics.errors)
    assert any("unexpected_zero:sitemap_parser" in error for error in metrics.errors)
