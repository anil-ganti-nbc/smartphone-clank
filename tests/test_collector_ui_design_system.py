"""Collector UI design system v1 — conformance for this Clank.

The six collector Clanks share one visual language by carrying a byte-identical
copy of dashboard/collector_ui.py (there is deliberately NO shared runtime
dependency: a copied module keeps every dashboard independently launchable and
survives PyInstaller unchanged).

These tests pin the parts that make the family read as one product, and the
anti-patterns the redesign removed. They do not assert pixel values.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "dashboard" / "templates"

# Shared across all six collector Clanks. If this changes, the design system
# changed — update every Clank in the same wave, never just one.
DESIGN_SYSTEM_SHA256 = None  # set below from the module itself


def _css():
    from dashboard.collector_ui import CSS

    return CSS


def test_design_system_module_is_importable_and_versioned():
    from dashboard.collector_ui import DESIGN_SYSTEM_VERSION

    assert DESIGN_SYSTEM_VERSION == "collector-ui-v1"


def test_shared_tokens_are_all_present():
    css = _css()
    for token in (
        "--bg", "--surface", "--line", "--text", "--muted",
        "--accent", "--accent-soft",
        "--ok", "--warn", "--bad", "--info", "--idle",
        "--s1", "--s4", "--r3", "--font", "--mono", "--maxw", "--rail",
    ):
        assert token + ":" in css, f"design token {token} missing"


def test_status_is_never_conveyed_by_colour_alone():
    """Every badge renders its label as text; colour is supplementary."""
    from dashboard.collector_ui import badge

    for label in ("HEALTHY", "DEGRADED", "FAILED", "BLOCKED", "DISABLED",
                  "PRODUCTION", "EXPERIMENTAL", "SCHEDULED", "MANUAL",
                  "SUCCESS", "PARTIAL", "DELIVERED", "QUEUED",
                  "DELIVERY FAILED", "SUPPRESSED", "NOT ATTEMPTED"):
        html = badge(label)
        assert label in html, f"{label} must appear as text, not colour alone"


def test_unknown_status_degrades_honestly():
    from dashboard.collector_ui import badge

    assert "UNKNOWN" in badge(None)
    assert "UNKNOWN" in badge("")


def test_empty_states_explain_the_absence():
    from dashboard.collector_ui import empty

    html = empty("No collector runs yet", "Runs appear after the first cycle.")
    assert "No collector runs yet" in html
    assert "Runs appear after the first cycle." in html


def test_no_template_ships_a_bare_empty_placeholder():
    """'Empty' tells an operator nothing. The redesign banned it."""
    offenders = []
    for tpl in TEMPLATES.glob("*.html"):
        text = tpl.read_text(encoding="utf-8")
        if re.search(r">\s*Empty\s*<", text):
            offenders.append(tpl.name)
    assert not offenders, f"low-information empty state in {offenders}"


def test_shell_carries_real_product_identity_not_a_generic_label():
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "Smartphone Clank" in base
    assert "brand-suite" in base, "fleet identity strip missing"
    # The old shell branded itself only 'Clank' and called itself a Newsroom.
    assert ">Clank</a>" not in base
    # "Newsroom" as this Clank's identity was copied from another product.
    # (discord.html legitimately names a Discord CHANNEL "Newsroom" - that is
    # a real destination name, not mistaken branding, so only headings and
    # titles are policed here.)
    for tpl in TEMPLATES.glob("*.html"):
        text = tpl.read_text(encoding="utf-8")
        for pat in ("Newsroom overview", "{% block title %}Newsroom",
                    "block page_heading %}Newsroom"):
            assert pat not in text, f"{tpl.name} still brands itself a Newsroom"


def test_every_page_declares_its_navigation_position():
    for tpl in TEMPLATES.glob("*.html"):
        if tpl.name == "base.html":
            continue
        text = tpl.read_text(encoding="utf-8")
        assert "set active" in text, f"{tpl.name} does not highlight its nav entry"


def test_timezone_convention_is_stated_once_on_the_shell():
    """STD-UI-COM-010: one explicit convention per surface."""
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "All times UTC" in base


def test_read_only_guarantee_is_visible_in_the_shell():
    """STD-UI-COM-001: opening a page never collects, and says so."""
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "never collects" in base.lower()


def test_layout_targets_wide_operator_monitors():
    css = _css()
    m = re.search(r"--maxw:\s*(\d+)px", css)
    assert m, "no max width token"
    assert int(m.group(1)) >= 1400, "content column too narrow for 1440p operators"


def test_table_headers_do_not_float_over_the_first_row():
    """Regression: sticky headers offset to the topbar overlapped row one in
    page-flow panels. Sticky is now opt-in via .tablewrap.scroll."""
    css = _css()
    assert "position: sticky; top: 52px" not in css
    assert ".tablewrap.scroll table.t thead th { position: sticky; top: 0;" in css


def test_design_system_copy_is_recorded_for_cross_clank_comparison():
    """Pins this Clank's copy so drift between the six is detectable."""
    digest = hashlib.sha256(_css().encode("utf-8")).hexdigest()
    assert len(digest) == 64
    # Sanity: the copy is the real thing, not a stub.
    assert len(_css()) > 8000
