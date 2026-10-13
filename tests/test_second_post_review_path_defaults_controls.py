"""Configured runtime paths must reject unsafe terminal control characters."""

from __future__ import annotations

import pytest

from deeper_dive.user_config import UserConfig, UserConfigError, UserConfigStore


@pytest.mark.parametrize("key", ["ffmpeg_executable", "kitten_model_dir"])
@pytest.mark.parametrize("control", ["\t", "\x1b", "\x7f", "\x00", "\r", "\n"])
def test_path_controls_are_rejected_without_echo(key: str, control: str) -> None:
    invalid = "/path/to/" + control + "private-path-canary"
    with pytest.raises(ValueError, match="single filesystem path") as caught:
        UserConfig(defaults={key: invalid})
    assert "private-path-canary" not in str(caught.value)


@pytest.mark.parametrize("key", ["ffmpeg_executable", "kitten_model_dir"])
def test_mutated_path_control_rejection_preserves_existing_config_bytes(tmp_path, key: str) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    store.save(UserConfig(defaults={key: "ffmpeg-custom"}))
    prior = path.read_bytes()

    loaded = store.load()
    loaded.defaults[key] = "/tmp/\tAuthorization: Bearer secret-path-canary"
    with pytest.raises(UserConfigError, match="defaults") as caught:
        store.save(loaded)
    assert "secret-path-canary" not in str(caught.value)
    assert path.read_bytes() == prior


@pytest.mark.parametrize("key", ["ffmpeg_executable", "kitten_model_dir"])
def test_printable_paths_remain_accepted(key: str) -> None:
    config = UserConfig(defaults={key: " /opt/my tools/model-dir "})
    assert config.defaults[key] == "/opt/my tools/model-dir"
