from __future__ import annotations

import json
import wave
from pathlib import Path

from followup_acceptance_fixture import (
    create_additional_ready_episode,
    create_ready_followup_fixture,
    run_followup_fixture,
)

from deeper_dive import cli
from deeper_dive.audio_timeline import AudioTimelineRepository
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
    assert turns[0].evidence_ids == (completed.chunk_id,)

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
    assert f"Citations: {completed.chunk_id}" in transcript
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


def test_followup_fixture_supports_cancel_control(tmp_path: Path, monkeypatch) -> None:
    ready = create_ready_followup_fixture(tmp_path)
    _patch_ffmpeg_detect(monkeypatch, ready.ffmpeg)
    run = ready.composition.create_generation_run(ready.project_id, ready.episode_id)
    pipeline = ready.composition.generation_pipeline(ready.project_id)

    pipeline.request_cancel(run.id)
    cancelled = ready.composition.run_generation(ready.project_id, run.id).run

    assert cancelled.id == run.id
    assert cancelled.state == "cancelled"


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

    completed = app.composition.run_generation(ready.project_id, first.id).run
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
    assert all(turn.evidence_ids == (ready.chunk_id,) for turn in turns)
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
    assert f"Citations: {ready.chunk_id}" in exported.transcript.read_text(encoding="utf-8")


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
    assert turns[0].evidence_ids == (ready.chunk_id,)
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
    assert f"Citations: {ready.chunk_id}" in transcript.read_text(encoding="utf-8")
    assert audio.is_file()
    with wave.open(str(audio), "rb") as wav:
        assert wav.getnframes() > 0


def test_followup_fixture_cli_generate_auto_plans_and_consumes_persisted_plan(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    ready = create_ready_followup_fixture(tmp_path, with_plan=False)
    _patch_ffmpeg_detect(monkeypatch, ready.ffmpeg)
    repository = HostEpisodeRepository(ready.database)
    assert repository.get_plan(ready.episode_id) is None

    assignments, errors = ready.composition.effective_model_role_assignments_for_episode(
        ready.project_id, ready.episode_id
    )
    assert not errors
    planning = assignments.resolve(ModelRole.EPISODE_PLANNING)
    assert planning is not None
    assert (planning.provider, planning.model) == ("dialogue", "fake-v1")

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

    plan = repository.get_plan(ready.episode_id)
    assert plan is not None
    segments = repository.list_segments(plan.id)
    assert segments
    assert segments[0].title == "Overview"
    turns = HostTurnService(ready.database).list_turns(ready.episode_id)
    assert len(turns) > 1


def test_followup_fixture_tui_generate_shares_auto_planning_boundary(
    tmp_path: Path, monkeypatch
) -> None:
    ready = create_ready_followup_fixture(tmp_path, with_plan=False)
    _patch_ffmpeg_detect(monkeypatch, ready.ffmpeg)
    repository = HostEpisodeRepository(ready.database)
    assert repository.get_plan(ready.episode_id) is None

    app = DeeperDiveApp(service=ready.composition.service)
    app.current_project_id = ready.project_id
    app.current_project_name = "R6 shared acceptance"
    app.current_episode_id = ready.episode_id
    app.preflight_controller.ffmpeg_executable = ready.ffmpeg

    presentation = app.preflight_controller.build(app)
    assert presentation.report.ready
    run = app.preflight_controller.start_generation(app)
    completed = app.composition.run_generation(ready.project_id, run.id).run
    assert completed.state == "completed"

    plan = repository.get_plan(ready.episode_id)
    assert plan is not None
    segments = repository.list_segments(plan.id)
    assert segments
    assert segments[0].title == "Overview"
    turns = HostTurnService(ready.database).list_turns(ready.episode_id)
    assert len(turns) > 1


def test_followup_fixture_keeps_two_episodes_isolated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first_ready = create_ready_followup_fixture(tmp_path)
    second_ready = create_additional_ready_episode(first_ready)
    _patch_ffmpeg_detect(monkeypatch, first_ready.ffmpeg)

    first = run_followup_fixture(first_ready)
    second = run_followup_fixture(second_ready)
    assert first.export is not None
    assert second.export is not None

    database = first_ready.database
    first_turns = HostTurnService(database).list_turns(first_ready.episode_id)
    second_turns = HostTurnService(database).list_turns(second_ready.episode_id)
    assert first_turns
    assert second_turns
    assert {turn.id for turn in first_turns}.isdisjoint(turn.id for turn in second_turns)
    assert all(turn.evidence_ids == (first_ready.chunk_id,) for turn in first_turns)
    assert all(turn.evidence_ids == (second_ready.chunk_id,) for turn in second_turns)

    timeline_repository = AudioTimelineRepository(database)
    first_timeline = timeline_repository.get(first_ready.episode_id)
    second_timeline = timeline_repository.get(second_ready.episode_id)
    assert first_timeline is not None
    assert second_timeline is not None
    assert first_timeline.episode_id == first_ready.episode_id
    assert second_timeline.episode_id == second_ready.episode_id
    first_timeline_turns = {item.turn_id for item in first_timeline.items if item.turn_id}
    second_timeline_turns = {item.turn_id for item in second_timeline.items if item.turn_id}
    assert first_timeline_turns == {turn.id for turn in first_turns}
    assert second_timeline_turns == {turn.id for turn in second_turns}
    assert first_timeline_turns.isdisjoint(second_timeline_turns)

    first_transcript = first.export.transcript.read_text(encoding="utf-8")
    second_transcript = second.export.transcript.read_text(encoding="utf-8")
    assert f"Citations: {first_ready.chunk_id}" in first_transcript
    assert f"Citations: {second_ready.chunk_id}" not in first_transcript
    assert f"Citations: {second_ready.chunk_id}" in second_transcript
    assert f"Citations: {first_ready.chunk_id}" not in second_transcript
    assert first.export.audio != second.export.audio


def _patch_ffmpeg_detect(monkeypatch, ffmpeg: Path) -> None:
    monkeypatch.setattr(
        FFmpegConfig,
        "detect",
        classmethod(lambda cls, configured=None: cls(ffmpeg)),
    )
