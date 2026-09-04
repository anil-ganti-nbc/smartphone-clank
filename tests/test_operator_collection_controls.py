"""Explicit operator collection controls — the invariants that matter.

Two rules are in tension and BOTH are enforced here:

  * opening, refreshing, or polling the console never starts collection; and
  * an explicit operator action really does start exactly one collection run,
    through the canonical controller, against the same database the UI reads.

Every test in this module is deterministic and offline. The one seam that
would perform network I/O — ``runtime.run_once.run_target`` — is replaced with
a stub that records the invocation and writes the canonical rows a real run
writes, so persistence, run history and the Devices surface are exercised
end to end without a single outbound request.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "config.yaml"

# Loopback peer == local operator. TestClient's default client host is
# "testclient", which the authority check correctly rejects.
LOCAL_OPERATOR = ("127.0.0.1", 50000)

# Every GET an operator can reach from the shell. If a new page is added to
# the rail it belongs in this list, so "no collection on page load" keeps
# covering the whole console rather than the pages that existed in 2026.
READ_ONLY_ROUTES = (
    "/", "/devices", "/collect", "/metrics", "/health", "/discord", "/about",
    "/healthz", "/api/local-collection/status",
)


class SpyController:
    """Stands in for LocalCollectionController and counts every start()."""

    def __init__(self):
        self.start_calls = []
        self.sources_calls = 0
        self.database_url = "sqlite:///spy.db"
        self._state = {
            "state": "idle", "source_id": None, "source_label": None,
            "message": "Ready.", "started_at": None, "finished_at": None,
            "duration_seconds": None, "metrics": None, "run_id": None,
            "errors": [], "busy": False,
        }

    def snapshot(self):
        return dict(self._state)

    def sources(self):
        self.sources_calls += 1
        return [{
            "source_id": "google_store_category_phones", "label": "Google",
            "maturity": "production", "enabled": True, "interval_minutes": 45,
            "last_status": None, "last_started_at": None, "last_duration_ms": None,
            "last_run_id": None, "last_candidates": None, "last_new_devices": None,
        }]

    def start(self, source_id):
        self.start_calls.append(source_id)
        self._state.update(state="queued", source_id=source_id,
                           source_label="Google", busy=True)
        return True, self.snapshot()


@pytest.fixture
def spy_client(tmp_path):
    from dashboard.app import create_app
    from database.schema_guard import init_fresh_database

    database_url = f"sqlite:///{tmp_path / 'clank.db'}"
    init_fresh_database(database_url)
    controller = SpyController()
    app = create_app(database_url, collection_controller=controller)
    return TestClient(app, client=LOCAL_OPERATOR), controller


# --------------------------------------------------------------------------- F


def test_F_no_get_request_anywhere_in_the_console_invokes_the_collector(spy_client):
    """F: a GUI GET never invokes the collector — not once, on any page."""
    client, controller = spy_client

    for route in READ_ONLY_ROUTES:
        response = client.get(route)
        assert response.status_code == 200, f"{route} -> {response.status_code}"
        assert controller.start_calls == [], f"{route} started a collection run"

    # A refresh is just another GET, and repeating the whole sweep must not
    # accumulate a single run either.
    for route in READ_ONLY_ROUTES:
        client.get(route)
    assert controller.start_calls == []


def test_F_the_collect_page_ships_no_load_time_run_trigger():
    """The Collect page's script may POLL on load; it must never POST on load.

    Read as source rather than executed, because the guarantee has to hold for
    the file the operator's browser actually receives.
    """
    page = (ROOT / "dashboard" / "templates" / "collect.html").read_text(encoding="utf-8")
    assert "/api/local-collection/run" in page, "the page must offer a run control"
    # The only POST is inside the click handler.
    for trigger in ("DOMContentLoaded", "window.onload", "onload="):
        assert trigger not in page, f"collect.html wires a load-time hook: {trigger}"
    post_index = page.index('method: "POST"')
    click_index = page.index('addEventListener("click"')
    assert click_index < post_index, "the run POST is not inside the click handler"


# ------------------------------------------------------------------------- G/H


def test_G_an_explicit_run_invokes_the_canonical_controller(spy_client):
    """G: the POST reaches LocalCollectionController.start with that source."""
    client, controller = spy_client

    response = client.post(
        "/api/local-collection/run",
        json={"source_id": "google_store_category_phones"},
    )

    assert response.status_code == 202
    assert controller.start_calls == ["google_store_category_phones"]
    assert response.json()["source_id"] == "google_store_category_phones"


def test_H_exactly_one_run_per_explicit_action(spy_client):
    """H: one button press == one start(). No retry, no double dispatch."""
    client, controller = spy_client

    client.post("/api/local-collection/run",
                json={"source_id": "google_store_category_phones"})

    assert len(controller.start_calls) == 1

    # And the status poll the page performs afterwards adds nothing.
    for _ in range(5):
        client.get("/api/local-collection/status")
    assert len(controller.start_calls) == 1


# --------------------------------------------------------------------------- I


def _settings_for(tmp_path, monkeypatch):
    from config.settings import load_settings

    monkeypatch.setenv("CLANK_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CLANK_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("CLANK_LOCAL_CONFIG", str(tmp_path / "missing.yaml"))
    return load_settings(str(CONFIG))


def _real_controller(tmp_path, monkeypatch):
    """A REAL LocalCollectionController over a real (empty) local database."""
    from dashboard.local_collection import LocalCollectionController
    from database.schema_guard import init_fresh_database
    from database.session import get_session_factory, resolve_database_url
    from pipeline import IntelligencePipeline

    settings = _settings_for(tmp_path, monkeypatch)
    database_url = resolve_database_url(settings.database_url)
    init_fresh_database(database_url)
    session_factory = get_session_factory(database_url)
    pipeline = IntelligencePipeline(settings, session_factory)
    controller = LocalCollectionController(
        settings, session_factory, pipeline, project_root=ROOT,
        database_url=database_url,
    )
    return controller, database_url, session_factory


def test_I_a_busy_controller_refuses_a_duplicate_concurrent_run(tmp_path, monkeypatch):
    """I: while one run is in flight, a second explicit action is refused.

    The real controller is used; only the network-touching run_target seam is
    replaced, with a stub that blocks until the test releases it.
    """
    import runtime.run_once as run_once

    controller, _, _ = _real_controller(tmp_path, monkeypatch)

    entered = threading.Event()
    release = threading.Event()
    calls = []

    def blocking_run_target(target, session_factory, database_url, *, force):
        calls.append(target.source_id)
        entered.set()
        assert release.wait(timeout=30), "test did not release the stub run"
        return "ran"

    monkeypatch.setattr(run_once, "run_target", blocking_run_target)

    started, _ = controller.start("google_store_category_phones")
    assert started is True
    assert entered.wait(timeout=30), "the first run never started"
    assert controller.busy is True

    # Second explicit action while the first is still running.
    started_again, refusal = controller.start("nothing_products_sitemap")
    assert started_again is False
    assert refusal["error"] == "collection_already_running"
    assert refusal["source_id"] == "google_store_category_phones"

    release.set()
    _wait_for_idle(controller)
    assert controller.busy is False
    assert calls == ["google_store_category_phones"], "the refused run still executed"


def test_I_the_endpoint_reports_a_busy_controller_as_409(spy_client):
    client, controller = spy_client

    def refuse(source_id):
        return False, {"error": "collection_already_running", "state": "running"}

    controller.start = refuse
    response = client.post("/api/local-collection/run",
                           json={"source_id": "google_store_category_phones"})
    assert response.status_code == 409
    assert response.json()["error"] == "collection_already_running"


def test_I_an_out_of_scope_source_is_refused_as_a_bad_request(tmp_path, monkeypatch):
    """Default scope never silently widens: a canary/soak id is not runnable."""
    controller, _, _ = _real_controller(tmp_path, monkeypatch)

    started, refusal = controller.start("samsung_us_owners_product")

    assert started is False
    assert refusal["error"] == "source_not_allowed"
    assert "samsung_us_owners_product" not in refusal["allowed"]


def test_I_every_offered_source_holds_production_maturity(tmp_path, monkeypatch):
    """The Collect surface must not offer an experimental source by default."""
    from alerts.source_maturity import MATURITY_PRODUCTION

    controller, _, _ = _real_controller(tmp_path, monkeypatch)

    inventory = controller.sources()
    assert inventory, "no sources offered"
    for source in inventory:
        assert source["maturity"] == MATURITY_PRODUCTION, source["source_id"]
        assert source["enabled"] is True


# --------------------------------------------------------------------------- J


def test_J_dashboard_and_collector_resolve_the_same_database(tmp_path, monkeypatch):
    """J: the UI reads exactly the database the collector writes."""
    from dashboard.app import create_app
    from dashboard import app as dashboard_app

    controller, database_url, _ = _real_controller(tmp_path, monkeypatch)
    create_app(database_url, collection_controller=controller)

    assert str(dashboard_app._engine.url) == database_url
    assert controller.database_url == database_url
    assert Path(database_url.removeprefix("sqlite:///")).is_absolute()


def test_J_a_relative_configured_url_is_anchored_not_left_to_the_cwd(tmp_path, monkeypatch):
    """The historical split-brain: importing runtime.run_once chdirs to the
    repo root, so a CWD-relative sqlite URL could name two different files."""
    from database.session import resolve_database_url

    monkeypatch.chdir(tmp_path)
    from_elsewhere = resolve_database_url("sqlite:///./data/clank.db")
    monkeypatch.chdir(ROOT)
    from_repo_root = resolve_database_url("sqlite:///./data/clank.db")

    assert from_elsewhere == from_repo_root
    assert from_elsewhere == f"sqlite:///{(ROOT / 'data' / 'clank.db').resolve()}"
    # Absolute and non-sqlite URLs are never rewritten.
    absolute = f"sqlite:///{tmp_path / 'x.db'}"
    assert resolve_database_url(absolute) == absolute
    assert resolve_database_url("postgresql://h/db") == "postgresql://h/db"


# ------------------------------------------------------------------------- K/L


def _stub_a_successful_run(monkeypatch, session_factory, *, devices):
    """Replace the network seam with the canonical writes a real run performs."""
    import runtime.run_once as run_once
    from database.models import Device
    from observability.metrics import CollectorRunRecord

    recorded = {}

    def fake_run_target(target, factory, database_url, *, force):
        session = factory()
        try:
            started = datetime.utcnow()
            run = CollectorRunRecord(
                collector_name=target.source_id,
                source_name=target.source_id,
                started_at=started,
                finished_at=started + timedelta(seconds=3),
                duration_ms=3000,
                status="success",
                pages_requested=2, pages_fetched=2,
                http_requests=2, http_failures=0,
                candidates_found=len(devices), valid_devices=len(devices),
                new_devices=len(devices), evidence_added=len(devices),
                run_reason="field_test_manual",
            )
            session.add(run)
            for model_number, marketing in devices:
                session.add(Device(
                    model_number=model_number, manufacturer="google",
                    marketing_name=marketing, confidence=35,
                    first_seen=started, last_seen=started,
                ))
            session.commit()
            recorded["run_id"] = run.id
        finally:
            session.close()
        return "ran"

    monkeypatch.setattr(run_once, "run_target", fake_run_target)
    return recorded


def _wait_for_idle(controller, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not controller.busy:
            return
        time.sleep(0.05)
    raise AssertionError("collection did not finish")


def test_K_a_persisted_run_appears_in_run_history(tmp_path, monkeypatch):
    """K: what the run wrote is what Run History shows, via the real UI."""
    from dashboard.app import create_app

    controller, database_url, session_factory = _real_controller(tmp_path, monkeypatch)
    recorded = _stub_a_successful_run(monkeypatch, session_factory, devices=[])

    client = TestClient(
        create_app(database_url, collection_controller=controller),
        client=LOCAL_OPERATOR,
    )
    assert client.get("/metrics").status_code == 200
    assert "google_store_category_phones" not in client.get("/metrics").text

    assert client.post(
        "/api/local-collection/run",
        json={"source_id": "google_store_category_phones"},
    ).status_code == 202
    _wait_for_idle(controller)

    state = controller.snapshot()
    assert state["state"] == "success", state
    assert state["run_id"] == recorded["run_id"]
    assert state["duration_seconds"] is not None

    history = client.get("/metrics")
    assert history.status_code == 200
    assert "google_store_category_phones" in history.text
    assert recorded["run_id"][:8] in history.text

    detail = client.get(f"/metrics/runs/{recorded['run_id']}")
    assert detail.status_code == 200
    assert "google_store_category_phones" in detail.text

    # And the Collect surface reflects the same run, with a link to it.
    collect = client.get("/collect")
    assert collect.status_code == 200
    assert f"/metrics/runs/{recorded['run_id']}" in collect.text


def test_L_a_source_result_appears_on_the_devices_page(tmp_path, monkeypatch):
    """L: devices the run persisted are visible on Devices afterwards."""
    from dashboard.app import create_app

    controller, database_url, session_factory = _real_controller(tmp_path, monkeypatch)
    _stub_a_successful_run(
        monkeypatch, session_factory,
        devices=[("GX-9000", "Pixel Test 9"), ("GX-9001", "Pixel Test 9 Pro")],
    )

    client = TestClient(
        create_app(database_url, collection_controller=controller),
        client=LOCAL_OPERATOR,
    )
    before = client.get("/devices")
    assert before.status_code == 200
    assert "No devices observed yet" in before.text
    assert "GX-9000" not in before.text

    client.post("/api/local-collection/run",
                json={"source_id": "google_store_category_phones"})
    _wait_for_idle(controller)

    after = client.get("/devices")
    assert after.status_code == 200
    assert "GX-9000" in after.text
    assert "Pixel Test 9 Pro" in after.text
    assert "No devices observed yet" not in after.text

    # An empty database and an empty filter result are different statements.
    filtered = client.get("/devices", params={"q": "no-such-model"})
    assert "No device matches this filter" in filtered.text
    assert "No devices observed yet" not in filtered.text


# --------------------------------------------------------- copy accuracy (§5)


def test_the_console_no_longer_claims_to_be_permanently_read_only():
    templates = ROOT / "dashboard" / "templates"
    stale = (
        "Collection is read-only in this console",
        "Phase 0 dashboard is read-only",
        "collectors cannot be controlled here",
    )
    for tpl in templates.glob("*.html"):
        text = tpl.read_text(encoding="utf-8")
        for phrase in stale:
            assert phrase not in text, f"{tpl.name} still says: {phrase}"

    # The accurate half of the guarantee is preserved, on the shell.
    base = (templates / "base.html").read_text(encoding="utf-8")
    assert "never collects" in base.lower()


def test_the_collect_page_reuses_the_shared_design_system():
    """§6: new controls live inside the redesigned shell, not bolted onto it."""
    page = (ROOT / "dashboard" / "templates" / "collect.html").read_text(encoding="utf-8")
    assert 'extends "base.html"' in page
    assert 'set active = "collect"' in page
    for component in ("panel", "kpi", "badge", "btn", "tablewrap", "empty", "notice"):
        assert component in page, f"collect.html does not reuse .{component}"
    # No hand-rolled styling outside the design system.
    assert "<style" not in page

    base = (ROOT / "dashboard" / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'href="/collect"' in base, "Collect is not reachable from the rail"
