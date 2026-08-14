from pathlib import Path

from runtime.provenance import source_revision


def test_runtime_reports_checkout_revision(monkeypatch):
    monkeypatch.delenv("CLANK_SOURCE_REVISION", raising=False)
    revision = source_revision(Path(__file__).resolve().parents[1])
    assert len(revision) == 40
    assert all(ch in "0123456789abcdef" for ch in revision)


def test_invalid_configured_revision_is_never_fabricated(monkeypatch):
    monkeypatch.setenv("CLANK_SOURCE_REVISION", "not-a-sha")
    assert source_revision(Path.cwd()) == "unknown"
