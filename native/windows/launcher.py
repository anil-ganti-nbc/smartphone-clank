"""Thin Windows wrapper for the existing local FastAPI/Jinja2 dashboard.

Mirrors native/macos/launcher.py: honours an explicit CLANK_DATA_DIR,
otherwise uses %LOCALAPPDATA%\\Smartphone Clank; sets an isolated local
CLANK_ENV_FILE; initialises only a brand-new local SQLite DB; scrubs any
inherited Discord/webhook delivery credentials as belt-and-suspenders (this
repo's config/settings.py reads DISCORD_WEBHOOK_URL and
MAINTENANCE_DISCORD_WEBHOOK_URL from the environment, so an ambient value
must never silently activate delivery in this read-mostly field-test
build); and opens the loopback dashboard. The dashboard itself is unchanged
from the checkout: bulk/GLOBAL collection stays hard-blocked (403) and only
the eight named SMARTPHONE_FIELD_TEST_SOURCES remain individually
triggerable via LocalCollectionController.start(source_id).
"""

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

# A frozen, console=False PyInstaller exe has no attached console, so
# sys.stdout/stderr are None -- uvicorn's default logging setup (which
# calls .isatty() on the configured stream via its ColourizedFormatter)
# crashes with AttributeError/ValueError before the server ever starts.
# Same failure mode found and fixed the same day in watch-clank's Windows
# launcher -- give both streams a real, discarding fallback before
# anything else (including uvicorn) can touch them.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

APP_NAME = "Smartphone Clank"


def resource_root() -> Path:
    """Return the source checkout or PyInstaller extraction directory."""
    if hasattr(sys, "_MEIPASS"):
        # Onefile Windows build: PyInstaller extracts everything (including
        # bundled datas) directly under _MEIPASS at runtime.
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


# Put the project root on sys.path so `config`, `dashboard`, `database`,
# `pipeline` and friends import when this file is run directly from a
# source checkout. Python seeds sys.path[0] with the SCRIPT's directory --
# native/windows -- not the repo, so without this the launcher dies on
# "ModuleNotFoundError: No module named 'config'" and only works frozen,
# where PyInstaller flattens every module into _MEIPASS. Idempotent, and
# it adds exactly one entry: the same root resource_root() already
# resolves for both execution modes.
_ROOT = str(resource_root())
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def default_data_dir() -> Path:
    """Windows per-user application data location; no username is embedded."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / APP_NAME


def configure_field_test_runtime() -> Path:
    """Force isolated local state and remove inherited delivery credentials."""
    override = os.environ.get("SMARTPHONE_FIELD_TEST_HOME")
    data_dir = Path(override or default_data_dir()).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["CLANK_DATA_DIR"] = str(data_dir)
    os.environ["CLANK_LOCK_DIR"] = str(data_dir / "locks")
    os.environ["CLANK_ENV_FILE"] = str(data_dir / "field-test.env.disabled")
    os.environ["CLANK_LOCAL_CONFIG"] = str(data_dir / "config.local.disabled.yaml")
    # Belt-and-suspenders: scrub any Discord/webhook/delivery/outbox env vars
    # inherited from the ambient shell so they can never silently activate
    # a delivery path in this read-mostly field-test build.
    for name in tuple(os.environ):
        if any(token in name.upper() for token in ("DISCORD", "WEBHOOK", "DELIVERY", "OUTBOX")):
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
    # alembic.ini intentionally uses ``script_location = alembic``. The
    # launch directory (desktop, Explorer double-click, etc.) is arbitrary,
    # so resolve that read-only bundled resource from the extraction root,
    # then restore the original CWD immediately.
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
