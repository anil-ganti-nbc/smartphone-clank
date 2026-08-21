"""Small cross-process locks for one-shot production collectors.

The source lock is non-blocking: a duplicate invocation of the same source
exits while the owner continues.  The execution lock is blocking: different
source timers remain independently visible/runnable, but serialize the full
collector transaction because the current SQLite/pipeline design has not
proved cross-source concurrent writes safe.

Lock files are persistent names; ownership is the kernel lock, not file
existence.  A crashed process therefore cannot leave a stale live lock.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import IO, Any

if os.name == "nt":
    _windows_lock: Any = __import__("msvcrt")

_WINDOWS_LOCK_OFFSET = 1 << 20


class FileLock:
    def __init__(self, path: Path):
        self.path = path
        self._file: IO[str] | None = None

    def acquire(self, *, blocking: bool) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            if os.name == "nt":  # pragma: no cover - exercised on Windows hosts
                # Lock outside the JSON metadata range. Windows denies reads and
                # writes that overlap another handle's locked byte, which made a
                # second contender fail before it could block or return False.
                handle.seek(_WINDOWS_LOCK_OFFSET)
                mode = _windows_lock.LK_LOCK if blocking else _windows_lock.LK_NBLCK
                try:
                    _windows_lock.locking(handle.fileno(), mode, 1)
                except OSError:
                    handle.close()
                    return False
            else:
                import fcntl

                operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
                try:
                    fcntl.flock(handle.fileno(), operation)
                except BlockingIOError:
                    handle.close()
                    return False

            handle.seek(0)
            handle.truncate()
            handle.write(json.dumps({
                "pid": os.getpid(),
                "host": socket.gethostname(),
            }, sort_keys=True))
            handle.flush()
            self._file = handle
            return True
        except Exception:
            handle.close()
            raise

    def release(self) -> None:
        if self._file is None:
            return
        handle = self._file
        self._file = None
        try:
            if os.name == "nt":  # pragma: no cover - exercised on Windows hosts
                handle.seek(_WINDOWS_LOCK_OFFSET)
                _windows_lock.locking(handle.fileno(), _windows_lock.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> "FileLock":
        if not self.acquire(blocking=True):  # blocking acquisition only fails on OS error
            raise RuntimeError(f"could not acquire lock: {self.path}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def lock_directory(database_url: str) -> Path:
    override = os.environ.get("CLANK_LOCK_DIR")
    if override:
        return Path(override).resolve()
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("CLANK_LOCK_DIR is required for a non-file SQLite database")
    database = Path(database_url[len(prefix):]).resolve()
    return database.parent / ".locks"


def safe_lock_name(source_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in source_id)
    if not safe or safe != source_id:
        raise ValueError(f"unsafe source id for lock name: {source_id!r}")
    return safe
