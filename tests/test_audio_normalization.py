from __future__ import annotations

import io
import wave

import pytest

from deeper_dive.audio_normalization import (
    CANONICAL_FORMAT,
    CANONICAL_SAMPLE_RATE_HZ,
    AudioNormalizationError,
    normalize_provider_audio,
    normalize_raw_pcm16,
)
from deeper_dive.tts import TTSAudioResult


def test_wav_fixture_normalizes_to_canonical_mono_pcm_metadata() -> None:
    wav = _wav_bytes(
        sample_rate_hz=12_000,
        channels=2,
        frames=((1000, -1000), (2000, 2000), (-3000, -1000)),
    )
    normalized = normalize_provider_audio(
        TTSAudioResult(
            audio=wav,
            media_type="audio/wav",
            format="wav",
            provider="fixture",
            voice="voice-a",
        )
    )

    assert normalized.format == CANONICAL_FORMAT
    assert normalized.sample_rate_hz == CANONICAL_SAMPLE_RATE_HZ
    assert normalized.channels == 1
    assert normalized.sample_width_bytes == 2
    assert normalized.source_format == "wav"
    assert normalized.duration_seconds == pytest.approx(normalized.frame_count / 24_000)
    assert normalized.frame_count == 6


def test_provider_raw_pcm_output_resamples_and_normalizes_metadata() -> None:
    stereo = b"".join(
        left.to_bytes(2, "little", signed=True) + right.to_bytes(2, "little", signed=True)
        for left, right in ((100, 300), (300, 500), (500, 700), (700, 900))
    )

    normalized = normalize_raw_pcm16(stereo, sample_rate_hz=48_000, channels=2)

    assert normalized.sample_rate_hz == 24_000
    assert normalized.channels == 1
    assert normalized.frame_count == 2
    assert normalized.duration_seconds == pytest.approx(2 / 24_000)


def test_provider_api_raw_pcm_requires_sample_rate() -> None:
    with pytest.raises(AudioNormalizationError, match="sample_rate_hz"):
        normalize_provider_audio(
            TTSAudioResult(
                audio=b"\x00\x00",
                media_type="audio/L16",
                format="pcm_s16le",
                provider="fixture",
                voice="voice-a",
            )
        )


def test_corrupt_empty_and_unsupported_provider_outputs_are_rejected() -> None:
    with pytest.raises(AudioNormalizationError, match="empty"):
        normalize_provider_audio(TTSAudioResult(b"", "audio/wav", "wav", "fixture", "voice-a"))
    with pytest.raises(AudioNormalizationError, match="invalid WAV"):
        normalize_provider_audio(
            TTSAudioResult(b"not-a-wav", "audio/wav", "wav", "fixture", "voice-a")
        )
    with pytest.raises(AudioNormalizationError, match="MP3 decoding requires"):
        normalize_provider_audio(
            TTSAudioResult(b"ID3\x04\x00", "audio/mpeg", "mp3", "fixture", "voice-a")
        )


def _wav_bytes(*, sample_rate_hz: int, channels: int, frames: tuple[tuple[int, ...], ...]) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate_hz)
        payload = bytearray()
        for frame in frames:
            assert len(frame) == channels
            for sample in frame:
                payload.extend(sample.to_bytes(2, "little", signed=True))
        wav.writeframes(bytes(payload))
    return buffer.getvalue()
