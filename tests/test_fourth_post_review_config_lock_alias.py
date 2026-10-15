"""FPR-16: lock re-entrancy follows the real file, not the spelling of its path."""

from __future__ import annotations

import os
import time
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

import pytest

from deeper_dive.user_config import UserConfigStore


def _finishes(target: object, seconds: float = 5.0) -> bool:
    assert callable(target)
    worker = Thread(target=target, daemon=True)
    worker.start()
    worker.join(seconds)
    return not worker.is_alive()


def test_dotdot_alias_nests_without_deadlock(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    direct = UserConfigStore(tmp_path / "config.json")
    alias = UserConfigStore(tmp_path / "sub" / ".." / "config.json")

    def nested() -> None:
        with direct._locked(), alias._locked():
            pass

    assert _finishes(nested), "aliased nested _locked() deadlocked"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_symlinked_directory_alias_nests_without_deadlock(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    direct = UserConfigStore(real / "config.json")
    alias = UserConfigStore(tmp_path / "link" / "config.json")

    def nested() -> None:
        with direct._locked(), alias._locked():
            pass

    assert _finishes(nested), "symlink-aliased nested _locked() deadlocked"


def test_other_threads_wait_while_an_alias_holds_the_lock(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    direct = UserConfigStore(tmp_path / "config.json")
    alias = UserConfigStore(tmp_path / "sub" / ".." / "config.json")
    holding, release, acquired = Event(), Event(), Event()

    def holder() -> None:
        with direct._locked(), alias._locked():
            holding.set()
            release.wait(5)

    def waiter() -> None:
        holding.wait(5)
        with alias._locked():
            acquired.set()

    threads = [Thread(target=holder, daemon=True), Thread(target=waiter, daemon=True)]
    for thread in threads:
        thread.start()
    assert holding.wait(5)
    time.sleep(0.3)
    assert not acquired.is_set(), "a second thread entered while the lock was held"
    release.set()
    for thread in threads:
        thread.join(5)
    assert acquired.is_set()


def test_handle_is_closed_even_if_unlock_raises(tmp_path: Path) -> None:
    import fcntl

    store = UserConfigStore(tmp_path / "config.json")
    closed: list[bool] = []
    real_open = store._open_advisory_lock

    def tracking_open():  # type: ignore[no-untyped-def]
        handle = real_open()
        original_close = handle.close

        def close() -> None:
            closed.append(True)
            original_close()

        handle.close = close  # type: ignore[method-assign]
        return handle

    real_flock = fcntl.flock

    def failing_unlock(fd: int, operation: int) -> None:
        if operation == fcntl.LOCK_UN:
            raise OSError("unlock failed")
        real_flock(fd, operation)

    with (
        patch.object(store, "_open_advisory_lock", tracking_open),
        patch("deeper_dive.user_config.fcntl.flock", failing_unlock),
        pytest.raises(OSError, match="unlock failed"),
        store._locked(),
    ):
        pass
    assert closed, "the lock handle leaked when LOCK_UN raised"
