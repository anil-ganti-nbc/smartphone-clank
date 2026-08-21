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


def test_dashboard_collection_endpoint_is_disabled_outside_field_test(tmp_path):
    from fastapi.testclient import TestClient
    from dashboard.app import create_app
    from database.schema_guard import init_fresh_database

    database_url = f"sqlite:///{tmp_path / 'clank.db'}"
    init_fresh_database(database_url)
    client = TestClient(create_app(database_url))

    assert client.get("/api/local-collection/status").status_code == 404
    assert client.post(
        "/api/local-collection/run", json={"source_id": "google_store_category_phones"}
    ).status_code == 403


def test_dashboard_collection_endpoint_fails_closed_with_controller(tmp_path):
    from fastapi.testclient import TestClient
    from dashboard.app import create_app
    from database.schema_guard import init_fresh_database

    database_url = f"sqlite:///{tmp_path / 'clank-controller.db'}"
    init_fresh_database(database_url)
    client = TestClient(create_app(database_url, collection_controller=object()))
    response = client.post(
        "/api/local-collection/run", json={"source_id": "google_store_category_phones"}
    )
    assert response.status_code == 403


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
