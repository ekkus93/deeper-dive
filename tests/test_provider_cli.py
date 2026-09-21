from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.command import main
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _call(args: list[str], capsys: pytest.CaptureFixture[str]) -> object:
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def test_provider_cli_list_health_discovery_and_kitten_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    UserConfigStore(tmp_path / "config.json").save(
        UserConfig(
            providers={
                "local": ProviderConfig(
                    provider_type="ollama",
                    base_url="http://localhost:11434",
                    default_model="qwen3",
                ),
                "fake": ProviderConfig(provider_type="fake"),
                "fake-tts": ProviderConfig(provider_type="fake-tts"),
            }
        )
    )
    base = ["--data-dir", str(tmp_path), "--json", "provider"]

    listed = _call([*base, "list"], capsys)
    assert isinstance(listed, list)
    assert {item["id"] for item in listed} == {"fake", "fake-tts", "local"}

    health = _call([*base, "health", "fake"], capsys)
    assert health == {"healthy": True, "id": "fake", "message": "ready"}

    models = _call([*base, "models", "fake"], capsys)
    assert models[0]["model"] == "fake-v1"

    voices = _call([*base, "voices", "fake-tts"], capsys)
    assert voices[0]["id"] == "voice-a"

    status = _call([*base, "kitten-status"], capsys)
    assert status["installed"] is False

    benchmark = _call([*base, "kitten-benchmark"], capsys)
    assert benchmark["voice_count"] == 8
    assert benchmark["sample_rate_hz"] == 24000


def test_provider_router_preserves_existing_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _call(["--data-dir", str(tmp_path), "--json", "project", "create", "Router"], capsys)
    assert result["name"] == "Router"


def test_router_rewrites_delegated_cli_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _call(["--data-dir", str(tmp_path), "--json", "project", "create", "Errors"], capsys)

    assert main(["--data-dir", str(tmp_path), "research", "run", str(project["id"])]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Network request failed." in captured.err
    assert "gap IDs" not in captured.err
