"""Truthful source revision identity for native-checkout runtimes."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def source_revision(root: Path) -> str:
    configured = os.environ.get("CLANK_SOURCE_REVISION", "").strip().lower()
    if configured:
        return configured if _FULL_SHA.fullmatch(configured) else "unknown"
    try:
        revision = subprocess.run(
            ["git", "-c", f"safe.directory={root}", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip().lower()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return revision if _FULL_SHA.fullmatch(revision) else "unknown"
