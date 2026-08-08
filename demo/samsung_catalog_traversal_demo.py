"""Offline demo: multi-run catalog traversal."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base
from collectors.samsung.sitemap_discovery import DiscoveredURL
from collectors.samsung import traversal as trav

def run_demo() -> int:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    sess = sessionmaker(bind=eng)()
    urls = [
        DiscoveredURL(
            url=f"https://www.samsung.com/us/support/mobile/phones/galaxy-a/item-{i}/",
            origin_type="sitemap", origin_source="s",
            product_slug=f"item-{i}", series="galaxy-a",
        )
        for i in range(126)
    ]
    trav.sync_sitemap_urls(sess, urls)
    print(f"Synced {len(urls)} URLs")
    evidence_proxy = 0
    for run in range(1, 4):
        batch = trav.select_urls_to_fetch(sess, budget=60)
        print(f"Run {run}: selected {len(batch)}")
        for r in batch:
            trav.record_attempt(sess, r, http_status=200, result="FETCH_SUCCESS_MODEL_FOUND", model=f"SM-A{r.product_slug}")
            evidence_proxy += 1
        sess.commit()
        rep = trav.coverage_report(sess)
        print(f"  progress={rep['cycle_progress_pct']}% attempted={rep['ever_attempted']} never={rep['never_attempted']}")
    # restart simulation — new session same DB
    sess2 = sessionmaker(bind=eng)()
    batch = trav.select_urls_to_fetch(sess2, budget=60, min_refetch_hours=12)
    print(f"After 'restart': selected {len(batch)} (should be 0 if all attempted and within refetch window)")
    rep = trav.coverage_report(sess2)
    print("Final coverage:", rep)
    assert rep["ever_attempted"] == 126
    assert rep["never_attempted"] == 0
    print("PASS catalog traversal demo")
    return 0

if __name__ == "__main__":
    raise SystemExit(run_demo())
