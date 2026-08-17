"""Thin macOS wrapper for the existing local FastAPI/Jinja2 dashboard."""

from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser
import time
import urllib.request
from contextlib import contextmanager
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
    """Force isolated local state and remove inherited delivery credentials."""
    override = os.environ.get("SMARTPHONE_FIELD_TEST_HOME")
    data_dir = Path(override or default_data_dir()).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["CLANK_DATA_DIR"] = str(data_dir)
    os.environ["CLANK_LOCK_DIR"] = str(data_dir / "locks")
    os.environ["CLANK_ENV_FILE"] = str(data_dir / "field-test.env.disabled")
    os.environ["CLANK_LOCAL_CONFIG"] = str(data_dir / "config.local.disabled.yaml")
    for name in (
        "DISCORD_WEBHOOK_URL", "MAINTENANCE_DISCORD_WEBHOOK_URL",
        "STAGING_DISCORD_WEBHOOK_URL",
    ):
        os.environ[name] = ""
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


@contextmanager
def working_directory(path: Path):
    """Resolve bundled relative resources without leaving runtime state there."""
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def main() -> None:
    data_dir = configure_field_test_runtime()
    root = resource_root()
    revision_file = root / "metadata" / "revision.txt"
    if revision_file.exists():
        os.environ.setdefault("CLANK_BUILD_REVISION", revision_file.read_text(encoding="utf-8").strip())
    config_path = root / "config" / "config.yaml"
    if not config_path.exists():
        raise RuntimeError(f"Bundled configuration not found: {config_path}")
    os.environ["CLANK_CONFIG"] = str(config_path)
    # Never merge checkout/operator mutable config into the frozen field test.
    os.environ["CLANK_LOCAL_CONFIG"] = str(root / "metadata" / "field-test-no-local-config.yaml")
    from config.settings import load_settings
    settings = load_settings(str(config_path))
    # alembic.ini intentionally uses ``script_location = alembic``. Finder
    # supplies an arbitrary CWD, so resolve that read-only bundled resource
    # from Contents/Resources, then restore the original CWD immediately.
    with working_directory(root):
        initialise_local_database(settings.database_url)
    from database.session import get_session_factory
    from pipeline import IntelligencePipeline
    from dashboard.local_collection import LocalCollectionController
    session_factory = get_session_factory(settings.database_url)
    pipeline = IntelligencePipeline(settings, session_factory)
    controller = LocalCollectionController(
        settings, session_factory, pipeline, project_root=root,
    )
    from runtime.daemon import setup_runtime_logging
    setup_runtime_logging(data_dir / "logs", os.environ.get("CLANK_LOG_LEVEL", "INFO"))
    from dashboard.app import create_app
    import uvicorn
    port = available_loopback_port()
    url = f"http://127.0.0.1:{port}/"
    dashboard = create_app(settings.database_url, collection_controller=controller)
    def open_when_ready() -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url + "healthz", timeout=1) as response:
                    if response.status == 200:
                        webbrowser.open(url)
                        return
            except Exception:
                time.sleep(0.15)
    threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run(dashboard, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
