"""v0.3.7 traversal, resight, metrics unit tests (fixture / in-memory)."""
from __future__ import annotations
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, SitemapProductUrl, SitemapTraversalState, Device, Evidence
from collectors.samsung.sitemap_discovery import DiscoveredURL, normalize_url
from collectors.samsung import traversal as trav
from entity_resolution.resolver import EntityResolver
from models.schemas import Discovery, Manufacturer, SourceType


def _session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_oldest_checked_first_advances_beyond_first_batch():
    sess = _session()
    urls = [
        DiscoveredURL(url=f"https://www.samsung.com/us/support/mobile/phones/galaxy-a/galaxy-a{i:02d}/",
                      origin_type="sitemap", origin_source="s", product_slug=f"galaxy-a{i:02d}", series="galaxy-a")
        for i in range(1, 31)
    ]
    trav.sync_sitemap_urls(sess, urls)
    batch1 = trav.select_urls_to_fetch(sess, budget=10)
    assert len(batch1) == 10
    for r in batch1:
        trav.record_attempt(sess, r, http_status=200, result="FETCH_SUCCESS_MODEL_FOUND", model="SM-A015")
    sess.commit()
    batch2 = trav.select_urls_to_fetch(sess, budget=10, min_refetch_hours=12)
    # second batch should be different URLs (never attempted remain first)
    ids1 = {r.normalized_url for r in batch1}
    ids2 = {r.normalized_url for r in batch2}
    assert ids1.isdisjoint(ids2), (ids1, ids2)
    assert len(batch2) == 10
    print("advance batch ok")


def test_failed_url_backoff_skips():
    sess = _session()
    u = DiscoveredURL(url="https://www.samsung.com/us/support/mobile/phones/galaxy-a/galaxy-x/",
                      origin_type="sitemap", origin_source="s", product_slug="galaxy-x", series="galaxy-a")
    trav.sync_sitemap_urls(sess, [u])
    row = sess.query(SitemapProductUrl).first()
    trav.record_attempt(sess, row, http_status=500, result="FETCH_HTTP_ERROR", failed_retry_minutes=180)
    sess.commit()
    selected = trav.select_urls_to_fetch(sess, budget=5)
    assert row.normalized_url not in {r.normalized_url for r in selected}
    print("backoff ok")


def test_resight_no_new_evidence():
    sess = _session()
    r = EntityResolver(sess, weights={"support_page": 10})
    d = Discovery(
        manufacturer=Manufacturer.SAMSUNG,
        model_number="SM-A015",
        source="samsung_us_support_sitemap",
        source_type=SourceType.SUPPORT_PAGE,
        url="https://example.com/a01/",
    )
    dev1, is_new1, ev1 = r.resolve(d)
    assert is_new1 and ev1
    n_ev = sess.query(Evidence).count()
    conf = dev1.confidence
    ls1 = dev1.last_seen
    # second sighting same url
    import time
    time.sleep(0.01)
    dev2, is_new2, ev2 = r.resolve(d)
    assert not is_new2 and not ev2
    assert sess.query(Evidence).count() == n_ev
    assert dev2.last_seen >= ls1
    print("resight ok")


def test_coverage_report():
    sess = _session()
    urls = [
        DiscoveredURL(url=f"https://www.samsung.com/us/support/mobile/phones/galaxy-a/p{i}/",
                      origin_type="sitemap", origin_source="s", product_slug=f"p{i}", series="galaxy-a")
        for i in range(5)
    ]
    trav.sync_sitemap_urls(sess, urls)
    for r in trav.select_urls_to_fetch(sess, budget=3):
        trav.record_attempt(sess, r, http_status=200, result="FETCH_SUCCESS_MODEL_FOUND", model="SM-A015")
    rep = trav.coverage_report(sess)
    assert rep["sitemap_phone_urls"] == 5
    assert rep["ever_attempted"] == 3
    assert rep["never_attempted"] == 2
    print("coverage", rep)


def test_http_metrics_on_fixture_sitemap():
    from collectors.samsung.sitemap_discovery import SamsungSitemapDiscovery
    d = SamsungSitemapDiscovery(max_product_fetches=2, fixtures_dir=str(ROOT / "fixtures" / "samsung"))
    stats = d.discover(use_fixture_sitemap=True, max_fetches=2)
    assert stats.pages_requested >= 1
    assert stats.pages_fetched >= 1
    assert stats.bytes_downloaded > 0
    print("http metrics", stats.pages_requested, stats.pages_fetched, stats.bytes_downloaded)


if __name__ == "__main__":
    test_oldest_checked_first_advances_beyond_first_batch()
    test_failed_url_backoff_skips()
    test_resight_no_new_evidence()
    test_coverage_report()
    test_http_metrics_on_fixture_sitemap()
    print("ALL v0.3.7 tests passed")
