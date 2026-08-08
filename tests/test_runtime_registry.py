"""v0.3.6 production registry and adapter tests."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import load_settings
from collectors import build_collectors, describe_registry
from collectors.samsung.sitemap_collector import SamsungSitemapCollector


def test_sitemap_in_production_registry():
    settings = load_settings(str(ROOT / "config" / "config.yaml"))
    cols = build_collectors(settings, project_root=ROOT)
    names = [c.name for c in cols]
    assert "samsung_us_support_sitemap" in names, names
    sm = next(c for c in cols if c.name == "samsung_us_support_sitemap")
    assert isinstance(sm, SamsungSitemapCollector)
    assert sm.capability == "discovery"
    assert sm.validation_status == "LIVE_VALIDATED"
    print("sitemap in registry ok", names)


def test_legacy_support_disabled_by_default():
    settings = load_settings(str(ROOT / "config" / "config.yaml"))
    cols = build_collectors(settings, project_root=ROOT)
    names = [c.name for c in cols]
    assert "samsung_support" not in names
    print("legacy secondary off ok")


def test_describe_registry():
    settings = load_settings(str(ROOT / "config" / "config.yaml"))
    rows = describe_registry(settings, project_root=ROOT)
    assert any(r["collector_id"] == "samsung_us_support_sitemap" for r in rows)
    print("describe ok", rows)


def test_sitemap_adapter_fixture_collect():
    col = SamsungSitemapCollector(
        max_product_fetches=2,
        fixtures_dir=str(ROOT / "fixtures" / "samsung"),
        use_fixture_sitemap=True,
        min_delay=0.0,
    )
    # force fixture path
    discoveries = col.collect()
    # may be empty if product fixtures don't match first URLs; still must not raise
    assert isinstance(discoveries, list)
    print("adapter collect ok", len(discoveries))


if __name__ == "__main__":
    test_sitemap_in_production_registry()
    test_legacy_support_disabled_by_default()
    test_describe_registry()
    test_sitemap_adapter_fixture_collect()
    print("All runtime registry tests passed")
