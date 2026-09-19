from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from deeper_dive.kitten_model_manager import KittenModelManager


def test_model_manager_installs_tracks_version_and_uninstalls(tmp_path: Path) -> None:
    payload = b"deterministic fake kitten weights"
    digest = hashlib.sha256(payload).hexdigest()

    def fetch(_url: str, destination: Path) -> None:
        destination.write_bytes(payload)

    manager = KittenModelManager(tmp_path / "custom-models", fetcher=fetch)
    assert not manager.state().installed

    state = manager.install(url="https://example.invalid/model", version="0.8", sha256=digest)
    assert state.installed
    assert state.version == "0.8"
    assert state.sha256 == digest
    assert state.path.read_bytes() == payload
    assert not list(manager.model_dir.glob("*.partial"))

    manager.uninstall()
    assert not manager.state().installed


def test_interrupted_download_is_cleaned_and_not_installed(tmp_path: Path) -> None:
    def interrupted(_url: str, destination: Path) -> None:
        destination.write_bytes(b"partial")
        raise OSError("connection lost")

    manager = KittenModelManager(tmp_path, fetcher=interrupted)
    with pytest.raises(OSError, match="connection lost"):
        manager.install(url="https://example.invalid/model", version="0.8")
    assert not manager.state().installed
    assert not list(tmp_path.glob("*.partial"))


def test_integrity_failure_does_not_promote_partial_download(tmp_path: Path) -> None:
    manager = KittenModelManager(
        tmp_path, fetcher=lambda _url, destination: destination.write_bytes(b"wrong")
    )
    with pytest.raises(RuntimeError, match="integrity"):
        manager.install(url="https://example.invalid/model", version="0.8", sha256="0" * 64)
    assert not manager.state().installed
    assert not (tmp_path / "model.bin").exists()


def test_reinstall_replaces_existing_artifact(tmp_path: Path) -> None:
    payloads = iter((b"first", b"second"))

    def fetch(_url: str, destination: Path) -> None:
        destination.write_bytes(next(payloads))

    manager = KittenModelManager(tmp_path, fetcher=fetch)
    manager.install(url="https://example.invalid/one", version="1")
    state = manager.reinstall(url="https://example.invalid/two", version="2")
    assert state.installed
    assert state.version == "2"
    assert state.path.read_bytes() == b"second"


def test_stale_partial_is_removed_before_install(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "abandoned.partial").write_bytes(b"incomplete")
    manager = KittenModelManager(
        tmp_path, fetcher=lambda _url, destination: destination.write_bytes(b"complete")
    )
    manager.install(url="https://example.invalid/model", version="1")
    assert not (tmp_path / "abandoned.partial").exists()
    assert manager.state().installed
