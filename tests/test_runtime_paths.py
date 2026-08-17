"""Regression coverage for the documented CLANK_DATA_DIR runtime boundary."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from config.settings import load_settings
from database.schema_guard import init_fresh_database


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "config.yaml"


@pytest.fixture(autouse=True)
def _restore_native_environment():
    names = (
        "CLANK_DATA_DIR", "CLANK_LOCK_DIR", "CLANK_ENV_FILE", "CLANK_LOCAL_CONFIG",
        "DISCORD_WEBHOOK_URL", "MAINTENANCE_DISCORD_WEBHOOK_URL",
        "STAGING_DISCORD_WEBHOOK_URL", "SMARTPHONE_FIELD_TEST_HOME",
    )
    before = {name: os.environ.get(name) for name in names}
    yield
    for name, value in before.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def _load_with_clean_env(monkeypatch):
    monkeypatch.delenv("CLANK_DATA_DIR", raising=False)
    monkeypatch.setenv("CLANK_ENV_FILE", str(ROOT / "tests" / "missing-field-test.env"))
    monkeypatch.setenv("CLANK_LOCAL_CONFIG", str(ROOT / "tests" / "missing-local-config.yaml"))
    return load_settings(str(CONFIG))


def test_default_database_path_is_unchanged(monkeypatch):
    settings = _load_with_clean_env(monkeypatch)
    assert settings.database_url == "sqlite:///./data/clank.db"


def test_explicit_data_dir_is_created_and_derives_db_path(monkeypatch, tmp_path):
    requested = tmp_path / "Application Support" / "Smartphone Clank"
    monkeypatch.setenv("CLANK_DATA_DIR", str(requested))
    monkeypatch.setenv("CLANK_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("CLANK_LOCAL_CONFIG", str(tmp_path / "missing.yaml"))

    settings = load_settings(str(CONFIG))

    database_url = settings.database_url
    assert requested.is_dir()
    assert database_url == f"sqlite:///{(requested / 'clank.db').resolve()}"


def test_configured_state_does_not_follow_current_working_directory(monkeypatch, tmp_path):
    state_dir = tmp_path / "field-state"
    elsewhere = tmp_path / "unrelated-working-directory"
    elsewhere.mkdir()
    monkeypatch.setenv("CLANK_DATA_DIR", str(state_dir))
    monkeypatch.setenv("CLANK_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("CLANK_LOCAL_CONFIG", str(tmp_path / "missing.yaml"))
    monkeypatch.chdir(elsewhere)

    assert load_settings(str(CONFIG)).database_url == f"sqlite:///{(state_dir / 'clank.db').resolve()}"
    assert not (elsewhere / "data").exists()


def test_dashboard_and_collector_use_the_same_configured_database(monkeypatch, tmp_path):
    state_dir = tmp_path / "field-state"
    monkeypatch.setenv("CLANK_DATA_DIR", str(state_dir))
    monkeypatch.setenv("CLANK_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("CLANK_LOCAL_CONFIG", str(tmp_path / "missing.yaml"))
    settings = load_settings(str(CONFIG))
    init_fresh_database(settings.database_url)

    from collectors.samsung.sitemap_collector import SamsungSitemapCollector
    from dashboard import app as dashboard_app

    dashboard_app.create_app(settings.database_url)
    assert str(dashboard_app._engine.url) == settings.database_url
    assert SamsungSitemapCollector(database_url=settings.database_url).database_url == settings.database_url
    assert dashboard_app.TEMPLATES.env.globals["runtime_identity"]["database_revision"] != "unstamped"


def test_native_launcher_uses_app_support_and_never_bundle_state(monkeypatch, tmp_path):
    launcher_path = ROOT / "native" / "macos" / "launcher.py"
    spec = importlib.util.spec_from_file_location("smartphone_macos_launcher", launcher_path)
    assert spec and spec.loader
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)

    monkeypatch.setattr(launcher.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.delenv("CLANK_DATA_DIR", raising=False)
    monkeypatch.delenv("CLANK_ENV_FILE", raising=False)

    state_dir = launcher.configure_field_test_runtime()
    bundle_dir = ROOT / "native" / "macos"

    assert state_dir == tmp_path / "home" / "Library" / "Application Support" / "Smartphone Clank"
    assert state_dir.is_dir()
    assert bundle_dir not in state_dir.parents
    assert "native/macos" not in str(state_dir)
    assert Path(__import__("os").environ["CLANK_ENV_FILE"]).parent == state_dir
    assert Path(__import__("os").environ["CLANK_LOCK_DIR"]).parent == state_dir


def test_native_launcher_refuses_inherited_state_and_delivery_env(monkeypatch, tmp_path):
    launcher_path = ROOT / "native" / "macos" / "launcher.py"
    spec = importlib.util.spec_from_file_location("smartphone_macos_launcher_isolation", launcher_path)
    assert spec and spec.loader
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)

    monkeypatch.setattr(launcher.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setenv("CLANK_DATA_DIR", str(tmp_path / "production-data"))
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.invalid/production")
    monkeypatch.setenv("MAINTENANCE_DISCORD_WEBHOOK_URL", "https://example.invalid/maintenance")

    state_dir = launcher.configure_field_test_runtime()

    assert state_dir == tmp_path / "home" / "Library" / "Application Support" / "Smartphone Clank"
    assert __import__("os").environ["CLANK_DATA_DIR"] == str(state_dir)
    assert __import__("os").environ["DISCORD_WEBHOOK_URL"] == ""
    assert __import__("os").environ["MAINTENANCE_DISCORD_WEBHOOK_URL"] == ""
