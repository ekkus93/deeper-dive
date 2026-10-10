from __future__ import annotations

import os
from pathlib import Path

import pytest

from deeper_dive.user_config import (
    UserConfig,
    UserConfigConflictError,
    UserConfigError,
    UserConfigStore,
)


def test_user_config_save_uses_unique_temp_and_leaves_no_temp_files(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    fixed_canary = tmp_path / "config.json.tmp"
    fixed_canary.write_text("do-not-touch", encoding="utf-8")

    UserConfigStore(path).save(UserConfig(defaults={"research_policy": "useful"}))

    assert fixed_canary.read_text(encoding="utf-8") == "do-not-touch"
    assert path.exists()
    leftovers = [
        item.name
        for item in tmp_path.iterdir()
        if item.name.startswith(".config.json.") and item.name.endswith(".tmp")
    ]
    assert leftovers == []
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600


def test_stale_loaded_writer_is_rejected_instead_of_losing_newer_update(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    store.save(UserConfig(defaults={"research_policy": "useful"}))

    first = store.load()
    stale = store.load()
    first.defaults["research_policy"] = "off"
    store.save(first)
    bytes_after_first = path.read_bytes()

    stale.defaults["research_policy"] = "aggressive"
    with pytest.raises(UserConfigConflictError, match="reload and retry"):
        store.save(stale)

    assert path.read_bytes() == bytes_after_first
    assert store.load().defaults["research_policy"] == "off"


def test_successful_save_refreshes_revision_for_same_object(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    config = UserConfig(defaults={"research_policy": "useful"})

    store.save(config)
    config.defaults["research_policy"] = "off"
    store.save(config)

    assert store.load().defaults["research_policy"] == "off"


def test_config_symlink_is_rejected_without_touching_target(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks unsupported")
    target = tmp_path / "target.json"
    target.write_text("target-canary", encoding="utf-8")
    path = tmp_path / "config.json"
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")

    store = UserConfigStore(path)
    with pytest.raises(UserConfigError, match="configuration path"):
        store.load()
    with pytest.raises(UserConfigError, match="configuration path"):
        store.save(UserConfig())

    assert target.read_text(encoding="utf-8") == "target-canary"


def test_pre_replace_failure_preserves_previous_bytes_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    store.save(UserConfig(defaults={"research_policy": "useful"}))
    candidate = store.load()
    candidate.defaults["research_policy"] = "off"
    original = path.read_bytes()

    def fail_replace(source, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        store.save(candidate)

    assert path.read_bytes() == original
    leftovers = [
        item.name
        for item in tmp_path.iterdir()
        if item.name.startswith(".config.json.") and item.name.endswith(".tmp")
    ]
    assert leftovers == []


def test_stale_disjoint_writer_conflicts_instead_of_losing_independent_update(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    store.save(UserConfig(defaults={"research_policy": "useful", "local_only": "false"}))

    first = store.load()
    stale = store.load()
    first.defaults["local_only"] = "true"
    store.save(first)

    stale.defaults["research_policy"] = "off"
    with pytest.raises(UserConfigConflictError, match="reload and retry"):
        store.save(stale)

    durable = store.load()
    assert durable.defaults["local_only"] == "true"
    assert durable.defaults["research_policy"] == "useful"


def test_temp_fsync_failure_preserves_previous_bytes_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    store.save(UserConfig(defaults={"research_policy": "useful"}))
    candidate = store.load()
    candidate.defaults["research_policy"] = "off"
    original = path.read_bytes()

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("simulated temp fsync failure")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="simulated temp fsync failure"):
        store.save(candidate)

    assert path.read_bytes() == original
    assert not any(
        item.name.startswith(".config.json.") and item.name.endswith(".tmp")
        for item in tmp_path.iterdir()
    )


def test_post_replace_directory_fsync_failure_reports_uncertain_durability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    store.save(UserConfig(defaults={"research_policy": "useful"}))
    candidate = store.load()
    candidate.defaults["research_policy"] = "off"
    real_fsync = os.fsync
    calls = 0

    def fail_second_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated directory fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_second_fsync)
    with pytest.raises(OSError, match="simulated directory fsync failure"):
        store.save(candidate)

    # The atomic replace already happened: the caller gets an error rather than
    # a false rollback claim, and the resulting JSON remains complete/parseable.
    assert UserConfigStore(path).load().defaults["research_policy"] == "off"
    assert not any(
        item.name.startswith(".config.json.") and item.name.endswith(".tmp")
        for item in tmp_path.iterdir()
    )


def test_lock_symlink_is_not_followed_on_posix(tmp_path: Path) -> None:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("O_NOFOLLOW advisory-lock protection unavailable")
    target = tmp_path / "lock-target"
    target.write_text("lock-canary", encoding="utf-8")
    lock_path = tmp_path / ".config.json.lock"
    try:
        lock_path.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")

    store = UserConfigStore(tmp_path / "config.json")
    with pytest.raises(OSError):
        store.load()

    assert target.read_text(encoding="utf-8") == "lock-canary"
