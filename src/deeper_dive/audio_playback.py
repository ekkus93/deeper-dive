"""Portable local audio playback control for review screens.

The playback layer is deliberately optional: inability to find or control a local
player is surfaced as user-visible reduced capability, never as a generation or
export blocker.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PlaybackCapabilities:
    """Capabilities exposed by the selected playback strategy."""

    strategy: str
    can_play: bool
    can_pause: bool
    can_seek: bool
    chapter_sync: bool
    detail: str


@dataclass(frozen=True, slots=True)
class PlaybackState:
    """User-presentable playback status."""

    available: bool
    playing: bool
    message: str
    audio_path: Path | None = None
    position_seconds: float | None = None
    capabilities: PlaybackCapabilities | None = None


class AudioPlaybackBackend(Protocol):
    @property
    def capabilities(self) -> PlaybackCapabilities: ...

    def play(self, audio_path: Path, *, start_seconds: float = 0.0) -> PlaybackState: ...

    def pause(self) -> PlaybackState: ...

    def resume(self) -> PlaybackState: ...

    def stop(self) -> PlaybackState: ...

    def is_running(self) -> bool: ...


class NoAudioPlayerBackend:
    """Graceful fallback used on headless systems or machines without a known player."""

    @property
    def capabilities(self) -> PlaybackCapabilities:
        return PlaybackCapabilities(
            strategy="none",
            can_play=False,
            can_pause=False,
            can_seek=False,
            chapter_sync=False,
            detail=(
                "No supported local audio player was found; generation and export "
                "are unaffected."
            ),
        )

    def play(self, audio_path: Path, *, start_seconds: float = 0.0) -> PlaybackState:
        return PlaybackState(
            available=False,
            playing=False,
            message=self.capabilities.detail,
            audio_path=audio_path,
            position_seconds=max(0.0, start_seconds),
            capabilities=self.capabilities,
        )

    def pause(self) -> PlaybackState:
        return PlaybackState(
            available=False,
            playing=False,
            message=self.capabilities.detail,
            capabilities=self.capabilities,
        )

    def resume(self) -> PlaybackState:
        return PlaybackState(
            available=False,
            playing=False,
            message=self.capabilities.detail,
            capabilities=self.capabilities,
        )

    def stop(self) -> PlaybackState:
        return PlaybackState(
            available=False,
            playing=False,
            message="No playback process is active.",
            capabilities=self.capabilities,
        )

    def is_running(self) -> bool:
        return False


class LocalProcessAudioPlayer:
    """Best-effort local playback through an installed terminal-capable player."""

    _CANDIDATES = ("mpv", "ffplay", "cvlc", "vlc")
    _STOP_TIMEOUT_SECONDS = 2.0

    def __init__(self, executable: Path, *, strategy: str) -> None:
        self.executable = executable
        self.strategy = strategy
        self._process: subprocess.Popen[bytes] | None = None
        self._last_path: Path | None = None
        self._last_position = 0.0

    @classmethod
    def discover(cls) -> LocalProcessAudioPlayer | None:
        for name in cls._CANDIDATES:
            discovered = shutil.which(name)
            if discovered is not None:
                return cls(Path(discovered), strategy=name)
        return None

    @property
    def capabilities(self) -> PlaybackCapabilities:
        return PlaybackCapabilities(
            strategy=self.strategy,
            can_play=True,
            can_pause=False,
            can_seek=True,
            chapter_sync=True,
            detail=(
                f"Using {self.strategy}. Play and seek restart the local player at "
                "the requested position; pause is unavailable without player-specific IPC."
            ),
        )

    def play(self, audio_path: Path, *, start_seconds: float = 0.0) -> PlaybackState:
        if not audio_path.is_file():
            return PlaybackState(
                available=True,
                playing=False,
                message=f"Audio file not found: {audio_path}",
                audio_path=audio_path,
                position_seconds=max(0.0, start_seconds),
                capabilities=self.capabilities,
            )
        self.stop()
        position = max(0.0, start_seconds)
        args = self._args(audio_path, position)
        try:
            self._process = subprocess.Popen(  # noqa: S603 - fixed argv, shell=False.
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
        except OSError as exc:
            self._process = None
            return PlaybackState(
                available=True,
                playing=False,
                message=f"Unable to start {self.strategy}: {exc}",
                audio_path=audio_path,
                position_seconds=position,
                capabilities=self.capabilities,
            )
        self._last_path = audio_path
        self._last_position = position
        return PlaybackState(
            available=True,
            playing=True,
            message=f"Playing {audio_path.name} at {position:.1f}s via {self.strategy}",
            audio_path=audio_path,
            position_seconds=position,
            capabilities=self.capabilities,
        )

    def pause(self) -> PlaybackState:
        return PlaybackState(
            available=True,
            playing=self.is_running(),
            message=f"Pause is not supported by the {self.strategy} terminal playback strategy.",
            audio_path=self._last_path,
            position_seconds=self._last_position,
            capabilities=self.capabilities,
        )

    def resume(self) -> PlaybackState:
        return PlaybackState(
            available=True,
            playing=self.is_running(),
            message=f"Resume is not supported by the {self.strategy} terminal playback strategy.",
            audio_path=self._last_path,
            position_seconds=self._last_position,
            capabilities=self.capabilities,
        )

    def stop(self) -> PlaybackState:
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=self._STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=self._STOP_TIMEOUT_SECONDS)
        self._process = None
        return PlaybackState(
            available=True,
            playing=False,
            message="Playback stopped.",
            audio_path=self._last_path,
            position_seconds=self._last_position,
            capabilities=self.capabilities,
        )

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _args(self, audio_path: Path, start_seconds: float) -> list[str]:
        if self.strategy == "mpv":
            return [
                str(self.executable),
                "--really-quiet",
                f"--start={start_seconds:.3f}",
                str(audio_path),
            ]
        if self.strategy == "ffplay":
            return [
                str(self.executable),
                "-nodisp",
                "-autoexit",
                "-ss",
                f"{start_seconds:.3f}",
                str(audio_path),
            ]
        return [
            str(self.executable),
            "--play-and-exit",
            f"--start-time={start_seconds:.3f}",
            str(audio_path),
        ]


class AudioPlaybackController:
    """Optional playback controller used by TUI screens."""

    def __init__(self, backend: AudioPlaybackBackend | None = None) -> None:
        self.backend = backend or LocalProcessAudioPlayer.discover() or NoAudioPlayerBackend()

    @property
    def capabilities(self) -> PlaybackCapabilities:
        return self.backend.capabilities

    def play(self, audio_path: Path, *, start_seconds: float = 0.0) -> PlaybackState:
        return self.backend.play(audio_path, start_seconds=start_seconds)

    def pause(self) -> PlaybackState:
        return self.backend.pause()

    def resume(self) -> PlaybackState:
        return self.backend.resume()

    def stop(self) -> PlaybackState:
        return self.backend.stop()

    def seek(self, audio_path: Path, *, start_seconds: float) -> PlaybackState:
        if not self.capabilities.can_seek:
            return PlaybackState(
                available=self.capabilities.can_play,
                playing=self.backend.is_running(),
                message="Seek is not supported by the selected playback strategy.",
                audio_path=audio_path,
                position_seconds=max(0.0, start_seconds),
                capabilities=self.capabilities,
            )
        return self.backend.play(audio_path, start_seconds=start_seconds)
