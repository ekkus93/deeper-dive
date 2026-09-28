from __future__ import annotations

import wave
from pathlib import Path

import deeper_dive.composition as composition_module
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.composition import ProductionComposition
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.tui import DeeperDiveApp
from tests.test_transcript_review_screen import (
    _configure_fake_repair_provider,
    _insert_repair_worthy_claim,
    _project_with_episode,
)


def test_regenerate_episode_audio_sanitizes_runtime_failure(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / 'data'))
    service.workspaces.initialize()
    project = service.create_project('Failure Case')
    composition = ProductionComposition.build(service=service)

    def fail_stage(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError('token=secret-value runtime exploded')

    monkeypatch.setattr(composition_module, '_tts_stage', fail_stage)

    try:
        composition.regenerate_episode_audio(project.id, 'episode-1')
    except RuntimeError as error:
        message = str(error)
    else:
        raise AssertionError('expected audio regeneration failure')

    assert 'episode audio regeneration failed:' in message
    assert '[REDACTED]' in message
    assert 'secret-value' not in message


def test_controller_repair_regenerates_audio_timeline_and_review_export(
    tmp_path: Path,
) -> None:
    service, project_id, episode_id = _project_with_episode(tmp_path)
    _configure_fake_repair_provider(service)
    database = Database(service.workspaces.project_root(project_id) / 'project.db')
    _insert_repair_worthy_claim(database, project_id, episode_id)
    output = service.workspaces.project_root(project_id) / 'output'
    output.mkdir(parents=True, exist_ok=True)
    episode_audio = output / f'{episode_id}.wav'
    episode_audio.write_bytes(b'stale audio')
    with database.transaction() as connection:
        connection.execute(
            '''INSERT INTO tts_artifacts(
                turn_id,artifact_id,cache_key,status,path,provider_id,voice,model
            ) VALUES (?,?,?,?,?,?,?,?)''',
            (
                'turn-1',
                'artifact-1',
                'cache-1',
                'completed',
                str(episode_audio),
                'tts',
                'h1',
                'm',
            ),
        )

    app = DeeperDiveApp(service)
    app.current_project_id = project_id
    app.current_episode_id = episode_id
    controller = TranscriptReviewController()

    repaired = controller.repair_turn('turn-1', app)
    export_path = controller.export_markdown(app)

    assert repaired is not None
    assert export_path.is_file()
    exported = export_path.read_text(encoding='utf-8')
    assert '# Transcript review:' in exported
    assert 'segments' in exported
    assert episode_audio.exists()
    with wave.open(str(episode_audio), 'rb') as wav:
        assert wav.getnframes() > 0
    timeline = AudioTimelineRepository(database).get(episode_id)
    assert timeline is not None
    assert timeline.placements[0].item.turn_id == 'turn-1'
