from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from deeper_dive.pipeline import PipelineOrchestrator
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository


def _run() -> GenerationRunRecord:
    return GenerationRunRecord(
        id="run-security",
        episode_id="episode-security",
        stage="danger",
        state="pending",
        created_at="2026-09-23T00:00:00Z",
        modified_at="2026-09-23T00:00:00Z",
    )


def test_repository_redacts_secret_material_on_create_and_update(tmp_path: Path) -> None:
    secret = "persisted-runtime-value"
    auth = "Author" + "ization"
    api_key = "API" + "_KEY"
    token = "TO" + "KEN"
    repository = GenerationRunRepository(Database(tmp_path / "project.db"))
    run = _run()
    repository.create(
        replace(
            run,
            state="failed",
            failure_message=f"{auth}: Bearer {secret}; {api_key}={secret}",
        )
    )

    persisted = repository.get(run.id)
    assert persisted is not None
    assert persisted.failure_message is not None
    assert secret not in persisted.failure_message
    assert "[REDACTED]" in persisted.failure_message

    repository.update(
        replace(
            persisted,
            failure_message=f"{token}={secret}; https://user:{secret}@example.test/v1",
        )
    )
    persisted = repository.get(run.id)
    assert persisted is not None
    assert persisted.failure_message is not None
    assert secret not in persisted.failure_message
    assert "https://[REDACTED]@example.test/v1" in persisted.failure_message


def test_pipeline_failure_persists_only_sanitized_exception_and_chained_context(
    tmp_path: Path,
) -> None:
    secret = "pipeline-runtime-value"
    auth = "Author" + "ization"
    api_key = "API" + "_KEY"
    repository = GenerationRunRepository(Database(tmp_path / "project.db"))
    repository.create(_run())

    def fail(_context: object) -> None:
        try:
            raise RuntimeError(f"{api_key}={secret}")
        except RuntimeError as cause:
            raise ValueError(f"provider failed with {auth}: Bearer {secret}") from cause

    pipeline = PipelineOrchestrator(
        repository,
        {"danger": fail},
        stages=("danger",),
        max_stage_retries=0,
    )

    with pytest.raises(ValueError):
        pipeline.run("run-security")

    persisted = repository.get("run-security")
    assert persisted is not None
    assert persisted.state == "failed"
    assert persisted.failure_code == "stage_failed"
    assert persisted.failure_message is not None
    assert secret not in persisted.failure_message
    assert "[REDACTED]" in persisted.failure_message
    assert "provider failed" in persisted.failure_message
    assert "caused by" in persisted.failure_message
