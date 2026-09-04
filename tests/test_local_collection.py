from __future__ import annotations

from dashboard.local_collection import SMARTPHONE_FIELD_TEST_SOURCES


def test_field_test_source_scope_is_exact_and_excludes_legacy_sources():
    assert dict(SMARTPHONE_FIELD_TEST_SOURCES) == {
        "samsung_us_support_sitemap": "Samsung",
        "google_store_category_phones": "Google",
        "nothing_products_sitemap": "Nothing",
        "oneplus_regional_sitemap": "OnePlus",
        "motorola_regional_sitemap": "Motorola",
        "honor_global_sitemap": "Honor",
        "oppo_global_sitemap": "Oppo",
        "realme_regional_sitemap": "Realme",
    }
    forbidden = {"xiaomi", "vivo", "asus", "certification", "ota", "firmware"}
    rendered = " ".join(source for source, _ in SMARTPHONE_FIELD_TEST_SOURCES).lower()
    assert not any(value in rendered for value in forbidden)


def test_dashboard_collection_endpoint_is_unavailable_without_a_controller(tmp_path):
    """A dashboard started with no controller cannot collect, and says so.

    (Before explicit operator runs existed this asserted a blanket 403
    "Phase 0 dashboard is read-only". The console now supports an explicit,
    authorized run, so the honest answer when no controller is wired is
    "unavailable here" — 404 — not "forbidden".)
    """
    from fastapi.testclient import TestClient
    from dashboard.app import create_app
    from database.schema_guard import init_fresh_database

    database_url = f"sqlite:///{tmp_path / 'clank.db'}"
    init_fresh_database(database_url)
    client = TestClient(create_app(database_url), client=("127.0.0.1", 50000))

    assert client.get("/api/local-collection/status").status_code == 404
    response = client.post(
        "/api/local-collection/run", json={"source_id": "google_store_category_phones"}
    )
    assert response.status_code == 404
    assert response.json()["error"] == "local_collection_unavailable"


def test_dashboard_collection_endpoint_refuses_a_non_loopback_operator(tmp_path):
    """Fail closed on authority: a non-loopback peer never starts a run."""
    from fastapi.testclient import TestClient
    from dashboard.app import create_app
    from database.schema_guard import init_fresh_database

    class NeverCalled:
        def start(self, source_id):  # pragma: no cover - must not run
            raise AssertionError("a non-loopback caller reached the controller")

        def snapshot(self):
            return {"state": "idle"}

    database_url = f"sqlite:///{tmp_path / 'clank-controller.db'}"
    init_fresh_database(database_url)
    client = TestClient(
        create_app(database_url, collection_controller=NeverCalled()),
        client=("203.0.113.7", 41000),
    )
    response = client.post(
        "/api/local-collection/run", json={"source_id": "google_store_category_phones"}
    )
    assert response.status_code == 403
    assert response.json()["error"] == "local_operator_required"


def test_dashboard_collection_endpoint_refuses_an_unnamed_source(tmp_path):
    from fastapi.testclient import TestClient
    from dashboard.app import create_app
    from database.schema_guard import init_fresh_database

    class NeverCalled:
        def start(self, source_id):  # pragma: no cover - must not run
            raise AssertionError("an unnamed source reached the controller")

        def snapshot(self):
            return {"state": "idle"}

    database_url = f"sqlite:///{tmp_path / 'clank-unnamed.db'}"
    init_fresh_database(database_url)
    client = TestClient(
        create_app(database_url, collection_controller=NeverCalled()),
        client=("127.0.0.1", 50000),
    )
    assert client.post("/api/local-collection/run", json={}).status_code == 400


def test_dashboard_host_validation_is_fail_closed():
    from main import require_loopback_host

    for host in ("127.0.0.1", "::1", "localhost"):
        require_loopback_host(host)
    for host in ("0.0.0.0", "::", "192.168.1.20", "bad host", ""):
        try:
            require_loopback_host(host)
        except ValueError:
            continue
        raise AssertionError(f"unsafe host accepted: {host}")
