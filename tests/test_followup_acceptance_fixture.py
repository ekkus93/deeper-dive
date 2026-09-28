from __future__ import annotations

import json
import wave
from pathlib import Path

from followup_acceptance_fixture import (
    create_ready_followup_fixture,
    run_followup_fixture,
)

from deeper_dive import cli
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_library_screen import EpisodeLibraryController
from deeper_dive.ffmpeg import FFmpegConfig
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.model_roles import ModelRole
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.tts_generation import TTSArtifactRepository
from deeper_dive.tui import DeeperDiveApp


def test_reusable_followup_fixture_runs_generation_composition_and_export(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ready = create_ready_followup_fixture(tmp_path)
    _patch_ffmpeg_detect(monkeypatch, ready.ffmpeg)
    completed = run_followup_fixture(ready)
    assert completed.run is not None
    assert completed.export is not None
    database = completed.database
    turns = HostTurnService(database).list_turns(completed.episode_id)

    assert completed.run.state == "completed"
    assert len(turns) > 1
    assert "Configured fake provider host turn marker" in turns[0].text
    assert "Configured fake directing decision marker" in turns[0].text
    assert turns[0].evidence_ids == ("chunk-r6",)

    artifact = TTSArtifactRepository(database).get_by_turn_id(turns[0].id)
    assert artifact is not None
    assert artifact.provider_id == "speech"
    assert artifact.voice == "voice-a"
    assert artifact.format == "wav"
    assert artifact.path.suffix == ".wav"
    assert artifact.path.is_file()

    assert completed.export.audio is not None
    with wave.open(str(completed.export.audio), "rb") as audio:
        assert audio.getframerate() == 24000
        assert audio.getnframes() > 0
    transcript = completed.export.transcript.read_text(encoding="utf-8")
    assert "Citations: chunk-r6" in transcript
    assert "R6 acceptance source marker" in transcript


def test_followup_fixture_supports_duplicate_start_pause_resume_and_cli_export(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    ready = create_ready_followup_fixture(tmp_path)
    _patch_ffmpeg_detect(monkeypatch, ready.ffmpeg)
    starter = GenerationStartService(ready.composition, ffmpeg_executable=ready.ffmpeg)

    first = starter.start(ready.project_id, ready.episode_id)
    second = starter.start(ready.project_id, ready.episode_id)

    assert first.run.id == second.run.id

    pipeline = ready.composition.generation_pipeline(ready.project_id)
    pipeline.request_pause(first.run.id)
    paused = ready.composition.run_generation(ready.project_id, first.run.id).run
    assert paused.state == "paused"
    resumed = pipeline.resume(first.run.id)
    completed = ready.composition.run_generation(ready.project_id, resumed.id).run
    assert completed.state == "completed"

    status_code = cli.main(
        [
            "--data-dir",
            str(ready.data_dir),
            "--json",
            "episode",
            "status",
            ready.project_id,
            ready.episode_id,
        ]
    )
    status_output = json.loads(capsys.readouterr().out)
    assert status_code == 0
    assert status_output["run"]["id"] == completed.id
    assert status_output["run"]["state"] == "completed"

    output_dir = tmp_path / "cli-export"
    export_code = cli.main(
        [
            "--data-dir",
            str(ready.data_dir),
            "--json",
            "episode",
            "export",
            ready.project_id,
            ready.episode_id,
            "--output-dir",
            str(output_dir),
        ]
    )
    export_output = json.loads(capsys.readouterr().out)
    assert export_code == 0
    assert Path(export_output["transcript"]).is_file()
    audio = Path(export_output["audio"])
    assert audio.is_file()
    with wave.open(str(audio), "rb") as wav:
        assert wav.getnframes() > 0

    episode = HostEpisodeRepository(ready.database).get_episode(ready.episode_id)
    assert episode is not None


def test_followup_fixture_drives_tui_preflight_generation_monitor_review_and_export(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ready = create_ready_followup_fixture(tmp_path)
    _patch_ffmpeg_detect(monkeypatch, ready.ffmpeg)
    app = DeeperDiveApp(service=ready.composition.service)
    app.current_project_id = ready.project_id
    app.current_project_name = "R6 shared acceptance"
    app.current_episode_id = ready.episode_id
    app.preflight_controller.ffmpeg_executable = ready.ffmpeg

    app.provider_controller.save_provider(
        "dialogue",
        "fake",
        default_model="fake-v1",
    )
    app.provider_controller.reload()

    presentation = app.preflight_controller.build(app)
    assert presentation.report.ready

    first = app.preflight_controller.start_generation(app)
    second = app.preflight_controller.start_generation(app)
    assert first.id == second.id

    composition = app.service._production_composition  # type: ignore[attr-defined]
    completed = composition.run_generation(ready.project_id, first.id).run
    assert completed.state == "completed"

    snapshot = app.generation_monitor_controller.snapshot(app)
    assert snapshot.run is not None
    assert snapshot.run.id == completed.id
    assert snapshot.run.state == "completed"
    assert snapshot.recent_turns
    assert "Configured fake provider host turn marker" in snapshot.recent_turns[0]

    review = TranscriptReviewController()
    turns = review.turns(app)
    assert len(turns) > 1
    assert all(turn.evidence_ids == ("chunk-r6",) for turn in turns)
    passages = review.passages(app, turns[0].evidence_ids)
    assert len(passages) == 1
    assert "R6 acceptance source marker" in passages[0].text

    items = EpisodeLibraryController.items(app)
    item = next(item for item in items if item.episode.id == ready.episode_id)
    assert item.run is not None
    assert item.run.state == "completed"
    exported = EpisodeLibraryController.export(app, item)
    assert exported.audio is not None
    assert exported.audio.is_file()
    assert exported.transcript.is_file()
    assert "Citations: chunk-r6" in exported.transcript.read_text(encoding="utf-8")


def test_followup_fixture_drives_explicit_cli_generation_status_and_export(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    ready = create_ready_followup_fixture(tmp_path)
    _patch_ffmpeg_detect(monkeypatch, ready.ffmpeg)

    generate_code = cli.main(
        [
            "--data-dir",
            str(ready.data_dir),
            "--json",
            "episode",
            "generate",
            ready.project_id,
            ready.episode_id,
        ]
    )
    generated = json.loads(capsys.readouterr().out)
    assert generate_code == 0
    assert generated["state"] == "completed"

    composition = ProductionComposition.build(
        ready.data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    assignments, errors = composition.effective_model_role_assignments_for_episode(
        ready.project_id, ready.episode_id
    )
    assert not errors
    planning = assignments.resolve(ModelRole.EPISODE_PLANNING)
    assert planning is not None
    assert (planning.provider, planning.model) == ("dialogue", "fake-v1")

    database = composition.database_for_project(ready.project_id)
    turns = HostTurnService(database).list_turns(ready.episode_id)
    assert len(turns) > 1
    assert turns[0].evidence_ids == ("chunk-r6",)
    artifact = TTSArtifactRepository(database).get_by_turn_id(turns[0].id)
    assert artifact is not None
    assert (artifact.provider_id, artifact.voice, artifact.format) == (
        "speech",
        "voice-a",
        "wav",
    )

    status_code = cli.main(
        [
            "--data-dir",
            str(ready.data_dir),
            "--json",
            "episode",
            "status",
            ready.project_id,
            ready.episode_id,
        ]
    )
    status = json.loads(capsys.readouterr().out)
    assert status_code == 0
    assert status["run"]["state"] == "completed"

    output_dir = tmp_path / "explicit-cli-export"
    export_code = cli.main(
        [
            "--data-dir",
            str(ready.data_dir),
            "--json",
            "episode",
            "export",
            ready.project_id,
            ready.episode_id,
            "--output-dir",
            str(output_dir),
        ]
    )
    exported = json.loads(capsys.readouterr().out)
    assert export_code == 0
    transcript = Path(exported["transcript"])
    audio = Path(exported["audio"])
    assert transcript.is_file()
    assert "Citations: chunk-r6" in transcript.read_text(encoding="utf-8")
    assert audio.is_file()
    with wave.open(str(audio), "rb") as wav:
        assert wav.getnframes() > 0


def _patch_ffmpeg_detect(monkeypatch, ffmpeg: Path) -> None:
    monkeypatch.setattr(
        FFmpegConfig,
        "detect",
        classmethod(lambda cls, configured=None: cls(ffmpeg)),
    )
