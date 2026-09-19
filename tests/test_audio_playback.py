from __future__ import annotations

from pathlib import Path

from deeper_dive.audio_playback import (
    AudioPlaybackController,
    NoAudioPlayerBackend,
    PlaybackCapabilities,
    PlaybackState,
)


class FakePlaybackBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, float]] = []
        self.paused = False
        self.running = False

    @property
    def capabilities(self) -> PlaybackCapabilities:
        return PlaybackCapabilities(
            strategy="fake",
            can_play=True,
            can_pause=True,
            can_seek=True,
            chapter_sync=True,
            detail="fake controllable player",
        )

    def play(self, audio_path: Path, *, start_seconds: float = 0.0) -> PlaybackState:
        self.calls.append((audio_path, start_seconds))
        self.running = True
        self.paused = False
        return PlaybackState(True, True, "playing", audio_path, start_seconds, self.capabilities)

    def pause(self) -> PlaybackState:
        self.paused = True
        return PlaybackState(True, False, "paused", capabilities=self.capabilities)

    def resume(self) -> PlaybackState:
        self.paused = False
        self.running = True
        return PlaybackState(True, True, "resumed", capabilities=self.capabilities)

    def stop(self) -> PlaybackState:
        self.running = False
        return PlaybackState(True, False, "stopped", capabilities=self.capabilities)

    def is_running(self) -> bool:
        return self.running


def test_missing_player_is_nonfatal(tmp_path: Path) -> None:
    audio_path = tmp_path / "episode.mp3"
    controller = AudioPlaybackController(NoAudioPlayerBackend())

    state = controller.play(audio_path, start_seconds=12.5)

    assert not state.available
    assert not state.playing
    assert "generation and export are unaffected" in state.message
    assert state.position_seconds == 12.5


def test_play_pause_resume_seek_with_capable_backend(tmp_path: Path) -> None:
    audio_path = tmp_path / "episode.wav"
    audio_path.write_bytes(b"fake")
    backend = FakePlaybackBackend()
    controller = AudioPlaybackController(backend)

    assert controller.play(audio_path, start_seconds=3.0).playing
    assert controller.pause().message == "paused"
    assert controller.resume().playing
    assert controller.seek(audio_path, start_seconds=42.25).position_seconds == 42.25
    assert controller.stop().message == "stopped"
    assert backend.calls == [(audio_path, 3.0), (audio_path, 42.25)]
