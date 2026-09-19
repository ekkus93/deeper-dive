from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deeper_dive.application.events import ProgressEvent
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.pipeline import PipelineContext, PipelineOrchestrator
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository

STAGES = ("sources", "conversation", "tts", "export")


def make_repository(tmp_path) -> GenerationRunRepository:
    database = Database(tmp_path / "pipeline.sqlite3")
    repository = GenerationRunRepository(database)
    now = "2026-09-19T00:00:00.000000Z"
    with database.transaction() as db:
        db.execute(
            "INSERT INTO projects(id,name,created_at,modified_at) VALUES (?,?,?,?)",
            ("project", "Project", now, now),
        )
        db.execute(
            "INSERT INTO episodes(id,project_id,title,created_at,modified_at) VALUES (?,?,?,?,?)",
            ("episode", "project", "Episode", now, now),
        )
    repository.create(GenerationRunRecord("run", "episode", "sources", "pending", now, now))
    return repository


def test_fake_pipeline_completes_and_rerun_is_idempotent(tmp_path) -> None:
    repository = make_repository(tmp_path)
    calls: list[str] = []
    events: list[ProgressEvent] = []

    def handler(context: PipelineContext) -> None:
        calls.append(context.stage)

    orchestrator = PipelineOrchestrator(
        repository,
        {stage: handler for stage in STAGES},
        stages=STAGES,
        clock=FrozenClock(datetime(2026, 9, 19, tzinfo=UTC)),
        progress=events.append,
    )
    first = orchestrator.run("run")
    second = orchestrator.run("run")

    assert first.run.state == "completed"
    assert first.executed_stages == STAGES
    assert second.executed_stages == ()
    assert second.skipped_stages == STAGES
    assert calls == list(STAGES)
    for stage in STAGES:
        assert len(repository.list_completed_units("run", stage)) == 1
    assert events[-1].operation == "pipeline"
    assert events[-1].state == "completed"


def test_force_from_rebuilds_selected_stage_and_all_downstream(tmp_path) -> None:
    repository = make_repository(tmp_path)
    calls: list[str] = []

    def handler(context: PipelineContext) -> None:
        calls.append(context.stage)

    orchestrator = PipelineOrchestrator(
        repository,
        {stage: handler for stage in STAGES},
        stages=STAGES,
    )
    orchestrator.run("run")
    calls.clear()

    result = orchestrator.run("run", force_from="tts")

    assert calls == ["tts", "export"]
    assert result.skipped_stages == ("sources", "conversation")
    assert result.executed_stages == ("tts", "export")


def test_invalid_artifact_is_rebuilt_even_when_checkpoint_exists(tmp_path) -> None:
    repository = make_repository(tmp_path)
    calls: list[str] = []

    def handler(context: PipelineContext) -> None:
        calls.append(context.stage)

    orchestrator = PipelineOrchestrator(
        repository, {stage: handler for stage in STAGES}, stages=STAGES
    )
    orchestrator.run("run")
    calls.clear()

    orchestrator.run("run", artifact_valid=lambda stage: stage != "conversation")

    assert calls == ["conversation"]


def test_stage_retry_is_bounded_and_checkpointed_only_after_success(tmp_path) -> None:
    repository = make_repository(tmp_path)
    attempts = 0

    def flaky(context: PipelineContext) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("transient")

    handlers = {stage: (flaky if stage == "sources" else lambda context: None) for stage in STAGES}
    orchestrator = PipelineOrchestrator(repository, handlers, stages=STAGES, max_stage_retries=2)

    orchestrator.run("run")

    assert attempts == 3
    assert repository.list_completed_units("run", "sources")


def test_terminal_stage_failure_is_durable(tmp_path) -> None:
    repository = make_repository(tmp_path)

    def fail(context: PipelineContext) -> None:
        raise RuntimeError("provider unavailable")

    handlers = {stage: (fail if stage == "sources" else lambda context: None) for stage in STAGES}
    orchestrator = PipelineOrchestrator(repository, handlers, stages=STAGES, max_stage_retries=1)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        orchestrator.run("run")

    record = repository.get("run")
    assert record is not None
    assert record.state == "failed"
    assert record.failure_code == "stage_failed"
    assert record.retry_count == 1
    assert not repository.list_completed_units("run", "sources")


def test_configuration_bounds_are_validated(tmp_path) -> None:
    repository = make_repository(tmp_path)
    handlers = {stage: lambda context: None for stage in STAGES}
    with pytest.raises(ValueError, match="max_concurrency"):
        PipelineOrchestrator(repository, handlers, stages=STAGES, max_concurrency=0)
    with pytest.raises(ValueError, match="max_stage_retries"):
        PipelineOrchestrator(repository, handlers, stages=STAGES, max_stage_retries=-1)


def test_frozen_clock_serialization_used_for_durable_updates(tmp_path) -> None:
    repository = make_repository(tmp_path)
    instant = datetime(2026, 9, 19, 5, 0, tzinfo=UTC)
    handlers = {stage: lambda context: None for stage in STAGES}
    orchestrator = PipelineOrchestrator(
        repository, handlers, stages=STAGES, clock=FrozenClock(instant)
    )

    result = orchestrator.run("run")

    assert result.run.modified_at == format_timestamp(instant)


def test_pause_requested_before_stage_stops_without_losing_prior_units(tmp_path) -> None:
    repository = make_repository(tmp_path)
    calls: list[str] = []

    def handler(context: PipelineContext) -> None:
        calls.append(context.stage)

    orchestrator = PipelineOrchestrator(
        repository, {stage: handler for stage in STAGES}, stages=STAGES
    )
    repository.request_pause("run", "2026-09-19T00:01:00.000000Z")

    result = orchestrator.run("run")

    assert result.run.state == "paused"
    assert calls == []
    assert result.executed_stages == ()
    record = repository.get("run")
    assert record is not None
    assert record.pause_requested is True


def test_pause_during_uninterruptible_stage_finishes_stage_then_pauses(tmp_path) -> None:
    repository = make_repository(tmp_path)
    calls: list[str] = []
    events: list[ProgressEvent] = []

    def handler(context: PipelineContext) -> None:
        calls.append(context.stage)
        if context.stage == "conversation":
            repository.request_pause(context.run_id, "2026-09-19T00:02:00.000000Z")

    orchestrator = PipelineOrchestrator(
        repository, {stage: handler for stage in STAGES}, stages=STAGES, progress=events.append
    )

    result = orchestrator.run("run")

    assert result.run.state == "paused"
    assert result.executed_stages == ("sources", "conversation")
    assert calls == ["sources", "conversation"]
    assert repository.list_completed_units("run", "conversation")
    assert events[-1].state == "paused"


def test_resume_after_restart_continues_from_durable_stage_boundaries(tmp_path) -> None:
    repository = make_repository(tmp_path)

    def pause_on_conversation(context: PipelineContext) -> None:
        if context.stage == "conversation":
            repository.request_pause(context.run_id, "2026-09-19T00:02:00.000000Z")

    first = PipelineOrchestrator(
        repository, {stage: pause_on_conversation for stage in STAGES}, stages=STAGES
    )
    paused = first.run("run")
    assert paused.run.state == "paused"

    calls: list[str] = []

    def handler(context: PipelineContext) -> None:
        calls.append(context.stage)

    restarted = PipelineOrchestrator(
        repository, {stage: handler for stage in STAGES}, stages=STAGES
    )
    restarted.resume("run")
    resumed = restarted.run("run")

    assert resumed.run.state == "completed"
    assert resumed.skipped_stages == ("sources", "conversation")
    assert calls == ["tts", "export"]


def test_cancel_during_tts_preserves_completed_units_and_stops_downstream(tmp_path) -> None:
    repository = make_repository(tmp_path)
    calls: list[str] = []

    def handler(context: PipelineContext) -> None:
        calls.append(context.stage)
        if context.stage == "tts":
            repository.request_cancel(context.run_id, "2026-09-19T00:03:00.000000Z")

    orchestrator = PipelineOrchestrator(
        repository, {stage: handler for stage in STAGES}, stages=STAGES
    )

    result = orchestrator.run("run")

    assert result.run.state == "cancelled"
    assert result.executed_stages == ("sources", "conversation", "tts")
    assert calls == ["sources", "conversation", "tts"]
    assert repository.list_completed_units("run", "tts")
    assert not repository.list_completed_units("run", "export")


def test_cancelled_runs_cannot_resume(tmp_path) -> None:
    repository = make_repository(tmp_path)
    orchestrator = PipelineOrchestrator(
        repository, {stage: lambda context: None for stage in STAGES}, stages=STAGES
    )
    repository.request_cancel("run", "2026-09-19T00:03:00.000000Z")
    cancelled = orchestrator.run("run")
    assert cancelled.run.state == "cancelled"

    with pytest.raises(ValueError, match="cancelled"):
        orchestrator.resume("run")
