from __future__ import annotations

import json
from pathlib import Path

from followup_acceptance_fixture import (
    create_ready_followup_fixture,
    run_followup_fixture,
)

from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.composition import ProductionComposition
from deeper_dive.host_turn import HostTurnService
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.user_config import UserConfigStore


def test_persisted_state_reopens(tmp_path: Path, monkeypatch) -> None:
    ready = create_ready_followup_fixture(tmp_path)
    monkeypatch.setattr(
        "deeper_dive.ffmpeg.FFmpegConfig.detect",
        classmethod(lambda cls, configured=None: cls(ready.ffmpeg)),
    )
    completed = run_followup_fixture(ready)
    assert completed.run is not None
    assert completed.export is not None

    config = UserConfigStore(ready.data_dir / "config.json").load()
    assert set(config.providers) == {"dialogue", "speech"}

    reopened = ProductionComposition.build(
        ready.data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    database = reopened.database_for_project(ready.project_id)
    episode = HostEpisodeRepository(database).get_episode(ready.episode_id)
    run = reopened.service.runs(ready.project_id).get(completed.run.id)
    turn_service = HostTurnService(database)
    turns = turn_service.list_turns(ready.episode_id)
    timeline = AudioTimelineRepository(database).get(ready.episode_id)

    assert episode is not None
    assert run is not None
    assert run.state == "completed"
    assert len(turns) > 1
    for turn in turns:
        identity = turn_service.provider_identity(turn.id)
        assert identity is not None
        assert identity.provider_id == "dialogue"
        assert identity.model == "fake-v1"
    assert timeline is not None
    assert timeline.episode_id == ready.episode_id

    transcript = completed.export.transcript.read_text(encoding="utf-8")
    manifest_text = completed.export.manifest.read_text(encoding="utf-8")
    metadata_text = completed.export.metadata.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    metadata = json.loads(metadata_text)
    assert transcript.strip()
    assert manifest
    assert metadata["episode_id"] == ready.episode_id
    assert metadata["run_id"] == completed.run.id
    assert completed.export.audio is not None
    assert completed.export.audio.is_file()
