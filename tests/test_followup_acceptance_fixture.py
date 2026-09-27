from __future__ import annotations

import json
import wave
from pathlib import Path

from followup_acceptance_fixture import (
    create_ready_followup_fixture,
    run_followup_fixture,
)

from deeper_dive import cli
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.tts_generation import TTSArtifactRepository


def test_reusable_followup_fixture_runs_generation_composition_and_export(
    tmp_path: Path,
) -> None:
    completed = run_followup_fixture(create_ready_followup_fixture(tmp_path))
    assert completed.run is not None
    assert completed.export is not None
    database = completed.database
    turns = HostTurnService(database).list_turns(completed.episode_id)

    assert completed.run.state == "completed"
    assert len(turns) == 1
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
    tmp_path: Path, capsys
) -> None:
    ready = create_ready_followup_fixture(tmp_path)
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
