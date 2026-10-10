"""Restart recovery and non-POSIX-lock fallback regression tests.

Atomic-write failure injection lives in test_second_post_review_config_durability
and test_second_post_review_config_failure_matrix; avoid duplicating it here.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from deeper_dive.user_config import (
    UserConfig,
    UserConfigConflictError,
    UserConfigError,
    UserConfigStore,
)


@pytest.mark.parametrize(
    "broken_bytes",
    [
        b'{"defaults": ',
        b'{"schema_version":1,"defaults":{"research_policy":"invalid-mode"}}',
        b"\\xff\\xfe",
        b'{"schema_version":99,"defaults":{}}',
    ],
)
def test_restart_rejects_invalid_config_without_rewriting_bytes(
    tmp_path: Path, broken_bytes: bytes
) -> None:
    path = tmp_path / "config.json"
    path.write_bytes(broken_bytes)

    with pytest.raises(UserConfigError, match="invalid user configuration"):
        UserConfigStore(path).load()

    assert path.read_bytes() == broken_bytes
    assert not list(tmp_path.glob(".config.json.*.tmp"))


def test_stale_save_cannot_overwrite_corrupted_config_after_restart(
    tmp_path: Path,
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={"research_policy": "off"}))
    stale = store.load()
    stale.defaults["research_policy"] = "useful"
    corrupted = b'{"defaults":'

    store.path.write_bytes(corrupted)
    with pytest.raises(UserConfigConflictError, match="reload and retry"):
        store.save(stale)

    assert store.path.read_bytes() == corrupted
    with pytest.raises(UserConfigError, match="invalid user configuration"):
        UserConfigStore(store.path).load()


def test_without_fcntl_same_process_writers_still_conflict_and_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback guarantees in-process locking, not cross-process locking."""
    monkeypatch.setattr("deeper_dive.user_config.fcntl", None)
    path = tmp_path / "config.json"
    UserConfigStore(path).save(UserConfig())
    barrier = Barrier(2)

    def write(key: str, value: str) -> str:
        store = UserConfigStore(path)
        candidate = store.load()
        candidate.defaults[key] = value
        barrier.wait(timeout=10)
        try:
            store.save(candidate)
        except UserConfigConflictError:
            return "conflict"
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(write, "research_policy", "off")
        b = pool.submit(write, "network_policy", "local-only")
        assert sorted((a.result(), b.result())) == ["conflict", "saved"]

    reloaded = UserConfigStore(path).load()
    reloaded.defaults.update({"research_policy": "off", "network_policy": "local-only"})
    UserConfigStore(path).save(reloaded)
    assert UserConfigStore(path).load().defaults == {
        "research_policy": "off",
        "network_policy": "local-only",
    }
