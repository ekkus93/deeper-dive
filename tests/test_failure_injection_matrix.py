from __future__ import annotations

from dataclasses import dataclass

import pytest

from deeper_dive.failure_injection import (
    FailureInjector,
    FailurePoint,
    InjectedPipelineFailure,
    run_checkpointed_units,
)
from deeper_dive.pipeline import PipelineContext, PipelineOrchestrator
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository

STAGES = (
    "sources",
    "research",
    "planning",
    "conversation",
    "verification",
    "tts",
    "composition",
    "export",
)
UNITS = {
    "sources": ("parse", "index"),
    "research": ("gap-search", "candidate-fetch"),
    "planning": ("outline", "segments"),
    "conversation": ("turn-001", "turn-002", "turn-003", "summary"),
    "verification": ("extract", "retrieve", "classify"),
    "tts": ("turn-001", "turn-002", "turn-003"),
    "composition": ("normalize", "compose"),
    "export": ("wav", "mp3", "manifest"),
}


@dataclass(frozen=True, slots=True)
class MatrixCase:
    name: str
    point: FailurePoint


MATRIX_CASES = (
    MatrixCase("after source parse", FailurePoint("sources", "parse")),
    MatrixCase("during research", FailurePoint("research", "gap-search")),
    MatrixCase("during planning", FailurePoint("planning", "outline")),
    MatrixCase("arbitrary conversation turn", FailurePoint("conversation", "turn-002")),
    MatrixCase("during verification", FailurePoint("verification", "retrieve")),
    MatrixCase("arbitrary TTS turn", FailurePoint("tts", "turn-002")),
    MatrixCase("during composition", FailurePoint("composition", "compose")),
    MatrixCase("during export", FailurePoint("export", "mp3")),
)


def make_repository(tmp_path) -> GenerationRunRepository:
    database = Database(tmp_path / "failure-matrix.sqlite3")
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


def handlers_for(
    repository: GenerationRunRepository,
    injector: FailureInjector,
    calls: list[tuple[str, str]],
):
    def make_handler(stage: str):
        def handler(context: PipelineContext) -> None:
            def work(unit_id: str) -> None:
                calls.append((stage, unit_id))

            run_checkpointed_units(
                context,
                repository,
                UNITS[stage],
                work,
                injector=injector,
            )

        return handler

    return {stage: make_handler(stage) for stage in STAGES}


def completed_units(repository: GenerationRunRepository) -> set[tuple[str, str]]:
    return {
        (stage, unit.unit_id)
        for stage in STAGES
        for unit in repository.list_completed_units("run", stage)
    }


@pytest.mark.parametrize("case", MATRIX_CASES, ids=[case.name for case in MATRIX_CASES])
def test_failure_matrix_preserves_committed_units_and_resumes(tmp_path, case: MatrixCase) -> None:
    repository = make_repository(tmp_path)
    injector = FailureInjector((case.point,))
    calls: list[tuple[str, str]] = []
    orchestrator = PipelineOrchestrator(
        repository,
        handlers_for(repository, injector, calls),
        stages=STAGES,
        max_stage_retries=0,
    )

    with pytest.raises(InjectedPipelineFailure, match=case.point.stage):
        orchestrator.run("run")

    checkpoints_after_failure = completed_units(repository)
    calls_after_failure = tuple(calls)
    assert (case.point.stage, case.point.unit_id) in checkpoints_after_failure

    resumed = orchestrator.run("run")

    assert resumed.run.state == "completed"
    assert len(calls) == len(set(calls))
    assert tuple(calls[: len(calls_after_failure)]) == calls_after_failure
    assert checkpoints_after_failure <= completed_units(repository)
    for stage, units in UNITS.items():
        for unit_id in units:
            assert (stage, unit_id) in completed_units(repository)
    for stage in STAGES:
        assert (stage, "stage") in completed_units(repository)


def test_precheckpoint_failure_retries_uncommitted_unit(tmp_path) -> None:
    repository = make_repository(tmp_path)
    point = FailurePoint("conversation", "turn-002", fail_after_checkpoint=False)
    injector = FailureInjector((point,))
    calls: list[tuple[str, str]] = []
    orchestrator = PipelineOrchestrator(
        repository,
        handlers_for(repository, injector, calls),
        stages=STAGES,
        max_stage_retries=0,
    )

    with pytest.raises(InjectedPipelineFailure, match="conversation"):
        orchestrator.run("run")

    assert ("conversation", "turn-001") in completed_units(repository)
    assert ("conversation", "turn-002") not in completed_units(repository)

    resumed = orchestrator.run("run")

    assert resumed.run.state == "completed"
    assert calls.count(("conversation", "turn-001")) == 1
    assert calls.count(("conversation", "turn-002")) == 1


def test_failure_injection_stage_helper_accepts_any_ordered_unit_sequence(tmp_path) -> None:
    repository = make_repository(tmp_path)
    context = PipelineContext("run", "episode", "conversation")
    calls: list[str] = []

    run_checkpointed_units(
        context,
        repository,
        ["turn-010", "turn-011"],
        calls.append,
    )
    run_checkpointed_units(
        context,
        repository,
        ["turn-010", "turn-011", "turn-012"],
        calls.append,
    )

    assert calls == ["turn-010", "turn-011", "turn-012"]
