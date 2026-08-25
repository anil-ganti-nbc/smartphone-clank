"""Runtime-wiring regression tests for the samsung_us_owners_product soak path.

Covers DEFECT 1 (no operational route reached build_staging_targets) and the
environment/DB-path fencing. Offline only: no real HTTP, Discord, or production
database is touched; the real settings files are read to exercise the genuine
builder environment guards, but no writes occur.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

import runtime.run_once as run_once
from runtime.environment import EnvironmentMismatchError


def _load(config_file: str):
    from config.settings import load_settings

    return load_settings(f"config/{config_file}")


def test_staging_build_includes_soak_collector():
    settings = _load("config.staging.yaml")
    targets = run_once.build_staging_targets(settings, None, None)
    ids = {t.source_id for t in targets}
    assert "samsung_us_owners_product" in ids


def test_production_build_excludes_soak_collector():
    settings = _load("config.yaml")  # production DB path
    targets = run_once.build_targets(settings, None, None)
    ids = {t.source_id for t in targets}
    assert "samsung_us_owners_product" not in ids


def test_staging_builder_rejects_production_db_path():
    settings = _load("config.yaml")  # production DB path
    with pytest.raises(EnvironmentMismatchError):
        run_once.build_staging_targets(settings, None, None)


def test_production_builder_rejects_staging_db_path():
    settings = _load("config.staging.yaml")  # staging DB path
    with pytest.raises(EnvironmentMismatchError):
        run_once.build_targets(settings, None, None)


def test_canonical_staging_command_routes_to_soak_builder(monkeypatch):
    """DEFECT 1 regression: --environment staging must actually invoke the
    soak builder (and never build_targets)."""
    calls = {"staging": 0, "production": 0}

    class FakeTarget:
        source_id = "samsung_us_owners_product"
        interval_minutes = 180

        def run(self):
            return None

    def fake_staging(*a, **k):
        calls["staging"] += 1
        return [FakeTarget()]

    def fake_production(*a, **k):
        calls["production"] += 1
        return []

    monkeypatch.setattr(run_once, "build_staging_targets", fake_staging)
    monkeypatch.setattr(run_once, "build_targets", fake_production)
    monkeypatch.setattr("database.schema_guard.ensure_schema_or_refuse", lambda *a, **k: None)
    monkeypatch.setattr("database.session.get_session_factory", lambda *a, **k: None)
    monkeypatch.setattr("pipeline.IntelligencePipeline", lambda *a, **k: None)
    monkeypatch.setattr(run_once, "run_target", lambda *a, **k: "ran")

    rc = run_once.main(
        ["--environment", "staging", "--collector", "samsung_us_owners_product", "--force"]
    )
    assert rc == run_once.EXIT_OK
    assert calls["staging"] == 1
    assert calls["production"] == 0


def test_production_default_does_not_use_soak_builder(monkeypatch):
    calls = {"staging": 0, "production": 0}

    class FakeTarget:
        source_id = "samsung_us_support_sitemap"
        interval_minutes = 180

        def run(self):
            return None

    def fake_staging(*a, **k):
        calls["staging"] += 1
        return []

    def fake_production(*a, **k):
        calls["production"] += 1
        return [FakeTarget()]

    monkeypatch.setattr(run_once, "build_staging_targets", fake_staging)
    monkeypatch.setattr(run_once, "build_targets", fake_production)
    monkeypatch.setattr("database.schema_guard.ensure_schema_or_refuse", lambda *a, **k: None)
    monkeypatch.setattr("database.session.get_session_factory", lambda *a, **k: None)
    monkeypatch.setattr("pipeline.IntelligencePipeline", lambda *a, **k: None)
    monkeypatch.setattr(run_once, "run_target", lambda *a, **k: "ran")

    rc = run_once.main(["--collector", "samsung_us_support_sitemap", "--force"])
    assert rc == run_once.EXIT_OK
    assert calls["production"] == 1
    assert calls["staging"] == 0


def test_unknown_collector_fails_closed(monkeypatch):
    """An unknown --collector (incl. a soak id under production) returns the
    unknown-collector exit code; no soak target is silently created."""
    monkeypatch.setattr("database.schema_guard.ensure_schema_or_refuse", lambda *a, **k: None)
    monkeypatch.setattr("database.session.get_session_factory", lambda *a, **k: None)
    monkeypatch.setattr("pipeline.IntelligencePipeline", lambda *a, **k: None)

    class FakeTarget:
        source_id = "samsung_us_support_sitemap"
        interval_minutes = 180

        def run(self):
            return None

    monkeypatch.setattr(run_once, "build_targets", lambda *a, **k: [FakeTarget()])
    monkeypatch.setattr(run_once, "run_target", lambda *a, **k: "ran")

    rc = run_once.main(["--collector", "samsung_us_owners_product", "--force"])
    assert rc == run_once.EXIT_UNKNOWN_COLLECTOR


def test_soak_source_notification_suppressed_regardless_of_enabled_config():
    """Enabling a soak source in config must never flip it notification-eligible.
    The gate is maturity-driven, not config-driven (fail-closed)."""
    from alerts.source_maturity import notifications_allowed

    from collectors.samsung_owners import SamsungOwnersCollector

    # sanity: the source still reports soak maturity
    assert SamsungOwnersCollector.maturity == "soak"
    assert notifications_allowed("samsung_us_owners_product") is False
