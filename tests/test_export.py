import json
import wave
from pathlib import Path
from unittest.mock import patch

from deeper_dive.audio_normalization import CanonicalAudio
from deeper_dive.export import EpisodeExporter, ManifestSource, TranscriptTurn
from deeper_dive.ffmpeg import FFmpegComposer, FFmpegConfig


def audio() -> CanonicalAudio:
    return CanonicalAudio(b"\x00\x00" * 240, 24000, 1, 2, 0.01, "wav", "audio/wav")


def test_exports_wav_transcript_manifest_and_secret_safe_metadata(tmp_path: Path) -> None:
    exporter = EpisodeExporter(tmp_path)
    stem = exporter.reserve_stem("My Episode")
    wav_path = exporter.write_wav(stem.with_suffix(".wav"), audio())
    exporter.write_transcript(
        stem.with_suffix(".md"), "My Episode", (TranscriptTurn("Ada", "Hello evidence."),)
    )
    manifest = tmp_path / "manifest.json"
    exporter.write_manifest(
        manifest,
        (
            ManifestSource("User paper", "user", "p. 1"),
            ManifestSource("Web research", "supplemental", "https://example.test"),
        ),
    )
    metadata = tmp_path / "metadata.json"
    exporter.write_metadata(
        metadata, {"episode": "e1", "provider": {"model": "m", "api_key": "NEVER_EXPORT"}}
    )
    with wave.open(str(wav_path), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getnframes()) == (24000, 1, 240)
    assert "Hello evidence." in stem.with_suffix(".md").read_text()
    origins = [item["origin"] for item in json.loads(manifest.read_text())["sources"]]
    assert origins == ["user", "supplemental"]
    assert "NEVER_EXPORT" not in metadata.read_text()
    assert "api_key" not in metadata.read_text()


def test_collision_handling_is_stable(tmp_path: Path) -> None:
    exporter = EpisodeExporter(tmp_path)
    (tmp_path / "my-episode.wav").write_bytes(b"old")
    assert exporter.reserve_stem("My Episode").name == "my-episode-2"


def test_mp3_export_uses_safe_ffmpeg_argv(tmp_path: Path) -> None:
    wav_path = tmp_path / "input ; weird.wav"
    mp3_path = tmp_path / "output $(safe).mp3"
    composer = FFmpegComposer(FFmpegConfig(Path("ffmpeg")))
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        EpisodeExporter.write_mp3(wav_path, mp3_path, composer)
    args = run.call_args.args[0]
    assert str(wav_path) in args and str(mp3_path) in args
    assert run.call_args.kwargs["shell"] is False
