"""The Windows launcher must import the project from a source checkout.

Python seeds sys.path[0] with the *script's* directory, so running
`python native\windows\launcher.py` put native/windows on the path and not
the repo root. The launcher therefore died with

    ModuleNotFoundError: No module named 'config'

and worked only when frozen, where PyInstaller flattens every module into
_MEIPASS -- or when an operator supplied PYTHONPATH from outside.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "native" / "windows" / "launcher.py"


def _run(code: str, env_extra=None):
    import os

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True, text=True, env=env, cwd=str(Path.home()),
    )


def test_launcher_puts_the_repo_root_on_sys_path_without_pythonpath():
    """Runs from an unrelated cwd with PYTHONPATH scrubbed -- the exact
    conditions the .cmd launcher previously had to paper over."""
    out = _run(f"""
        import runpy, sys
        src = r"{LAUNCHER}"
        code = open(src, encoding="utf-8").read().split("def main(")[0]
        ns = {{"__file__": src, "__name__": "launcher_probe"}}
        exec(compile(code, src, "exec"), ns)
        print("ROOT_ON_PATH", str(ns["resource_root"]()) in sys.path)
        import config.settings
        print("CONFIG_IMPORTED", config.settings.__name__)
    """)
    assert out.returncode == 0, out.stderr
    assert "ROOT_ON_PATH True" in out.stdout
    assert "CONFIG_IMPORTED config.settings" in out.stdout


def test_resource_root_is_the_checkout_when_not_frozen():
    out = _run(f"""
        import sys
        src = r"{LAUNCHER}"
        code = open(src, encoding="utf-8").read().split("def main(")[0]
        ns = {{"__file__": src, "__name__": "launcher_probe"}}
        exec(compile(code, src, "exec"), ns)
        print("ROOT", ns["resource_root"]())
    """)
    assert out.returncode == 0, out.stderr
    assert f"ROOT {REPO}" in out.stdout


def test_frozen_execution_still_resolves_meipass(tmp_path):
    """The fix must not regress the packaged path."""
    fake = tmp_path / "_MEI42"
    fake.mkdir()
    out = _run(f"""
        import sys
        sys._MEIPASS = r"{fake}"
        src = r"{LAUNCHER}"
        code = open(src, encoding="utf-8").read().split("def main(")[0]
        ns = {{"__file__": src, "__name__": "launcher_probe"}}
        exec(compile(code, src, "exec"), ns)
        print("ROOT", ns["resource_root"]())
        print("ON_PATH", r"{fake}" in sys.path)
    """)
    assert out.returncode == 0, out.stderr
    assert f"ROOT {fake}" in out.stdout
    assert "ON_PATH True" in out.stdout


def test_sys_path_insert_is_idempotent():
    """Re-executing the module must not keep prepending the same root."""
    out = _run(f"""
        import sys
        src = r"{LAUNCHER}"
        code = open(src, encoding="utf-8").read().split("def main(")[0]
        for _ in range(3):
            ns = {{"__file__": src, "__name__": "launcher_probe"}}
            exec(compile(code, src, "exec"), ns)
        root = str(ns["resource_root"]())
        print("COUNT", sys.path.count(root))
    """)
    assert out.returncode == 0, out.stderr
    assert "COUNT 1" in out.stdout
