from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from deeper_dive.cli import main
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.ffmpeg import FFmpegConfig
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_cli_episode_export_uses_shared_artifact_exporter(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_ffmpeg = _fake_ffmpeg_executable(tmp_path)
    monkeypatch.setattr(
        "deeper_dive.ffmpeg.FFmpegConfig.detect",
        staticmethod(lambda executable=None: FFmpegConfig(fake_ffmpeg)),
    )
    data_dir = tmp_path / "data"
    config_store = UserConfigStore(data_dir / "config.json")
    config_store.save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={
                "episode_planning": "planner:fake-v1",
                "host_generation": "planner:fake-v1",
            },
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("CLI export")
    episode = composition.service.quick_deep_dive(project.id)
    database = composition.database_for_project(project.id)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE hosts SET tts_provider='speech',tts_voice='voice-a' WHERE project_id=?",
            (project.id,),
        )
    configs = EpisodeConfigurationService(database)
    config = configs.load_configuration(episode.id)
    configs.edit(episode.id, replace(config, focus="focused deep dive"))
    run = composition.create_generation_run(project.id, episode.id)
    result = composition.run_generation(project.id, run.id)
    assert result.run.state == "completed"

    output_dir = tmp_path / "cli-exports"
    exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "--json",
            "episode",
            "export",
            project.id,
            episode.id,
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    exported_paths = {Path(value) for value in payload["paths"]}
    assert exported_paths == {
        Path(payload["transcript"]),
        Path(payload["manifest"]),
        Path(payload["metadata"]),
        Path(payload["audio"]),
    }
    assert {path.parent for path in exported_paths} == {output_dir}
    transcript = Path(payload["transcript"]).read_text(encoding="utf-8")
    assert "deterministic production turn" in transcript
    assert json.loads(Path(payload["manifest"]).read_text(encoding="utf-8")) == {"sources": []}
    metadata = json.loads(Path(payload["metadata"]).read_text(encoding="utf-8"))
    assert metadata["episode_id"] == episode.id
    assert metadata["run_id"] == result.run.id
    assert Path(payload["audio"]).read_bytes().startswith(b"RIFF")


def _fake_ffmpeg_executable(tmp_path: Path) -> Path:
    executable = tmp_path / "ffmpeg"
    executable.write_text(
        r"""#!/usr/bin/env python3
import io
import sys
import wave

payload = sys.stdin.buffer.read()
args = sys.argv[1:]
try:
    first_format = args[args.index('-f') + 1]
except (ValueError, IndexError):
    sys.stderr.write('missing input format')
    sys.exit(2)

if first_format == 'wav':
    try:
        with wave.open(io.BytesIO(payload), 'rb') as wav:
            source_rate = wav.getframerate()
            frame_count = wav.getnframes()
    except (EOFError, wave.Error) as exc:
        sys.stderr.write(f'invalid wav: {exc}')
        sys.exit(1)
elif first_format == 's16le':
    try:
        source_rate = int(args[args.index('-ar') + 1])
        channels = int(args[args.index('-ac') + 1])
    except (ValueError, IndexError) as exc:
        sys.stderr.write(f'invalid raw args: {exc}')
        sys.exit(2)
    frame_size = channels * 2
    if not payload or len(payload) % frame_size != 0:
        sys.stderr.write('misaligned raw input')
        sys.exit(1)
    frame_count = len(payload) // frame_size
else:
    sys.stderr.write(f'unsupported input format: {first_format}')
    sys.exit(2)

target_frames = max(1, round(frame_count * 24000 / source_rate))
sys.stdout.buffer.write(b'\x00\x00' * target_frames)
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable
