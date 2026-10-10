"""Deterministic configuration failure and independent-writer regression matrix."""

from __future__ import annotations

import json
import os
import tempfile
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


def _existing_config(tmp_path: Path) -> tuple[UserConfigStore, UserConfig, bytes]:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={"research_policy": "off"}))
    candidate = store.load()
    candidate.defaults["research_policy"] = "useful"
    return store, candidate, store.path.read_bytes()


def _assert_preserved(store: UserConfigStore, before: bytes, tmp_path: Path) -> None:
    assert store.path.read_bytes() == before
    assert json.loads(store.path.read_text(encoding="utf-8"))["defaults"] == {
        "research_policy": "off"
    }
    assert list(tmp_path.glob(".config.json.*.tmp")) == []


def test_temp_creation_failure_does_not_change_durable_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, candidate, before = _existing_config(tmp_path)

    def fail_create(*args: object, **kwargs: object) -> None:
        raise OSError("injected temp creation failure")

    monkeypatch.setattr("deeper_dive.user_config.tempfile.NamedTemporaryFile", fail_create)
    with pytest.raises(OSError, match="injected temp creation failure"):
        store.save(candidate)

    _assert_preserved(store, before, tmp_path)


def test_temp_write_failure_cleans_owned_temp_and_preserves_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, candidate, before = _existing_config(tmp_path)
    original_factory = tempfile.NamedTemporaryFile

    class FailingWriter:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.handle = original_factory(*args, **kwargs)

        @property
        def name(self) -> str:
            return self.handle.name

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self.handle.__exit__(*args)

        def fileno(self) -> int:
            return self.handle.fileno()

        def write(self, data: bytes) -> None:
            raise OSError("injected temp write failure")

    monkeypatch.setattr("deeper_dive.user_config.tempfile.NamedTemporaryFile", FailingWriter)
    with pytest.raises(OSError, match="injected temp write failure"):
        store.save(candidate)

    _assert_preserved(store, before, tmp_path)


def test_pre_replace_permission_failure_preserves_bytes_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, candidate, before = _existing_config(tmp_path)

    def fail_permission(path: Path) -> None:
        raise OSError("injected chmod failure")

    monkeypatch.setattr(store, "_restrict_permissions", fail_permission)
    with pytest.raises(OSError, match="injected chmod failure"):
        store.save(candidate)

    _assert_preserved(store, before, tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX symlink semantics")
def test_existing_configuration_symlink_is_rejected_without_canary_clobber(
    tmp_path: Path,
) -> None:
    target = tmp_path / "user-data-canary.json"
    target.write_text('{"canary":"leave me alone"}', encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.symlink_to(target)

    with pytest.raises(UserConfigError, match="configuration path"):
        UserConfigStore(config_path).save(UserConfig())

    assert json.loads(target.read_text(encoding="utf-8")) == {"canary": "leave me alone"}
    assert config_path.is_symlink()


@pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="requires POSIX O_NOFOLLOW",
)
def test_symlinked_advisory_lock_is_never_followed(tmp_path: Path) -> None:
    target = tmp_path / "advisory-lock-canary.txt"
    target.write_text("leave me alone", encoding="utf-8")
    (tmp_path / ".config.json.lock").symlink_to(target)

    with pytest.raises(OSError):
        UserConfigStore(tmp_path / "config.json").save(UserConfig())

    assert target.read_text(encoding="utf-8") == "leave me alone"
    assert not (tmp_path / "config.json").exists()


def test_same_key_writers_conflict_without_silent_last_writer_wins(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    UserConfigStore(path).save(UserConfig())
    barrier = Barrier(2)

    def independent_writer(value: str) -> str:
        store = UserConfigStore(path)
        candidate = store.load()
        candidate.defaults["research_policy"] = value
        barrier.wait()
        try:
            store.save(candidate)
        except UserConfigConflictError:
            return "conflict"
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            executor.submit(independent_writer, "useful"),
            executor.submit(independent_writer, "aggressive"),
        ]
        assert sorted(result.result() for result in results) == ["conflict", "saved"]

    assert UserConfigStore(path).load().defaults["research_policy"] in {
        "useful",
        "aggressive",
    }
    assert list(tmp_path.glob(".config.json.*.tmp")) == []
