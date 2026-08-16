# macOS field-test build

`Smartphone Clank.app` is a thin wrapper over the canonical dashboard/core. It
uses the documented `CLANK_DATA_DIR` contract and defaults to:

`~/Library/Application Support/Smartphone Clank/`

It never bundles `.env`, a SQLite database, or production credentials. The
launcher sets an isolated `CLANK_ENV_FILE` unless an operator explicitly
supplies one, opens a loopback-only dashboard, and initialises only a brand-new
local SQLite database. Existing local state is neither reset nor migrated.

For source-mode field testing:

```bash
export CLANK_DATA_DIR="$HOME/Library/Application Support/Smartphone Clank"
export CLANK_ENV_FILE="$CLANK_DATA_DIR/field-test.env"
python main.py dashboard --host 127.0.0.1 --port 8200
```

Build the app bundle with:

```bash
PYTHON="$(pwd)/.venv/bin/python" native/macos/build.sh
open "native/macos/dist/Smartphone Clank.app"
```

The PyInstaller definition packages the existing FastAPI/Jinja2 templates and
configuration; it does not replace the dashboard or collector runtime.
