# Windows native symmetry

Windows packaging must wrap the same canonical Smartphone core/dashboard and
set `CLANK_DATA_DIR` to `%LOCALAPPDATA%\\Smartphone Clank`. It must not fork
business logic or bundle secrets/production state.

The eventual Windows launcher must mirror `native/macos/launcher.py`: honour
an explicit `CLANK_DATA_DIR`; otherwise use `%LOCALAPPDATA%\\Smartphone Clank`;
set an isolated local `CLANK_ENV_FILE`; initialise only a brand-new local
SQLite DB; open the loopback dashboard; and package templates, config, and
Alembic resources. No Windows binary or platform-specific business logic is
introduced in this macOS-only Stage A.
