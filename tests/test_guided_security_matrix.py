"""Guided wizard status and diagnostic output security matrix."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.diagnostics import (
    DiagnosticEvent,
    StructuredDiagnosticLog,
    export_diagnostic_bundle,
    sanitize_exception_message,
)
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


def test_guided_status_and_chained_errors_are_recursively_redacted(
    tmp_path: Path,
) -> None:
    asyncio.run(_guided_error_sanitization(tmp_path))


async def _guided_error_sanitization(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    canaries = ("CANARY_API_42", "CANARY_BEARER_19", "CANARY_URL_71")
    try:
        try:
            raise ValueError("api_key=CANARY_API_42")
        except ValueError as original:
            raise RuntimeError(
                "Authorization: Bearer CANARY_BEARER_19 "
                "https://user:CANARY_URL_71@example.invalid/path"
            ) from original
    except RuntimeError as error:
        message = sanitize_exception_message(error)

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.set_status(message)
        status = str(screen.query_one("#wizard-status", Static).render())
        assert all(canary not in status for canary in canaries)
        assert "[REDACTED]" in status


def test_diagnostics_and_support_bundle_reject_nested_credential_canaries(
    tmp_path: Path,
) -> None:
    canaries = ("CANARY_TOKEN_81", "CANARY_PASSWORD_82", "CANARY_API_83")
    details = {
        "providers": [
            {"access_token": canaries[0], "info": {"password": canaries[1]}},
            {"configuration": {"api_key": canaries[2]}, "status": "expected-failure"},
        ]
    }
    log = tmp_path / "logs" / "diagnostics.jsonl"
    StructuredDiagnosticLog(log).emit(
        DiagnosticEvent(
            level="error",
            event="provider_error",
            message="api_key=CANARY_API_83",
            details=details,
        )
    )
    exported = export_diagnostic_bundle(
        tmp_path / "exports" / "diagnostics.json",
        provider_diagnostics=details,
        configuration={"authorization": "Bearer CANARY_TOKEN_81"},
        source_excerpts={"private": "source text must require explicit opt-in"},
    )
    log_text = log.read_text(encoding="utf-8")
    payload_text = exported.read_text(encoding="utf-8")
    assert all(canary not in text for text in (log_text, payload_text) for canary in canaries)
    assert "[REDACTED]" in log_text and "[REDACTED]" in payload_text
    assert json.loads(payload_text)["source_excerpts_included"] is False
    assert "source text must require explicit opt-in" not in payload_text
