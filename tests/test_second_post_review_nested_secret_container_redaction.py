"""SPR-06: stringified nested authorization containers are support-safe."""

from __future__ import annotations

import json

import pytest

from deeper_dive.diagnostics import (
    DiagnosticEvent,
    StructuredDiagnosticLog,
    export_diagnostic_bundle,
    redact,
    sanitize_exception_message,
)


@pytest.mark.parametrize(
    ("key", "nested"),
    [
        ("Authorization", ["Basic nested-secret-canary"]),
        ("api_key", {"current": "nested-secret-canary"}),
        ("client.secret", [{"raw": {"key": "nested-secret-canary"}}]),
        ("refresh_token", ["prefix]nested-secret-canary", {"other": "safe"}]),
    ],
)
def test_stringified_sensitive_mapping_containers_are_redacted(key: str, nested: object) -> None:
    details = {"context": "keep-me", key: nested, "status": 401}
    raw = f"provider failed headers={details!r} retry=yes"
    safe = str(redact(raw))
    assert "nested-secret-canary" not in safe
    assert "[REDACTED]" in safe
    assert "keep-me" in safe
    assert "status" in safe
    assert "retry=yes" in safe


def test_stringified_nested_secret_list_in_chained_exception_log_and_bundle(tmp_path) -> None:
    details = {
        "public": ["benign"],
        "headers": {"Authorization": [{"credentials": ["Basic nested-secret-canary"]}]},
        "status": 401,
    }
    try:
        try:
            raise ValueError(f"remote provider returned {details!r}")
        except ValueError as original:
            raise RuntimeError("model generation failed") from original
    except RuntimeError as error:
        safe = sanitize_exception_message(error)
    assert "nested-secret-canary" not in safe
    assert "model generation failed" in safe
    assert "caused by:" in safe
    assert "status" in safe

    log_path = tmp_path / "diagnostics.jsonl"
    StructuredDiagnosticLog(log_path).emit(
        DiagnosticEvent(
            level="error",
            event="nested_header_error",
            details={"rendered_exception": repr(details)},
        )
    )
    bundle_path = export_diagnostic_bundle(
        tmp_path / "bundle.json",
        provider_diagnostics={"nested": [repr(details)]},
    )
    for path in (log_path, bundle_path):
        raw = path.read_text(encoding="utf-8")
        assert "nested-secret-canary" not in raw
        assert "benign" in raw
        assert "[REDACTED]" in raw
        assert json.loads(raw if path == bundle_path else raw.splitlines()[0])


def test_benign_nonsecret_nested_diagnostics_remain_readable() -> None:
    value = "headers={'Accept': ['application/json'], 'status': {'code': 200}}"
    assert redact(value) == value


def test_unterminated_sensitive_container_does_not_leak_trailing_credential() -> None:
    text = "headers={'Authorization': ['Basic nested-secret-canary'"
    safe = str(redact(text))
    assert "nested-secret-canary" not in safe
    assert "[REDACTED]" in safe


@pytest.mark.parametrize(
    "nested",
    [
        "('Basic tuple-secret-canary',)",
        "(('Basic tuple-secret-canary',), {'extra': 'safe'})",
        "('prefix)tuple-secret-canary', ['extra'])",
        "('Basic tuple-secret-canary'",
    ],
)
def test_stringified_secret_header_tuple_is_redacted(nested: str) -> None:
    raw = f"provider response headers={{'Authorization': {nested}, 'status': 401}} retry=yes"
    safe = str(redact(raw))
    assert "tuple-secret-canary" not in safe
    assert "[REDACTED]" in safe


def test_benign_tuple_mapping_does_not_lose_context() -> None:
    raw = "headers={'Accept': ('application/json',), 'status': 200}"
    assert redact(raw) == raw


def test_tuple_header_chained_cli_exception_and_diagnostic_bundle(
    tmp_path, capsys, monkeypatch
) -> None:
    from deeper_dive import cli as cli_module

    secret = "tuple-boundary-canary"
    header_repr = f"{{'Authorization': ('Basic {secret}',), 'status': 429}}"

    def reject_bootstrap(*args, **kwargs) -> None:
        try:
            raise ValueError(f"provider failed headers={header_repr}")
        except ValueError as cause:
            raise RuntimeError("unable to configure provider") from cause

    monkeypatch.setattr(cli_module.ProductionComposition, "build", reject_bootstrap)
    assert cli_module.main(["--data-dir", str(tmp_path), "project", "list"]) == 2
    cli = capsys.readouterr()
    assert cli.out == ""
    assert secret not in cli.err
    assert "unable to configure provider" in cli.err
    assert "status" in cli.err
    assert "Traceback" not in cli.err

    output = export_diagnostic_bundle(
        tmp_path / "bundle.json",
        provider_diagnostics={"error": f"provider failed headers={header_repr}"},
    )
    payload = output.read_text(encoding="utf-8")
    assert secret not in payload
    assert "status" in payload
    assert "[REDACTED]" in payload


def test_textual_provider_error_redacts_tuple_header(tmp_path) -> None:
    import asyncio

    from textual.widgets import Static

    from deeper_dive.application.service import DeeperDiveService
    from deeper_dive.guided_app import GuidedDeeperDiveApp
    from deeper_dive.guided_first_run import GuidedFirstRunWizard
    from deeper_dive.storage.workspace import WorkspaceManager

    async def exercise() -> None:
        service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
        app = GuidedDeeperDiveApp(service)
        async with app.run_test(size=(100, 35)) as pilot:
            app._first_run_readiness.close()
            wizard = app.screen
            assert isinstance(wizard, GuidedFirstRunWizard)
            secret = "textual-tuple-canary"
            cause = ValueError(f"headers={{'Authorization': ('Basic {secret}',), 'status': 403}}")
            error = RuntimeError("Provider setup failed")
            error.__cause__ = cause
            wizard.set_error("Provider setup failed.", error)
            await pilot.pause()
            rendered = str(wizard.query_one("#wizard-status", Static).render())
            assert secret not in rendered
            assert "Provider setup failed" in rendered
            wizard.action_help()
            details = str(wizard.query_one("#wizard-status", Static).render())
            assert secret not in details
            assert "[REDACTED]" in details
            assert secret not in (wizard._error_details or "")

    asyncio.run(exercise())



@pytest.mark.parametrize("scheme", ("Basic", "Token", "Digest", "Bearer"))
@pytest.mark.parametrize("separator", (":", "="))
def test_all_authorization_schemes_are_scrubbed_before_log_or_export(
    tmp_path, scheme: str, separator: str
) -> None:
    secret = "auth-scheme-canary"
    payload = (
        f'Authorization{separator} Digest username="{secret}", nonce="{secret}"; status=401'
        if scheme == "Digest"
        else f"Authorization{separator} {scheme} {secret}; status=401"
    )
    safe = str(redact(payload))
    assert secret not in safe
    assert "[REDACTED]" in safe
    assert "status=401" in safe

    log_path = tmp_path / "authorization.jsonl"
    StructuredDiagnosticLog(log_path).emit(
        DiagnosticEvent(level="error", event="authorization_failure", message=payload)
    )
    destination = export_diagnostic_bundle(
        tmp_path / "authorization.json",
        provider_diagnostics={"message": payload},
    )
    for path in (log_path, destination):
        text = path.read_text(encoding="utf-8")
        assert secret not in text
        assert "status=401" in text
        assert "[REDACTED]" in text
