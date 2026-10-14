"""TPR-19.6: nested config-store lock acquisition on one thread must not deadlock."""

from __future__ import annotations

from pathlib import Path
from threading import Thread

from deeper_dive.user_config import UserConfigStore


def _finishes(target: object, seconds: float = 5.0) -> bool:
    assert callable(target)
    worker = Thread(target=target, daemon=True)
    worker.start()
    worker.join(seconds)
    return not worker.is_alive()


def test_nested_lock_acquisition_completes(tmp_path: Path) -> None:
    store = UserConfigStore(tmp_path / "config.json")

    def nested() -> None:
        with store._locked():
            with store._locked():
                pass

    assert _finishes(nested), "nested _locked() deadlocked"


def test_load_and_save_inside_held_lock_complete(tmp_path: Path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(store.load())

    def inside_lock() -> None:
        with store._locked():
            config = store.load()
            store.save(config)

    assert _finishes(inside_lock), "load/save while holding the lock deadlocked"


def test_lock_is_released_after_nested_exit(tmp_path: Path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    other = UserConfigStore(tmp_path / "config.json")

    def sequence() -> None:
        with store._locked():
            with store._locked():
                pass
        # A different store instance (and thread-independent flock) must now be free.
        with other._locked():
            pass

    assert _finishes(sequence), "lock was not released after nested exit"
