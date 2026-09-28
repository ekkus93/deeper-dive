from __future__ import annotations

import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.tts_generation import TTS_ARTIFACT_STATUS_COMPLETE
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_production_pipeline_persists_reviewable_and_exportable_quick_episode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_ffmpeg(tmp_path, monkeypatch)
    data_dir = tmp_path / "data"
    config_store = UserConfigStore(data_dir / "config.json")
    planner = ProviderConfig(provider_type="fake", default_model="fake-v1")
    speech = ProviderConfig(provider_type="fake-tts")
    config_store.save(
        UserConfig(
            providers={"planner": planner, "speech": speech},
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
    project = composition.service.create_project("Quick durable workflow")
    root = composition.service.workspaces.project_root(project.id)
    database = composition.database_for_project(project.id)

    episode = composition.service.quick_deep_dive(project.id)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE hosts SET tts_provider='speech',tts_voice='voice-a' WHERE project_id=?",
            (project.id,),
        )
    configs = EpisodeConfigurationService(database)
    quick_config = configs.load_configuration(episode.id)
    episode = configs.edit(episode.id, replace(quick_config, focus="indexed corpus"))
    run = composition.create_generation_run(project.id, episode.id)

    result = composition.run_generation(project.id, run.id)

    with database.connection() as connection:
        turns = connection.execute(
            "SELECT id,text FROM conversation_turns WHERE episode_id=?",
            (episode.id,),
        ).fetchall()
        artifacts = connection.execute(
            "SELECT turn_id,status,path FROM tts_artifacts ORDER BY turn_id"
        ).fetchall()
    output_audio = root / "output" / f"{episode.id}.wav"
    timeline = AudioTimelineRepository(database).get(episode.id)
    export_service = EpisodeLibraryExportService(composition.service.workspaces)
    export = export_service.export(project.id, episode, result.run)

    assert result.run.state == "completed"
    assert turns
    assert "Configured fake provider host turn marker" in str(turns[0]["text"])
    assert artifacts
    assert all(str(row["status"]) == TTS_ARTIFACT_STATUS_COMPLETE for row in artifacts)
    assert output_audio.is_file()
    assert timeline is not None
    assert timeline.placements
    assert export.transcript.is_file()
    transcript = export.transcript.read_text(encoding="utf-8")
    assert "Configured fake provider host turn marker" in transcript
    assert export.audio is not None
    assert export.audio.is_file()


def _install_fake_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    current_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{current_path}")
    real_which = shutil.which

    def fake_which(command: str, *args, **kwargs):
        if command == "ffmpeg":
            return str(executable)
        return real_which(command, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", fake_which)
