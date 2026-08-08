"""Offline production runtime registry demo."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import load_settings
from collectors import build_collectors, describe_registry

def run_demo() -> int:
    settings = load_settings(str(ROOT / "config" / "config.yaml"))
    rows = describe_registry(settings, project_root=ROOT)
    print("Production registry:")
    ok = False
    for r in rows:
        print(f"  PASS {r['collector_id']:32} {r['capability']:12} {r['validation_status']}")
        if r["collector_id"] == "samsung_us_support_sitemap":
            ok = True
    if not ok:
        print("FAIL: sitemap discovery missing from production registry")
        return 1
    print("PASS: samsung_us_support_sitemap registered for python main.py run")
    return 0

if __name__ == "__main__":
    raise SystemExit(run_demo())
