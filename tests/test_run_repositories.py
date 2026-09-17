from __future__ import annotations

from pathlib import Path

from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord, HostEpisodeRepository
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord
from deeper_dive.storage.run_repositories import (
    CompletedUnitRecord,
    GenerationRunRecord,
    GenerationRunRepository,
)


def _repository(tmp_path: Path) -> GenerationRunRepository:
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("p1", "Project", "t0", "t0"))
    episodes = HostEpisodeRepository(database)
    episodes.create_episode(EpisodeRecord("e1", "p1", "Episode", "t0", "t0"), [])
    return GenerationRunRepository(database)


def test_run_stage_failure_flags_and_retry_state_survive_reopen(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    run = GenerationRunRecord("r1", "e1", "conversation", "running", "t0", "t0")
    repository.create(run)
    failed = repository.with_failure(
        run, code="provider_timeout", sanitized_message="provider timed out", modified_at="t1"
    )
    repository.update(failed)
    repository.request_pause("r1", "t2")
    repository.request_cancel("r1", "t3")

    reopened = GenerationRunRepository(Database(tmp_path / "project.db"))
    restored = reopened.get("r1")
    assert restored is not None
    assert restored.stage == "conversation"
    assert restored.state == "failed"
    assert restored.retry_count == 1
    assert restored.failure_code == "provider_timeout"
    assert restored.failure_message == "provider timed out"
    assert restored.pause_requested is True
    assert restored.cancel_requested is True


def test_completed_work_unit_checkpoint_is_idempotent_and_durable(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.create(GenerationRunRecord("r1", "e1", "tts", "running", "t0", "t0"))
    unit = CompletedUnitRecord("r1", "tts", "turn-0003", "t1")

    assert repository.complete_unit(unit) is True
    assert repository.complete_unit(unit) is False

    reopened = GenerationRunRepository(Database(tmp_path / "project.db"))
    assert reopened.list_completed_units("r1", "tts") == [unit]


def test_checkpoint_stage_namespaces_allow_same_unit_id(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.create(GenerationRunRecord("r1", "e1", "conversation", "running", "t0", "t0"))
    conversation = CompletedUnitRecord("r1", "conversation", "turn-1", "t1")
    tts = CompletedUnitRecord("r1", "tts", "turn-1", "t2")

    assert repository.complete_unit(conversation)
    assert repository.complete_unit(tts)
    assert repository.list_completed_units("r1", "conversation") == [conversation]
    assert repository.list_completed_units("r1", "tts") == [tts]
