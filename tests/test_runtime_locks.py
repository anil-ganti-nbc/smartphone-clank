from __future__ import annotations

import threading
import time

from runtime.locks import FileLock, lock_directory, safe_lock_name


def test_same_source_duplicate_is_refused(tmp_path):
    path = tmp_path / "source-google.lock"
    owner = FileLock(path)
    duplicate = FileLock(path)
    assert owner.acquire(blocking=False) is True
    try:
        assert duplicate.acquire(blocking=False) is False
    finally:
        owner.release()
    assert duplicate.acquire(blocking=False) is True
    duplicate.release()


def test_different_source_waits_for_shared_execution_lock(tmp_path):
    path = tmp_path / "shared-execution.lock"
    owner = FileLock(path)
    waiter = FileLock(path)
    assert owner.acquire(blocking=True) is True
    acquired = threading.Event()

    def wait_for_lock():
        assert waiter.acquire(blocking=True) is True
        acquired.set()
        waiter.release()

    thread = threading.Thread(target=wait_for_lock)
    thread.start()
    time.sleep(0.05)
    assert not acquired.is_set()
    owner.release()
    thread.join(timeout=2)
    assert acquired.is_set()


def test_lock_directory_is_database_adjacent(tmp_path):
    database = tmp_path / "clank.db"
    assert lock_directory(f"sqlite:///{database}") == tmp_path / ".locks"


def test_source_ids_must_be_safe_file_names():
    assert safe_lock_name("google_store_category_phones") == "google_store_category_phones"
    try:
        safe_lock_name("../escape")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe source id was accepted")
