"""Safe FFmpeg discovery and canonical timeline composition."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from deeper_dive.audio_timeline import AudioTimeline


class FFmpegError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FFmpegConfig:
    executable: Path
    loudness_target_lufs: float = -16.0
    true_peak_db: float = -1.5

    @classmethod
    def detect(cls, configured: Path | None = None) -> FFmpegConfig:
        if configured is not None:
            if not configured.is_file():
                raise FFmpegError(f"configured FFmpeg executable not found: {configured}")
            return cls(configured)
        discovered = shutil.which("ffmpeg")
        if discovered is None:
            raise FFmpegError("FFmpeg was not found on PATH; install it or configure its executable path")
        return cls(Path(discovered))


class FFmpegComposer:
    """Compose timeline clips using argv-only subprocess execution."""

    def __init__(self, config: FFmpegConfig) -> None:
        self.config = config

    def compose(self, timeline: AudioTimeline, artifact_paths: dict[str, Path], output: Path) -> None:
        clips = [placement for placement in timeline.placements if placement.item.kind == "clip"]
        if not clips:
            raise FFmpegError("timeline contains no audio clips")
        args = [str(self.config.executable), "-y", "-hide_banner", "-loglevel", "error"]
        for placement in clips:
            artifact_id = placement.item.artifact_id
            if artifact_id is None or artifact_id not in artifact_paths:
                raise FFmpegError(f"missing audio artifact for timeline clip: {artifact_id}")
            args.extend(["-i", str(artifact_paths[artifact_id])])

        filters: list[str] = []
        labels: list[str] = []
        for index, placement in enumerate(clips):
            delay_ms = round(placement.start_seconds * 1000)
            label = f"a{index}"
            filters.append(f"[{index}:a]adelay={delay_ms}:all=1[{label}]")
            labels.append(f"[{label}]")
        mixed = "".join(labels)
        filters.append(
            f"{mixed}amix=inputs={len(labels)}:normalize=0,"
            f"loudnorm=I={self.config.loudness_target_lufs}:TP={self.config.true_peak_db}:LRA=11[out]"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        args.extend(["-filter_complex", ";".join(filters), "-map", "[out]", str(output)])
        self._run(args)

    @staticmethod
    def _run(args: list[str]) -> None:
        try:
            result = subprocess.run(args, capture_output=True, text=True, check=False, shell=False)
        except OSError as exc:
            raise FFmpegError(f"unable to execute FFmpeg: {exc}") from exc
        if result.returncode != 0:
            raise FFmpegError(f"FFmpeg failed: {FFmpegComposer._sanitize(result.stderr)}")

    @staticmethod
    def _sanitize(stderr: str, limit: int = 2000) -> str:
        text = re.sub(r"(?i)(api[_-]?key|token|authorization|password)=\S+", r"\1=[redacted]", stderr)
        text = " ".join(text.split())
        return text[:limit]
