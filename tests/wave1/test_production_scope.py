"""
Production-scope gate tests, accumulated across every OEM promotion
(Google/Nothing/OnePlus Wave 1 canaries, Motorola/Honor/Oppo Wave 2
canaries): a config typo enabling an unapproved OEM in production must
never bring it into production — only collectors.wave1.PRODUCTION_OEM_SCOPE
(alias WAVE1_PRODUCTION_SCOPE) can. See docs/wave1/PROMOTION_REPORT.md and
docs/wave2/OPPO_CANARY_REPORT.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from collectors.wave1 import WAVE1_PRODUCTION_SCOPE, build_wave1_production_collectors
from config.settings import load_settings


def _settings_with_wave1(wave1_cfg: dict):
    settings = load_settings("config/config.yaml")
    settings.raw["wave1"] = wave1_cfg
    return settings


def test_production_scope_is_seven_promoted_oems_only():
    assert WAVE1_PRODUCTION_SCOPE == {"google", "nothing", "oneplus", "motorola", "honor", "oppo", "realme"}
    for excluded in ("xiaomi", "vivo", "asus"):
        assert excluded not in WAVE1_PRODUCTION_SCOPE


def test_google_enabled_alone_is_returned():
    settings = _settings_with_wave1({"google": {"enabled": True, "max_fetches_per_run": 20}})
    out = build_wave1_production_collectors(settings)
    assert [a.manufacturer for a in out] == ["google"]


def test_nothing_enabled_alone_is_returned():
    settings = _settings_with_wave1({"nothing": {"enabled": True, "max_fetches_per_run": 20}})
    out = build_wave1_production_collectors(settings)
    assert [a.manufacturer for a in out] == ["nothing"]


def test_oneplus_enabled_alone_is_returned():
    settings = _settings_with_wave1({"oneplus": {"enabled": True, "max_fetches_per_run": 20}})
    out = build_wave1_production_collectors(settings)
    assert [a.manufacturer for a in out] == ["oneplus"]


def test_motorola_enabled_alone_is_returned():
    settings = _settings_with_wave1({"motorola": {"enabled": True, "max_fetches_per_run": 20}})
    out = build_wave1_production_collectors(settings)
    assert [a.manufacturer for a in out] == ["motorola"]


def test_honor_enabled_alone_is_returned():
    settings = _settings_with_wave1({"honor": {"enabled": True, "max_fetches_per_run": 20}})
    out = build_wave1_production_collectors(settings)
    assert [a.manufacturer for a in out] == ["honor"]


def test_oppo_enabled_alone_is_returned():
    settings = _settings_with_wave1({"oppo": {"enabled": True, "max_fetches_per_run": 20}})
    out = build_wave1_production_collectors(settings)
    assert [a.manufacturer for a in out] == ["oppo"]


def test_realme_enabled_alone_is_returned():
    settings = _settings_with_wave1({"realme": {"enabled": True, "max_fetches_per_run": 20}})
    out = build_wave1_production_collectors(settings)
    assert [a.manufacturer for a in out] == ["realme"]


def test_google_nothing_oneplus_motorola_enabled_together_is_returned():
    settings = _settings_with_wave1({
        "google": {"enabled": True},
        "nothing": {"enabled": True},
        "oneplus": {"enabled": True},
        "motorola": {"enabled": True},
    })
    out = build_wave1_production_collectors(settings)
    assert sorted(a.manufacturer for a in out) == ["google", "motorola", "nothing", "oneplus"]


def test_all_seven_production_oems_enabled_together_is_returned():
    settings = _settings_with_wave1({
        "google": {"enabled": True},
        "nothing": {"enabled": True},
        "oneplus": {"enabled": True},
        "motorola": {"enabled": True},
        "honor": {"enabled": True},
        "oppo": {"enabled": True},
        "realme": {"enabled": True},
    })
    out = build_wave1_production_collectors(settings)
    assert sorted(a.manufacturer for a in out) == ["google", "honor", "motorola", "nothing", "oneplus", "oppo", "realme"]


def test_config_typo_enabling_xiaomi_does_not_reach_production():
    """spec (OnePlus canary phase): even with all promoted OEMs' config
    enabled, accidentally flipping xiaomi to enabled must not bring it into
    the production registry — only WAVE1_PRODUCTION_SCOPE can. Xiaomi's
    source oscillated 200/403 during qualification (KEEP_STAGING)."""
    settings = _settings_with_wave1({
        "google": {"enabled": True},
        "nothing": {"enabled": True},
        "oneplus": {"enabled": True},
        "motorola": {"enabled": True},
        "honor": {"enabled": True},
        "oppo": {"enabled": True},
        "realme": {"enabled": True},
        "xiaomi": {"enabled": True},  # simulated typo/regression
    })
    out = build_wave1_production_collectors(settings)
    assert sorted(a.manufacturer for a in out) == ["google", "honor", "motorola", "nothing", "oneplus", "oppo", "realme"]
    assert "xiaomi" not in WAVE1_PRODUCTION_SCOPE


def test_config_typo_enabling_wave2_held_oems_does_not_reach_production():
    """Final pre-soak expansion mission: Oppo and Realme are now approved
    (PROMOTED, see docs/wave2/{OPPO,REALME}_CANARY_REPORT.md). Vivo/ASUS
    remain RESEARCH_MORE/REJECT — neither has an entry in
    PRODUCTION_OEM_SCOPE, so even a config typo enabling them cannot bring
    them into production."""
    settings = _settings_with_wave1({
        "google": {"enabled": True},
        "nothing": {"enabled": True},
        "oneplus": {"enabled": True},
        "motorola": {"enabled": True},
        "honor": {"enabled": True},
        "oppo": {"enabled": True},
        "realme": {"enabled": True},
        "vivo": {"enabled": True},    # simulated typo/regression
        "xiaomi": {"enabled": True},  # simulated typo/regression
        "asus": {"enabled": True},    # simulated typo/regression
    })
    out = build_wave1_production_collectors(settings)
    assert sorted(a.manufacturer for a in out) == ["google", "honor", "motorola", "nothing", "oneplus", "oppo", "realme"]
    for excluded in ("vivo", "xiaomi", "asus"):
        assert excluded not in WAVE1_PRODUCTION_SCOPE


def test_vivo_xiaomi_each_alone_cannot_reach_production():
    """Explicit one-at-a-time coverage — each of these enabled alone (no
    other OEM config) must still return nothing for that OEM specifically.
    (Oppo and Realme are covered by their own dedicated tests since each
    was promoted — see test_oppo_enabled_alone_is_returned,
    test_realme_enabled_alone_is_returned.)"""
    for oem in ("vivo", "xiaomi"):
        settings = _settings_with_wave1({oem: {"enabled": True}})
        out = build_wave1_production_collectors(settings)
        assert oem not in {a.manufacturer for a in out}, f"{oem} reached production despite being unapproved"


def test_tracked_config_yaml_matches_promoted_production_scope():
    """`config/config.yaml` is not an inert default — per
    `docs/infra/DEPLOYMENT_MODEL.md` it is copied byte-for-byte to the
    production tree as the actual deploy artifact. This test used to assert
    the tracked file activated zero wave1 collectors; that stopped being
    true the moment Google was promoted (2026-08-10) and the tracked file
    simply hadn't been kept in sync with the deployed prod copy since. The
    real invariant is that the tracked file's active wave1 set matches
    WAVE1_PRODUCTION_SCOPE exactly — not more, not less, not zero."""
    settings = load_settings("config/config.yaml")
    out = {a.manufacturer for a in build_wave1_production_collectors(settings)}
    assert out == WAVE1_PRODUCTION_SCOPE


def test_daemon_refuses_wave1_against_staging_looking_db(monkeypatch):
    from runtime.environment import assert_db_matches_environment, EnvironmentMismatchError, PRODUCTION

    with pytest.raises(EnvironmentMismatchError):
        assert_db_matches_environment("sqlite:///./data/clank-staging.db", PRODUCTION)


# ---------------------------------------------------------------------------
# Scope-unification phase: fail-closed startup invariant
# (docs/infra/PRODUCTION_SCOPE_AUDIT.md). Reproduces the exact Motorola
# incident — approved + adapter registered + config enabled, but omitted
# from settings.manufacturers — and proves it can no longer reach a
# successfully-validated production state.
# ---------------------------------------------------------------------------

def _settings_fully_configured(*, manufacturers=None, wave1_cfg=None):
    settings = load_settings("config/config.yaml")
    settings.raw["manufacturers"] = manufacturers if manufacturers is not None else [
        "samsung", "google", "oneplus", "nothing", "xiaomi", "motorola", "honor", "oppo", "realme",
    ]
    settings.raw["wave1"] = wave1_cfg if wave1_cfg is not None else {
        "google": {"enabled": True, "interval_minutes": 45},
        "nothing": {"enabled": True, "interval_minutes": 90},
        "oneplus": {"enabled": True, "interval_minutes": 90},
        "motorola": {"enabled": True, "interval_minutes": 360},
        "honor": {"enabled": True, "interval_minutes": 360},
        "oppo": {"enabled": True, "interval_minutes": 360},
        "realme": {"enabled": True, "interval_minutes": 360},
    }
    return settings


def test_fully_configured_production_scope_validates_ok():
    from collectors.wave1 import validate_production_scope

    settings = _settings_fully_configured()
    result = validate_production_scope(settings)
    assert result.ok, result.render()
    assert result.mismatches == []


def test_motorola_missing_from_manufacturers_is_caught_exactly_like_the_incident():
    """Reproduces docs/wave2/MOTOROLA_CANARY_REPORT.md's incident precisely:
    approved (in PRODUCTION_OEM_SCOPE), adapter registered, config enabled —
    but omitted from settings.manufacturers. Before this phase this state
    was invisible until a baseline silently completed with zero devices."""
    from collectors.wave1 import validate_production_scope, assert_production_scope_or_refuse, ProductionScopeError

    settings = _settings_fully_configured(
        manufacturers=["samsung", "google", "oneplus", "nothing", "xiaomi"],  # motorola OMITTED
    )
    result = validate_production_scope(settings)
    assert not result.ok
    motorola_status = next(s for s in result.statuses if s.oem == "motorola")
    assert motorola_status.approved is True
    assert motorola_status.manufacturer_configured is False
    assert motorola_status.adapter_registered is True
    assert motorola_status.config_enabled is True
    assert motorola_status.ok is False

    with pytest.raises(ProductionScopeError, match="motorola"):
        assert_production_scope_or_refuse(settings)


def test_approved_oem_missing_adapter_registration_is_caught():
    """A second way the invariant could break: approved in scope but with
    no ADAPTER_REGISTRY entry (shouldn't be possible in practice — every
    approved OEM has an adapter — but the check must not assume that)."""
    from collectors.wave1 import validate_production_scope, PRODUCTION_OEM_SCOPE, ADAPTER_REGISTRY

    settings = _settings_fully_configured()
    assert PRODUCTION_OEM_SCOPE <= set(ADAPTER_REGISTRY.keys()), (
        "sanity check: every currently-approved OEM has a registered adapter "
        "(if this fails, the scenario below is not simulated correctly)"
    )
    result = validate_production_scope(settings)
    assert result.ok


def test_unapproved_vivo_enabled_does_not_cause_scope_mismatch():
    """Vivo is RESEARCH_MORE, not approved — enabling it in config must
    not itself be flagged as a scope mismatch (it correctly just never
    schedules, per build_wave1_production_collectors); the validator's job
    is to protect *approved* OEMs' consistency, not to complain about
    unapproved OEMs sitting in config."""
    from collectors.wave1 import validate_production_scope

    settings = _settings_fully_configured(
        manufacturers=["samsung", "google", "oneplus", "nothing", "xiaomi", "motorola", "honor", "oppo", "realme", "vivo"],
        wave1_cfg={
            "google": {"enabled": True}, "nothing": {"enabled": True},
            "oneplus": {"enabled": True}, "motorola": {"enabled": True},
            "honor": {"enabled": True}, "oppo": {"enabled": True},
            "realme": {"enabled": True},
            "vivo": {"enabled": True},  # unapproved, even though fully "configured"
        },
    )
    result = validate_production_scope(settings)
    assert result.ok, result.render()
    # Vivo has no ADAPTER_REGISTRY entry, so it doesn't even appear in the
    # per-OEM statuses (it's neither approved nor a registered adapter) —
    # its presence in `manufacturers`/config is correctly inert either way.
    assert all(s.oem != "vivo" for s in result.statuses)


def test_production_validate_cli_exits_nonzero_on_mismatch(tmp_path, monkeypatch):
    """python main.py production validate must surface the exact mismatch
    and exit non-zero — see docs/infra/PRODUCTION_SCOPE_AUDIT.md Part 7."""
    import yaml
    from typer.testing import CliRunner
    from main import app

    config = yaml.safe_load(Path("config/config.yaml").read_text())
    config["manufacturers"] = ["samsung", "google", "oneplus", "nothing", "xiaomi"]  # motorola OMITTED
    config.setdefault("wave1", {})["motorola"] = {"enabled": True, "interval_minutes": 360}
    config["wave1"].setdefault("google", {"enabled": True})
    config["wave1"].setdefault("nothing", {"enabled": True})
    config["wave1"].setdefault("oneplus", {"enabled": True})
    cfg_path = tmp_path / "config_mismatch.yaml"
    cfg_path.write_text(yaml.safe_dump(config))

    runner = CliRunner()
    result = runner.invoke(app, ["production", "validate", "--config", str(cfg_path)])
    assert result.exit_code == 1
    assert "motorola" in result.output.lower() or "MISMATCH" in result.output


def test_daemon_refuses_startup_on_scope_mismatch(monkeypatch):
    """runtime/daemon.py::main() must call assert_production_scope_or_refuse
    before scheduling anything and return a nonzero exit code on mismatch —
    not degrade to a warning (docs/infra/PRODUCTION_SCOPE_AUDIT.md Part 4)."""
    import runtime.daemon as daemon_module

    settings = _settings_fully_configured(
        manufacturers=["samsung", "google", "oneplus", "nothing", "xiaomi"],  # motorola OMITTED
    )
    monkeypatch.setattr("config.settings.load_settings", lambda *a, **kw: settings)
    monkeypatch.setattr(daemon_module, "load_settings", lambda *a, **kw: settings, raising=False)

    from database.schema_guard import ensure_schema_or_refuse
    monkeypatch.setattr(daemon_module, "ensure_schema_or_refuse", lambda *a, **kw: None, raising=False)

    # main() imports load_settings/ensure_schema_or_refuse locally, so patch
    # at the source modules too.
    import config.settings as settings_module
    monkeypatch.setattr(settings_module, "load_settings", lambda *a, **kw: settings)
    import database.schema_guard as schema_guard_module
    monkeypatch.setattr(schema_guard_module, "ensure_schema_or_refuse", lambda *a, **kw: None)

    exit_code = daemon_module.main()
    assert exit_code == 1
