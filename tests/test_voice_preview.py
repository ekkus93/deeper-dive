from __future__ import annotations

from pathlib import Path

import pytest

from deeper_dive.tts import FakeTTSProvider
from deeper_dive.voice_preview import PREVIEW_TEXT, VoicePreviewService


def test_preview_is_deterministic_and_reuses_cache(tmp_path: Path) -> None:
    provider = FakeTTSProvider()
    previews = VoicePreviewService(tmp_path / "cache")

    first = previews.preview(provider, voice="voice-a", model="fake-v1")
    second = previews.preview(provider, voice="voice-a", model="fake-v1")

    assert first == second
    assert first.read_bytes()
    assert len(provider.requests) == 1
    assert provider.requests[0].text == PREVIEW_TEXT


def test_preview_cache_identity_includes_voice_model_settings_and_text(tmp_path: Path) -> None:
    previews = VoicePreviewService(tmp_path)
    base = previews.cache_key("kitten", voice="a", model="m1", settings={}, text="hello")
    assert base != previews.cache_key("kitten", voice="b", model="m1", settings={}, text="hello")
    assert base != previews.cache_key("kitten", voice="a", model="m2", settings={}, text="hello")
    assert base != previews.cache_key(
        "kitten", voice="a", model="m1", settings={"speed": 1.1}, text="hello"
    )
    assert base != previews.cache_key("kitten", voice="a", model="m1", settings={}, text="bye")


def test_preview_can_be_exported(tmp_path: Path) -> None:
    previews = VoicePreviewService(tmp_path / "cache")
    cached = previews.preview(FakeTTSProvider(), voice="voice-a")
    destination = previews.export(cached, tmp_path / "exports" / "preview.wav")
    assert destination.read_bytes() == cached.read_bytes()


def test_playback_absence_has_actionable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previews = VoicePreviewService(tmp_path / "cache")
    cached = previews.preview(FakeTTSProvider(), voice="voice-a")
    monkeypatch.setattr(VoicePreviewService, "_discover_player", staticmethod(lambda: None))
    with pytest.raises(RuntimeError, match="playback is unavailable.*export"):
        previews.play(cached)
