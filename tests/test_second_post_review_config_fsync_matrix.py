"""Crash-durability fault injection through the real user configuration store.

These cases distinguish pre-publication failures (old bytes must survive)
from post-replace directory sync failures (new bytes are already visible).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.user_config import UserConfig, UserConfigError, UserConfigStore


def _pending_update(tmp_path: Path) -> tuple[UserConfigStore, UserConfig, bytes]:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={"research_policy": "off"}))
    candidate = store.load()
    candidate.defaults["research_policy"] = "useful"
    return store, candidate, store.path.read_bytes()


def _assert_old_bytes_and_no_owned_temps(
    store: UserConfigStore, original: bytes, tmp_path: Path
) -> None:
    assert store.path.read_bytes() == original
    assert UserConfigStore(store.path).load().defaults["research_policy"] == "off"
    assert not list(tmp_path.glob(".config.json.*.tmp"))


def test_data_fsync_failure_preserves_original_and_cleans_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, candidate, original = _pending_update(tmp_path)

    def fail_data_sync(_descriptor: int) -> None:
        raise OSError("injected data fsync failure")

    monkeypatch.setattr("deeper_dive.user_config.os.fsync", fail_data_sync)
    with pytest.raises(OSError, match="injected data fsync failure"):
        store.save(candidate)

    _assert_old_bytes_and_no_owned_temps(store, original, tmp_path)


def test_atomic_replace_failure_preserves_original_and_cleans_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, candidate, original = _pending_update(tmp_path)

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("injected atomic replace failure")

    monkeypatch.setattr("deeper_dive.user_config.os.replace", fail_replace)
    with pytest.raises(OSError, match="injected atomic replace failure"):
        store.save(candidate)

    _assert_old_bytes_and_no_owned_temps(store, original, tmp_path)


def test_post_replace_directory_sync_failure_reports_uncertain_durability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, candidate, original = _pending_update(tmp_path)

    def fail_directory_sync() -> None:
        raise OSError("injected directory fsync failure")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_sync_parent_directory", fail_directory_sync)
        with pytest.raises(OSError, match="injected directory fsync failure"):
            store.save(candidate)

    # A successful replace cannot be described as rolled back merely because
    # directory fsync failed; the caller must be able to retry explicitly.
    published = store.path.read_bytes()
    assert published != original
    assert json.loads(published)["defaults"]["research_policy"] == "useful"
    assert candidate._revision == UserConfigStore(store.path).load()._revision
    assert not list(tmp_path.glob(".config.json.*.tmp"))

    candidate.defaults["research_policy"] = "aggressive"
    store.save(candidate)
    assert UserConfigStore(store.path).load().defaults["research_policy"] == "aggressive"


@pytest.mark.parametrize(
    "broken_bytes",
    [
        b'{"defaults": ',
        b'{"schema_version":1,"defaults":{"research_policy":"invalid-mode"}}',
        b"\xff\xfe",
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
