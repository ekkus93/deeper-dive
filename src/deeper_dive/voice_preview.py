"""Deterministic TTS voice previews with reusable local caching."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from deeper_dive.tts import TTSProvider, TTSRequest

PREVIEW_TEXT = "Welcome to Deeper Dive. This is a preview of my speaking voice."


class VoicePreviewService:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)

    def preview(
        self,
        provider: TTSProvider,
        *,
        voice: str,
        model: str | None = None,
        settings: dict[str, object] | None = None,
        text: str = PREVIEW_TEXT,
    ) -> Path:
        key = self.cache_key(
            provider.provider_id,
            voice=voice,
            model=model,
            settings=settings,
            text=text,
        )
        path = self.cache_dir / f"{key}.wav"
        if path.is_file() and path.stat().st_size:
            return path
        result = provider.synthesize(TTSRequest(text=text, voice=voice, model=model))
        if not result.audio:
            raise RuntimeError("voice preview synthesis returned empty audio")
        suffix = f".{result.format.lower()}"
        path = self.cache_dir / f"{key}{suffix}"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_bytes(result.audio)
        temporary.replace(path)
        return path

    @staticmethod
    def cache_key(
        provider_id: str,
        *,
        voice: str,
        model: str | None,
        settings: dict[str, object] | None,
        text: str,
    ) -> str:
        identity = json.dumps(
            {
                "provider": provider_id,
                "voice": voice,
                "model": model,
                "settings": settings or {},
                "text": text,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(identity.encode()).hexdigest()

    def export(self, cached: Path, destination: Path) -> Path:
        if not cached.is_file():
            raise FileNotFoundError(f"voice preview does not exist: {cached}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached, destination)
        return destination

    def play(self, cached: Path, *, player: str | None = None) -> None:
        if not cached.is_file():
            raise FileNotFoundError(f"voice preview does not exist: {cached}")
        executable = player or self._discover_player()
        if executable is None:
            raise RuntimeError(
                "local audio playback is unavailable; export the voice preview "
                "and play it externally"
            )
        completed = subprocess.run(
            [executable, str(cached)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.returncode:
            raise RuntimeError(
                f"voice preview playback failed with exit code {completed.returncode}"
            )

    @staticmethod
    def _discover_player() -> str | None:
        for command in ("ffplay", "aplay", "paplay"):
            found = shutil.which(command)
            if found:
                return found
        return None
