from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive import cli as cli_module
from deeper_dive.cli import main
from deeper_dive.composition import ProductionComposition
from deeper_dive.ffmpeg import FFmpegConfig
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _json_call(args: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def _build_project_with_episode(data_dir: Path) -> tuple[ProductionComposition, str, str]:
    UserConfigStore(data_dir / "config.json").save(
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
    project = composition.service.create_project("CLI control")
    composition.service.add_pasted_source(project.id, "Fixture", "Indexed source text.")
    episode = composition.service.quick_deep_dive(project.id)
    with composition.database_for_project(project.id).transaction() as connection:
        connection.execute(
            "UPDATE hosts SET tts_provider='speech',tts_voice='voice-a' WHERE project_id=?",
            (project.id,),
        )
    return composition, project.id, episode.id


def test_cli_pause_reaches_durable_paused_state_and_resume_executes_from_checkpoint(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_ffmpeg = _fake_ffmpeg_executable(tmp_path)
    data_dir = tmp_path / "data"
    composition, project_id, episode_id = _build_project_with_episode(data_dir)
    run = composition.create_generation_run(project_id, episode_id)
    monkeypatch.setattr(
        "deeper_dive.ffmpeg.FFmpegConfig.detect",
        staticmethod(lambda executable=None: FFmpegConfig(fake_ffmpeg)),
    )
    monkeypatch.setattr(
        cli_module.ProductionComposition,
        "build",
        staticmethod(lambda data_dir=None: composition),
    )
    base = ["--data-dir", str(data_dir), "--json", "episode"]

    paused = _json_call([*base, "pause", project_id, episode_id], capsys)

    assert paused["id"] == run.id
    assert paused["state"] == "paused"
    persisted_pause = composition.generation_run_repository(project_id).get(run.id)
    assert persisted_pause is not None
    assert persisted_pause.state == "paused"

    resumed = _json_call([*base, "resume", project_id, episode_id], capsys)

    assert resumed["id"] == run.id
    assert resumed["state"] == "completed"
    assert resumed["stage"] == "export"
    root = composition.service.workspaces.project_root(project_id)
    assert (root / "output" / f"{episode_id}.wav").is_file()
    with composition.database_for_project(project_id).connection() as connection:
        turns = connection.execute(
            "SELECT COUNT(*) FROM conversation_turns WHERE episode_id=?",
            (episode_id,),
        ).fetchone()[0]
    assert turns > 0


def test_cli_cancel_reaches_durable_cancelled_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    composition, project_id, episode_id = _build_project_with_episode(data_dir)
    run = composition.create_generation_run(project_id, episode_id)
    monkeypatch.setattr(
        cli_module.ProductionComposition,
        "build",
        staticmethod(lambda data_dir=None: composition),
    )
    base = ["--data-dir", str(data_dir), "--json", "episode"]

    cancelled = _json_call([*base, "cancel", project_id, episode_id], capsys)

    assert cancelled["id"] == run.id
    assert cancelled["state"] == "cancelled"
    persisted_cancel = composition.generation_run_repository(project_id).get(run.id)
    assert persisted_cancel is not None
    assert persisted_cancel.state == "cancelled"


def test_cli_rejects_illegal_control_transitions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_ffmpeg = _fake_ffmpeg_executable(tmp_path)
    data_dir = tmp_path / "data"
    composition, project_id, episode_id = _build_project_with_episode(data_dir)
    monkeypatch.setattr(
        "deeper_dive.ffmpeg.FFmpegConfig.detect",
        staticmethod(lambda executable=None: FFmpegConfig(fake_ffmpeg)),
    )
    monkeypatch.setattr(
        cli_module.ProductionComposition,
        "build",
        staticmethod(lambda data_dir=None: composition),
    )
    base = ["--data-dir", str(data_dir), "--json", "episode"]

    completed = _json_call([*base, "generate", project_id, episode_id], capsys)
    assert completed["state"] == "completed"

    assert main([*base, "pause", project_id, episode_id]) == 2
    captured = capsys.readouterr()
    assert "cannot pause generation run in completed state" in captured.err

    assert main([*base, "resume", project_id, episode_id]) == 2
    captured = capsys.readouterr()
    assert "cannot resume generation run in completed state" in captured.err


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
