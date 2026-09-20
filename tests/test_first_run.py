from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from deeper_dive.first_run import FirstRunController
from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _controller(tmp_path: Path, config: UserConfig) -> FirstRunController:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(config)
    return FirstRunController(ProviderController(store, LLMProviderRegistry(), {}))


def test_first_run_allows_empty_cloud_configuration(tmp_path: Path) -> None:
    controller = _controller(tmp_path, UserConfig())
    with (
        patch("deeper_dive.first_run.shutil.which", return_value=None),
        patch("deeper_dive.first_run.importlib.util.find_spec", return_value=None),
    ):
        status = controller.status()
    assert status.cloud_required is False
    assert status.configured_providers == ()
    text = "\n".join(status.guidance())
    assert "cloud configuration may be skipped" in text
    assert "install FFmpeg" in text
    assert "KittenTTS optional dependency" in text
    assert "no copyrighted sample content is bundled" in text


def test_first_run_recognizes_local_only_provider(tmp_path: Path) -> None:
    config = UserConfig(
        providers={
            "desk": ProviderConfig(
                provider_type="ollama",
                base_url="http://localhost:11434",
                default_model="local-model",
            )
        }
    )
    controller = _controller(tmp_path, config)
    with (
        patch("deeper_dive.first_run.shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("deeper_dive.first_run.importlib.util.find_spec", return_value=object()),
    ):
        status = controller.status()
    assert status.ffmpeg_available is True
    assert status.kitten_available is True
    assert status.cloud_required is False
    assert status.can_continue_local_only is True
    assert status.local_providers == ("desk",)
    text = "\n".join(status.guidance())
    assert "FFmpeg: available" in text
    assert "KittenTTS Micro: runtime available" in text
    assert "Local providers: desk" in text
