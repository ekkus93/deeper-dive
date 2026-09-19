"""Deterministic episode export artifacts with provenance and secret-safe metadata."""

from __future__ import annotations

import json
import re
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

from deeper_dive.audio_normalization import CanonicalAudio
from deeper_dive.ffmpeg import FFmpegComposer


@dataclass(frozen=True, slots=True)
class TranscriptTurn:
    host: str
    text: str


@dataclass(frozen=True, slots=True)
class ManifestSource:
    title: str
    origin: str
    locator: str | None = None


class EpisodeExporter:
    """Write the complete portable artifact set for one episode."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def reserve_stem(self, title: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "episode"
        candidate = self.output_dir / slug
        suffix = 2
        while any(candidate.with_suffix(ext).exists() for ext in (".wav", ".mp3", ".md", ".json")):
            candidate = self.output_dir / f"{slug}-{suffix}"
            suffix += 1
        return candidate

    @staticmethod
    def write_wav(path: Path, audio: CanonicalAudio) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as output:
            output.setnchannels(audio.channels)
            output.setsampwidth(audio.sample_width_bytes)
            output.setframerate(audio.sample_rate_hz)
            output.writeframes(audio.pcm)
        return path

    @staticmethod
    def write_mp3(wav_path: Path, mp3_path: Path, composer: FFmpegComposer) -> Path:
        composer._run([str(composer.config.executable), "-y", "-i", str(wav_path), str(mp3_path)])
        return mp3_path

    @staticmethod
    def write_transcript(path: Path, title: str, turns: tuple[TranscriptTurn, ...]) -> Path:
        body = [f"# {title}", ""]
        for turn in turns:
            body.extend((f"## {turn.host}", "", turn.text, ""))
        path.write_text("\n".join(body), encoding="utf-8")
        return path

    @staticmethod
    def write_manifest(path: Path, sources: tuple[ManifestSource, ...]) -> Path:
        payload = {"sources": [asdict(source) for source in sources]}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    @staticmethod
    def write_metadata(path: Path, metadata: dict[str, object]) -> Path:
        forbidden = {"api_key", "apikey", "token", "authorization", "password", "secret"}

        def clean(value: object) -> object:
            if isinstance(value, dict):
                return {
                    str(key): clean(item)
                    for key, item in value.items()
                    if str(key).lower().replace("-", "_") not in forbidden
                }
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value

        path.write_text(json.dumps(clean(metadata), indent=2, sort_keys=True), encoding="utf-8")
        return path
