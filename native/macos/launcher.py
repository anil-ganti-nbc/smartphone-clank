"""Thin macOS wrapper for the existing local FastAPI/Jinja2 dashboard."""

from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

APP_NAME = "Smartphone Clank"


def resource_root() -> Path:
    """Return the source checkout or PyInstaller extraction directory."""
    if hasattr(sys, "_MEIPASS"):
        # In a macOS onedir .app, PyInstaller's Python runtime lives under
        # Contents/Frameworks while data files belong in Contents/Resources.
        # Resolving from the executable keeps templates/config out of the app
        # bundle's writable surface and works after Finder launches it.
        return Path(sys.executable).resolve().parents[1] / "Resources"
    return Path(__file__).resolve().parents[2]


def default_data_dir() -> Path:
    """macOS application-support location; no username is embedded."""
    return Path.home() / "Library" / "Application Support" / APP_NAME


def configure_field_test_runtime() -> Path:
    """Set safe state/env defaults without overriding an explicit choice."""
    data_dir = Path(os.environ.setdefault("CLANK_DATA_DIR", str(default_data_dir()))).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    # A source-checkout .env must never supply production credentials to a
    # native field test. An explicit CLANK_ENV_FILE still wins.
    os.environ.setdefault("CLANK_ENV_FILE", str(data_dir / "field-test.env"))
    return data_dir


def available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def initialise_local_database(database_url: str) -> None:
    """Initialise only an absent, local field-test database via the DB API."""
    if not database_url.startswith("sqlite:///"):
        raise RuntimeError("The native field-test launcher requires a SQLite CLANK_DATA_DIR database")
    db_path = Path(database_url.removeprefix("sqlite:///"))
    if db_path.exists():
        return
    from database.schema_guard import init_fresh_database
    init_fresh_database(database_url)


def main() -> None:
    configure_field_test_runtime()
    root = resource_root()
    revision_file = root / "metadata" / "revision.txt"
    if revision_file.exists():
        os.environ.setdefault("CLANK_BUILD_REVISION", revision_file.read_text(encoding="utf-8").strip())
    config_path = root / "config" / "config.yaml"
    if not config_path.exists():
        raise RuntimeError(f"Bundled configuration not found: {config_path}")
    from config.settings import load_settings
    settings = load_settings(str(config_path))
    initialise_local_database(settings.database_url)
    from dashboard.app import create_app
    import uvicorn
    port = available_loopback_port()
    url = f"http://127.0.0.1:{port}/"
    dashboard = create_app(settings.database_url)
    threading.Timer(0.35, webbrowser.open, args=(url,)).start()
    uvicorn.run(dashboard, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
