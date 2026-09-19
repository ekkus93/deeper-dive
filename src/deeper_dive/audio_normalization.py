"""Decode and normalize provider audio into canonical PCM metadata."""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass

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


def normalize_provider_audio(result: TTSAudioResult) -> CanonicalAudio:
    """Normalize one provider TTS result to mono 24 kHz signed 16-bit PCM."""

    if not result.audio:
        raise AudioNormalizationError("provider audio output is empty")
    audio_format = result.format.lower().lstrip(".")
    media_type = result.media_type.lower()
    if audio_format == "wav" or media_type in {"audio/wav", "audio/x-wav"}:
        return normalize_wav(result.audio, source_media_type=result.media_type)
    if audio_format in {"pcm_s16le", "raw", "pcm"}:
        if result.sample_rate_hz is None:
            raise AudioNormalizationError("raw PCM provider output requires sample_rate_hz")
        return normalize_raw_pcm16(
            result.audio,
            sample_rate_hz=result.sample_rate_hz,
            channels=CANONICAL_CHANNELS,
            source_format=audio_format,
            source_media_type=result.media_type,
        )
    if audio_format == "mp3" or media_type == "audio/mpeg":
        raise AudioNormalizationError(
            "MP3 decoding requires the FFmpeg-backed decoder introduced by DD-133"
        )
    raise AudioNormalizationError(f"unsupported audio format: {result.format!r}")


def normalize_wav(audio: bytes, *, source_media_type: str = "audio/wav") -> CanonicalAudio:
    """Decode a WAV byte payload and normalize it to canonical PCM."""

    if not audio:
        raise AudioNormalizationError("WAV audio output is empty")
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frame_count = wav.getnframes()
            frames = wav.readframes(frame_count)
    except (wave.Error, EOFError) as exc:
        raise AudioNormalizationError(f"invalid WAV audio: {exc}") from exc
    if not frames or frame_count <= 0:
        raise AudioNormalizationError("WAV audio contains no frames")
    if sample_width != CANONICAL_SAMPLE_WIDTH_BYTES:
        raise AudioNormalizationError(
            f"unsupported WAV sample width {sample_width}; expected 16-bit PCM"
        )
    pcm = _mono_mix_i16(frames, channels)
    pcm = _resample_nearest_i16(pcm, sample_rate, CANONICAL_SAMPLE_RATE_HZ)
    duration = _duration_seconds(pcm, CANONICAL_SAMPLE_RATE_HZ, CANONICAL_CHANNELS)
    return CanonicalAudio(
        pcm=pcm,
        sample_rate_hz=CANONICAL_SAMPLE_RATE_HZ,
        channels=CANONICAL_CHANNELS,
        sample_width_bytes=CANONICAL_SAMPLE_WIDTH_BYTES,
        duration_seconds=duration,
        source_format="wav",
        source_media_type=source_media_type,
    )


def normalize_raw_pcm16(
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
    mono = _mono_mix_i16(pcm, channels)
    normalized = _resample_nearest_i16(mono, sample_rate_hz, CANONICAL_SAMPLE_RATE_HZ)
    return CanonicalAudio(
        pcm=normalized,
        sample_rate_hz=CANONICAL_SAMPLE_RATE_HZ,
        channels=CANONICAL_CHANNELS,
        sample_width_bytes=CANONICAL_SAMPLE_WIDTH_BYTES,
        duration_seconds=_duration_seconds(normalized, CANONICAL_SAMPLE_RATE_HZ, CANONICAL_CHANNELS),
        source_format=source_format,
        source_media_type=source_media_type,
    )


def _mono_mix_i16(pcm: bytes, channels: int) -> bytes:
    if channels == CANONICAL_CHANNELS:
        return pcm
    if channels <= 0:
        raise AudioNormalizationError("channels must be positive")
    frame_size = channels * CANONICAL_SAMPLE_WIDTH_BYTES
    if len(pcm) % frame_size != 0:
        raise AudioNormalizationError("PCM data is frame-misaligned")
    samples = memoryview(pcm).cast("h")
    mixed = bytearray()
    for frame_start in range(0, len(samples), channels):
        total = 0
        for channel_index in range(channels):
            total += int(samples[frame_start + channel_index])
        mixed.extend(int(total / channels).to_bytes(2, "little", signed=True))
    return bytes(mixed)


def _resample_nearest_i16(pcm: bytes, source_rate: int, target_rate: int) -> bytes:
    if source_rate <= 0 or target_rate <= 0:
        raise AudioNormalizationError("sample rates must be positive")
    if source_rate == target_rate:
        return pcm
    samples = memoryview(pcm).cast("h")
    if not samples:
        raise AudioNormalizationError("PCM data contains no samples")
    target_count = max(1, round(len(samples) * target_rate / source_rate))
    resampled = bytearray()
    for target_index in range(target_count):
        source_index = min(len(samples) - 1, round(target_index * source_rate / target_rate))
        resampled.extend(int(samples[source_index]).to_bytes(2, "little", signed=True))
    return bytes(resampled)


def _duration_seconds(pcm: bytes, sample_rate_hz: int, channels: int) -> float:
    frame_size = channels * CANONICAL_SAMPLE_WIDTH_BYTES
    return len(pcm) / frame_size / sample_rate_hz
