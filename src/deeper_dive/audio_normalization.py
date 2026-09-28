"""Decode and normalize provider audio into canonical PCM metadata."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from deeper_dive.ffmpeg import FFmpegConfig, FFmpegError
from deeper_dive.tts import TTSAudioResult

CANONICAL_SAMPLE_RATE_HZ = 24_000
CANONICAL_CHANNELS = 1
CANONICAL_SAMPLE_WIDTH_BYTES = 2
CANONICAL_FORMAT = "pcm_s16le"


class AudioNormalizationError(ValueError):
    """Actionable failure raised when provider audio cannot be normalized."""


@dataclass(frozen=True, slots=True)
class CanonicalAudio:
    """Canonical PCM representation consumed by timeline/composition stages."""

    pcm: bytes
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    duration_seconds: float
    source_format: str
    source_media_type: str

    @property
    def frame_count(self) -> int:
        frame_size = self.channels * self.sample_width_bytes
        return len(self.pcm) // frame_size

    @property
    def format(self) -> str:
        return CANONICAL_FORMAT


@dataclass(frozen=True, slots=True)
class FFmpegAudioNormalizer:
    """FFmpeg/libswresample-backed converter to the canonical TTS PCM contract."""

    config: FFmpegConfig

    @classmethod
    def detect(cls, executable: Path | None = None) -> FFmpegAudioNormalizer:
        try:
            return cls(FFmpegConfig.detect(executable))
        except FFmpegError as exc:
            raise AudioNormalizationError(str(exc)) from exc

    def normalize_provider_audio(self, result: TTSAudioResult) -> CanonicalAudio:
        """Normalize one provider TTS result to mono 24 kHz signed 16-bit PCM."""

        if not result.audio:
            raise AudioNormalizationError("provider audio output is empty")
        audio_format = result.format.lower().lstrip(".")
        media_type = result.media_type.lower()
        if audio_format == "wav" or media_type in {"audio/wav", "audio/x-wav"}:
            return self.normalize_wav(result.audio, source_media_type=result.media_type)
        if audio_format in {"pcm_s16le", "raw", "pcm"}:
            if result.sample_rate_hz is None:
                raise AudioNormalizationError("raw PCM provider output requires sample_rate_hz")
            return self.normalize_raw_pcm16(
                result.audio,
                sample_rate_hz=result.sample_rate_hz,
                channels=CANONICAL_CHANNELS,
                source_format=audio_format,
                source_media_type=result.media_type,
            )
        if audio_format == "mp3" or media_type == "audio/mpeg":
            raise AudioNormalizationError(
                "MP3 decoding is not accepted by the WAV-only composition policy"
            )
        raise AudioNormalizationError(f"unsupported audio format: {result.format!r}")

    def normalize_wav(
        self,
        audio: bytes,
        *,
        source_media_type: str = "audio/wav",
    ) -> CanonicalAudio:
        """Decode a WAV byte payload using FFmpeg and normalize it to canonical PCM."""

        if not audio:
            raise AudioNormalizationError("WAV audio output is empty")
        pcm = self._convert(
            ["-f", "wav", "-i", "pipe:0"],
            audio,
            failure_context="invalid WAV audio",
        )
        return _canonical_audio(
            pcm,
            source_format="wav",
            source_media_type=source_media_type,
        )

    def normalize_raw_pcm16(
        self,
        pcm: bytes,
        *,
        sample_rate_hz: int,
        channels: int,
        source_format: str = "pcm_s16le",
        source_media_type: str = "audio/L16",
    ) -> CanonicalAudio:
        """Normalize raw little-endian signed 16-bit PCM from provider adapters."""

        if sample_rate_hz <= 0:
            raise AudioNormalizationError("sample_rate_hz must be positive")
        if channels <= 0:
            raise AudioNormalizationError("channels must be positive")
        frame_size = channels * CANONICAL_SAMPLE_WIDTH_BYTES
        if not pcm or len(pcm) % frame_size != 0:
            raise AudioNormalizationError("raw PCM data is empty or frame-misaligned")
        normalized = self._convert(
            [
                "-f",
                "s16le",
                "-ar",
                str(sample_rate_hz),
                "-ac",
                str(channels),
                "-i",
                "pipe:0",
            ],
            pcm,
            failure_context="invalid raw PCM audio",
        )
        return _canonical_audio(
            normalized,
            source_format=source_format,
            source_media_type=source_media_type,
        )

    def _convert(
        self,
        input_args: list[str],
        audio: bytes,
        *,
        failure_context: str,
    ) -> bytes:
        args = [
            str(self.config.executable),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            *input_args,
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            str(CANONICAL_CHANNELS),
            "-ar",
            str(CANONICAL_SAMPLE_RATE_HZ),
            "pipe:1",
        ]
        try:
            result = subprocess.run(
                args,
                input=audio,
                capture_output=True,
                check=False,
                shell=False,
            )
        except OSError as exc:
            raise AudioNormalizationError(f"unable to execute FFmpeg: {exc}") from exc
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            raise AudioNormalizationError(f"{failure_context}: {_sanitize(stderr)}")
        if not result.stdout:
            raise AudioNormalizationError("FFmpeg produced no normalized audio")
        if len(result.stdout) % (CANONICAL_CHANNELS * CANONICAL_SAMPLE_WIDTH_BYTES) != 0:
            raise AudioNormalizationError("FFmpeg produced frame-misaligned normalized audio")
        return result.stdout


def normalize_provider_audio(
    result: TTSAudioResult,
    *,
    normalizer: FFmpegAudioNormalizer | None = None,
) -> CanonicalAudio:
    """Normalize one provider TTS result to mono 24 kHz signed 16-bit PCM."""

    active_normalizer = normalizer or FFmpegAudioNormalizer.detect()
    return active_normalizer.normalize_provider_audio(result)


def normalize_wav(
    audio: bytes,
    *,
    source_media_type: str = "audio/wav",
    normalizer: FFmpegAudioNormalizer | None = None,
) -> CanonicalAudio:
    """Decode a WAV byte payload and normalize it to canonical PCM."""

    active_normalizer = normalizer or FFmpegAudioNormalizer.detect()
    return active_normalizer.normalize_wav(audio, source_media_type=source_media_type)


def normalize_raw_pcm16(
    pcm: bytes,
    *,
    sample_rate_hz: int,
    channels: int,
    source_format: str = "pcm_s16le",
    source_media_type: str = "audio/L16",
    normalizer: FFmpegAudioNormalizer | None = None,
) -> CanonicalAudio:
    """Normalize raw little-endian signed 16-bit PCM from provider adapters."""

    active_normalizer = normalizer or FFmpegAudioNormalizer.detect()
    return active_normalizer.normalize_raw_pcm16(
        pcm,
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        source_format=source_format,
        source_media_type=source_media_type,
    )


def _canonical_audio(
    pcm: bytes,
    *,
    source_format: str,
    source_media_type: str,
) -> CanonicalAudio:
    duration = _duration_seconds(pcm, CANONICAL_SAMPLE_RATE_HZ, CANONICAL_CHANNELS)
    return CanonicalAudio(
        pcm=pcm,
        sample_rate_hz=CANONICAL_SAMPLE_RATE_HZ,
        channels=CANONICAL_CHANNELS,
        sample_width_bytes=CANONICAL_SAMPLE_WIDTH_BYTES,
        duration_seconds=duration,
        source_format=source_format,
        source_media_type=source_media_type,
    )


def _duration_seconds(pcm: bytes, sample_rate_hz: int, channels: int) -> float:
    frame_size = channels * CANONICAL_SAMPLE_WIDTH_BYTES
    return len(pcm) / frame_size / sample_rate_hz


def _sanitize(stderr: str, limit: int = 2000) -> str:
    text = re.sub(
        r"(?i)(api[_-]?key|token|authorization|password)=\S+", r"\1=[redacted]", stderr
    )
    text = " ".join(text.split())
    return text[:limit]
