from __future__ import annotations

import subprocess
from pathlib import Path

from deeper_dive.audio_playback import (
    AudioPlaybackController,
    LocalProcessAudioPlayer,
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


class FakeProcess:
    def __init__(self, *, time_out_once: bool = False, always_time_out: bool = False) -> None:
        self.time_out_once = time_out_once
        self.always_time_out = always_time_out
        self.terminated = False
        self.killed = False
        self.wait_timeouts: list[float] = []

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float) -> int:
        self.wait_timeouts.append(timeout)
        if self.always_time_out or (self.time_out_once and len(self.wait_timeouts) == 1):
            raise subprocess.TimeoutExpired("fake-player", timeout)
        return 0


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


def test_local_player_stop_waits_after_terminate() -> None:
    player = LocalProcessAudioPlayer(Path("/fake/mpv"), strategy="mpv")
    process = FakeProcess()
    player._process = process  # type: ignore[assignment]

    state = player.stop()

    assert process.terminated
    assert not process.killed
    assert process.wait_timeouts == [player._STOP_TIMEOUT_SECONDS]
    assert not state.playing
    assert player._process is None


def test_local_player_stop_escalates_to_kill_after_timeout() -> None:
    player = LocalProcessAudioPlayer(Path("/fake/mpv"), strategy="mpv")
    process = FakeProcess(time_out_once=True)
    player._process = process  # type: ignore[assignment]

    state = player.stop()

    assert process.terminated
    assert process.killed
    assert process.wait_timeouts == [
        player._STOP_TIMEOUT_SECONDS,
        player._STOP_TIMEOUT_SECONDS,
    ]
    assert not state.playing
    assert player._process is None


def test_local_player_stop_remains_bounded_when_reap_stalls_after_kill() -> None:
    player = LocalProcessAudioPlayer(Path("/fake/mpv"), strategy="mpv")
    process = FakeProcess(always_time_out=True)
    player._process = process  # type: ignore[assignment]

    state = player.stop()

    assert process.terminated
    assert process.killed
    assert process.wait_timeouts == [
        player._STOP_TIMEOUT_SECONDS,
        player._STOP_TIMEOUT_SECONDS,
    ]
    assert not state.playing
    assert player._process is None
