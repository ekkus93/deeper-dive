from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive import command as command_module
from deeper_dive.command import main
from deeper_dive.llm import LLMModel, ProviderHealth
from deeper_dive.ollama_llm import OllamaLLMProvider
from deeper_dive.tts import FakeTTSProvider
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


def test_provider_cli_uses_configured_ollama_adapter_for_health_and_models(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    UserConfigStore(tmp_path / "config.json").save(
        UserConfig(
            providers={
                "local": ProviderConfig(
                    provider_type="ollama",
                    base_url="http://127.0.0.1:11434",
                    default_model="qwen3",
                )
            }
        )
    )
    monkeypatch.setattr(
        OllamaLLMProvider,
        "health",
        lambda self: ProviderHealth(True, "configured ollama ready"),
    )
    monkeypatch.setattr(
        OllamaLLMProvider,
        "models",
        lambda self: (LLMModel("ollama", "qwen3", ("chat",)),),
    )
    base = ["--data-dir", str(tmp_path), "--json", "provider"]

    health = _call([*base, "health", "local"], capsys)
    assert health == {"healthy": True, "id": "local", "message": "configured ollama ready"}

    models = _call([*base, "models", "local"], capsys)
    assert models == [{"capabilities": ["chat"], "model": "qwen3", "provider": "local"}]


def test_provider_cli_discovers_fixed_configured_tts_voice_catalog(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMPAT_KEY", "fixture-secret")
    UserConfigStore(tmp_path / "config.json").save(
        UserConfig(
            providers={
                "speech": ProviderConfig(
                    provider_type="openai-compatible-tts",
                    base_url="https://tts.example.invalid/v1",
                    credential_env="COMPAT_KEY",
                    voices=("narrator", "expert"),
                )
            }
        )
    )

    voices = _call(
        ["--data-dir", str(tmp_path), "--json", "provider", "voices", "speech"],
        capsys,
    )

    assert [voice["id"] for voice in voices] == ["narrator", "expert"]
    assert "fixture-secret" not in capsys.readouterr().out


def test_provider_cli_distinguishes_unknown_provider_from_unsupported_capability(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    UserConfigStore(tmp_path / "config.json").save(
        UserConfig(
            providers={
                "text": ProviderConfig(provider_type="fake"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            }
        )
    )
    base = ["--data-dir", str(tmp_path), "--json", "provider"]

    assert main([*base, "voices", "text"]) == 2
    captured = capsys.readouterr()
    assert "does not support voice discovery" in captured.err
    assert "unknown provider" not in captured.err.lower()

    assert main([*base, "models", "speech"]) == 2
    captured = capsys.readouterr()
    assert "does not support model discovery" in captured.err
    assert "unknown provider" not in captured.err.lower()

    assert main([*base, "models", "missing"]) == 2
    captured = capsys.readouterr()
    assert "unknown provider" in captured.err.lower()


def test_kitten_benchmark_runs_timed_synthesis_and_reports_metrics(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(command_module, "KittenTTSMicroProvider", FakeTTSProvider)
    benchmark = _call(
        ["--data-dir", str(tmp_path), "--json", "provider", "kitten-benchmark"],
        capsys,
    )
    assert benchmark["provider"] == "fake-tts"
    assert benchmark["voice"] == "voice-a"
    assert benchmark["audio_seconds"] > 0
    assert benchmark["wall_seconds"] > 0
    assert benchmark["realtime_factor"] > 0
    assert benchmark["x_realtime"] > 0
    assert benchmark["runtime"].startswith("Python ")
    assert benchmark["cpu"]


def test_provider_router_preserves_existing_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _call(
        ["--data-dir", str(tmp_path), "--json", "project", "create", "Router"],
        capsys,
    )
    assert result["name"] == "Router"


def test_router_rewrites_delegated_cli_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _call(
        ["--data-dir", str(tmp_path), "--json", "project", "create", "Errors"],
        capsys,
    )

    assert main(["--data-dir", str(tmp_path), "research", "run", str(project["id"])]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Network request failed." in captured.err
    assert "gap IDs" not in captured.err
