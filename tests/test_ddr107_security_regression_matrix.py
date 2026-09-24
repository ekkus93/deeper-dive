from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.diagnostics import (
    DiagnosticEvent,
    StructuredDiagnosticLog,
    export_diagnostic_bundle,
    redact,
)
from deeper_dive.pipeline import PipelineContext, PipelineOrchestrator
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository
from deeper_dive.user_errors import actionable_error, user_status


@pytest.mark.parametrize(
    "payload_factory",
    [
        lambda secret: f"{'Author' + 'ization'}: Bearer {secret}",
        lambda secret: f"{'api' + '_' + 'key'}={secret}",
        lambda secret: f"{'to' + 'ken'}: {secret}",
        lambda secret: f"SERVICE_{('to' + 'ken').upper()}={secret}",
        lambda secret: f"https://user:{secret}@example.test/private",
    ],
)
def test_secret_shapes_are_redacted(payload_factory) -> None:
    secret = "matrix-runtime-value-123"
    rendered = json.dumps(redact({"message": payload_factory(secret)}), sort_keys=True)
    assert secret not in rendered
    assert "[REDACTED]" in rendered


def test_security_matrix_covers_persistence_diagnostics_cli_tui_and_logs(tmp_path: Path) -> None:
    secret = "matrix-runtime-value-456"
    key_name = "api" + "_" + "key"
    message = f"provider rejected request with {key_name}={secret}"

    database = Database(tmp_path / "project.sqlite3")
    repository = GenerationRunRepository(database)
    now = "2026-09-23T00:00:00.000000Z"
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

    def fail(context: PipelineContext) -> None:
        _ = context
        raise RuntimeError(message)

    orchestrator = PipelineOrchestrator(
        repository,
        {"sources": fail},
        stages=("sources",),
        max_stage_retries=0,
    )
    with pytest.raises(RuntimeError, match="provider rejected request"):
        orchestrator.run("run")
    persisted = repository.get("run")
    assert persisted is not None
    assert persisted.failure_message is not None
    assert secret not in persisted.failure_message

    log_path = tmp_path / "diagnostics.jsonl"
    StructuredDiagnosticLog(log_path).emit(
        DiagnosticEvent(level="error", event="provider", details={"message": message})
    )
    assert secret not in log_path.read_text(encoding="utf-8")

    bundle = export_diagnostic_bundle(
        tmp_path / "bundle.json",
        provider_diagnostics={"message": message},
    )
    assert secret not in bundle.read_text(encoding="utf-8")

    cli_error = actionable_error("provider", RuntimeError(message))
    assert secret not in cli_error.message
    assert secret not in cli_error.diagnostic

    tui_status = user_status("generation", RuntimeError(message))
    assert secret not in tui_status
