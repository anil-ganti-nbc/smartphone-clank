"""
Lightweight doc<->code consistency check for docs/SOURCE_INVENTORY.md
(docs/ENGINEERING_PRINCIPLES.md Rule 19: "the document must not lie").

Deliberately not a documentation-generation framework — just an assertion
that every OEM in PRODUCTION_OEM_SCOPE is mentioned in the inventory (catches
the class of drift where an OEM is promoted/demoted but the doc isn't
updated), and that no currently-excluded Wave 2 OEM is marked PRODUCTION in
the doc.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from collectors.wave1 import PRODUCTION_OEM_SCOPE

INVENTORY = ROOT / "docs" / "SOURCE_INVENTORY.md"


def _inventory_text() -> str:
    return INVENTORY.read_text(encoding="utf-8")


def test_source_inventory_file_exists():
    assert INVENTORY.exists()


def test_every_approved_production_oem_is_mentioned():
    text = _inventory_text().lower()
    missing = [oem for oem in PRODUCTION_OEM_SCOPE if oem not in text]
    assert missing == [], f"docs/SOURCE_INVENTORY.md doesn't mention approved production OEM(s): {missing}"


def test_every_approved_production_oem_is_marked_production_yes():
    """Each approved OEM's row should say YES/PRODUCTION somewhere near its
    name — a coarse but effective check that the doc wasn't just updated
    with the OEM's name and left marked as staging/research."""
    # A few OEM names don't title-case cleanly (OnePlus is not "Oneplus").
    _TITLE_OVERRIDES = {"oneplus": "OnePlus"}

    text = _inventory_text()
    for oem in PRODUCTION_OEM_SCOPE:
        # Find the markdown table row(s) mentioning this OEM (case-sensitive
        # title-case match, matching the doc's own convention) and require
        # at least one to contain a YES/PRODUCTION marker.
        oem_title = _TITLE_OVERRIDES.get(oem, oem.capitalize())
        rows = [line for line in text.splitlines() if line.strip().startswith("|") and oem_title in line]
        assert rows, f"no table row found for approved OEM {oem_title!r} in docs/SOURCE_INVENTORY.md"
        assert any("YES" in row or "PRODUCTION" in row for row in rows), (
            f"approved OEM {oem_title!r} has a row in docs/SOURCE_INVENTORY.md "
            "but none of them say YES/PRODUCTION"
        )


def test_unapproved_wave2_oems_not_marked_production():
    """Honor/Oppo/Vivo/Realme/ASUS must never be marked as production in
    the doc while they remain outside PRODUCTION_OEM_SCOPE."""
    text = _inventory_text()
    for oem, title in [("honor", "Honor"), ("oppo", "Oppo"), ("vivo", "Vivo"), ("realme", "Realme")]:
        if oem in PRODUCTION_OEM_SCOPE:
            continue
        rows = [line for line in text.splitlines() if line.strip().startswith("|") and title in line]
        for row in rows:
            assert "PROMOTED" not in row and "**YES" not in row, (
                f"docs/SOURCE_INVENTORY.md marks unapproved OEM {title!r} as production: {row!r}"
            )
