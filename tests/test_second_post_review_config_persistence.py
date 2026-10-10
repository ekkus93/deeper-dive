from __future__ import annotations

import os
import tempfile
from pathlib import Path
from threading import Barrier, Event, Thread

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


def test_temp_creation_failure_preserves_previous_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    store.save(UserConfig(defaults={"research_policy": "useful"}))
    candidate = store.load()
    candidate.defaults["research_policy"] = "off"
    original = path.read_bytes()

    def fail_create(*args, **kwargs):
        raise OSError("simulated temp create failure")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", fail_create)
    with pytest.raises(OSError, match="simulated temp create failure"):
        store.save(candidate)

    assert path.read_bytes() == original


def test_temp_chmod_failure_preserves_previous_bytes_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name != "posix":
        pytest.skip("temporary fchmod is POSIX-specific")
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    store.save(UserConfig(defaults={"research_policy": "useful"}))
    candidate = store.load()
    candidate.defaults["research_policy"] = "off"
    original = path.read_bytes()

    def fail_fchmod(_fd: int, _mode: int) -> None:
        raise OSError("simulated temp chmod failure")

    monkeypatch.setattr(os, "fchmod", fail_fchmod)
    with pytest.raises(OSError, match="simulated temp chmod failure"):
        store.save(candidate)

    assert path.read_bytes() == original
    assert not any(
        item.name.startswith(".config.json.") and item.name.endswith(".tmp")
        for item in tmp_path.iterdir()
    )


def test_temp_write_failure_preserves_previous_bytes_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    store.save(UserConfig(defaults={"research_policy": "useful"}))
    candidate = store.load()
    candidate.defaults["research_policy"] = "off"
    original = path.read_bytes()
    real_factory = tempfile.NamedTemporaryFile

    class FailingTemporary:
        def __init__(self, handle):
            self._handle = handle
            self.name = handle.name

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self._handle.close()
            return False

        def fileno(self):
            return self._handle.fileno()

        def write(self, _payload):
            raise OSError("simulated temp write failure")

        def flush(self):
            return self._handle.flush()

    def failing_factory(*args, **kwargs):
        return FailingTemporary(real_factory(*args, **kwargs))

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", failing_factory)
    with pytest.raises(OSError, match="simulated temp write failure"):
        store.save(candidate)

    assert path.read_bytes() == original
    assert not any(
        item.name.startswith(".config.json.") and item.name.endswith(".tmp")
        for item in tmp_path.iterdir()
    )


def test_fixed_temp_symlink_canary_is_never_followed(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks unsupported")
    target = tmp_path / "temp-target"
    target.write_text("temp-symlink-canary", encoding="utf-8")
    fixed_temp = tmp_path / "config.json.tmp"
    try:
        fixed_temp.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")

    UserConfigStore(tmp_path / "config.json").save(
        UserConfig(defaults={"research_policy": "useful"})
    )

    assert target.read_text(encoding="utf-8") == "temp-symlink-canary"
    assert fixed_temp.is_symlink()


def test_two_independent_writers_have_deterministic_conflict_without_lost_update(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.json"
    UserConfigStore(path).save(
        UserConfig(defaults={"research_policy": "useful", "local_only": "false"})
    )
    loaded = Barrier(2)
    first_done = Event()
    results: list[str] = []

    def writer_one() -> None:
        store = UserConfigStore(path)
        candidate = store.load()
        candidate.defaults["local_only"] = "true"
        loaded.wait()
        store.save(candidate)
        results.append("first-saved")
        first_done.set()

    def writer_two() -> None:
        store = UserConfigStore(path)
        candidate = store.load()
        candidate.defaults["research_policy"] = "off"
        loaded.wait()
        assert first_done.wait(2)
        try:
            store.save(candidate)
        except UserConfigConflictError:
            results.append("second-conflict")
        else:
            results.append("second-overwrote")

    first = Thread(target=writer_one)
    second = Thread(target=writer_two)
    first.start()
    second.start()
    first.join(3)
    second.join(3)
    assert not first.is_alive() and not second.is_alive()
    assert results == ["first-saved", "second-conflict"]

    durable = UserConfigStore(path).load()
    assert durable.defaults["local_only"] == "true"
    assert durable.defaults["research_policy"] == "useful"
