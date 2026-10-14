"""Cross-surface credential fragment matrix for supported URL encodings."""

from __future__ import annotations

import asyncio
import json

import pytest
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.command import main as command_main
from deeper_dive.diagnostics import (
    DiagnosticEvent,
    StructuredDiagnosticLog,
    export_diagnostic_bundle,
    redact,
    sanitize_exception_message,
)
from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import ProviderConfig, UserConfigStore


@pytest.mark.parametrize(
    "fragment",
    [
        "safe=1;api%5Fkey=fragment-matrix-canary",
        "safe%3D1%26access_token%3Dfragment-matrix-canary",
        "client.secret=fragment-matrix-canary",
        "session%54oken=fragment-matrix-canary",
        "%2561pi_key%3Dfragment-matrix-canary",
    ],
)
def test_fragment_canary_is_rejected_and_redacted_across_surfaces(tmp_path, fragment: str) -> None:
    endpoint = f"https://example.test/v1#{fragment}"
    with pytest.raises(ValueError, match="fragments") as rejected:
        ProviderConfig(provider_type="openai", base_url=endpoint)
    assert "fragment-matrix-canary" not in str(rejected.value)

    safe = str(redact(f"GET {endpoint} status=401"))
    assert "fragment-matrix-canary" not in safe
    assert "status=401" in safe
    assert "#[REDACTED]" in safe
    assert "fragment-matrix-canary" not in sanitize_exception_message(
        RuntimeError(f"provider failed: {endpoint}")
    )

    log = tmp_path / "diagnostics.jsonl"
    StructuredDiagnosticLog(log).emit(
        DiagnosticEvent(level="error", event="provider_error", details={"url": endpoint})
    )
    assert b"fragment-matrix-canary" not in log.read_bytes()
    bundle = export_diagnostic_bundle(
        tmp_path / "diagnostics.json", provider_diagnostics={"url": endpoint}
    )
    assert b"fragment-matrix-canary" not in bundle.read_bytes()


def test_fragment_canary_is_not_rendered_by_provider_screen(tmp_path) -> None:
    asyncio.run(_fragment_canary_is_not_rendered_by_provider_screen(tmp_path))


async def _fragment_canary_is_not_rendered_by_provider_screen(tmp_path) -> None:
    canary = "provider-screen-fragment-canary"
    controller = ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ={}),
    )
    app = DeeperDiveApp(
        DeeperDiveService(WorkspaceManager(tmp_path / "data")),
        provider_controller=controller,
    )
    async with app.run_test(size=(110, 34)) as pilot:
        app.action_navigate("providers")
        await pilot.pause()
        screen = app.screen
        screen.query_one("#provider-name", Input).value = "remote"
        screen.query_one("#provider-type", Input).value = "openai"
        screen.query_one(
            "#provider-base-url", Input
        ).value = f"https://example.test/v1#api%5Fkey={canary}"
        screen.action_save()
        status = str(screen.query_one("#screen-status", Static).render())
        assert "base_url" in status or "fragment" in status
        assert canary not in status
        assert "remote" not in controller.config().providers
        config_path = controller.config_store.path
        assert not config_path.exists() or canary.encode() not in config_path.read_bytes()


def test_invalid_fragment_canary_is_not_echoed_by_cli_bootstrap(tmp_path, capsys) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    canary = "provider-cli-fragment-canary"
    (data_dir / "config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": {
                    "remote": {
                        "provider_type": "openai",
                        "base_url": f"https://example.test/v1#api%5Fkey={canary}",
                    }
                },
                "defaults": {},
            }
        ),
        encoding="utf-8",
    )

    result = command_main(["--data-dir", str(data_dir), "--json", "provider", "list"])

    captured = capsys.readouterr()
    assert result != 0
    assert "Provider request failed." in captured.err
    assert canary not in captured.out
    assert canary not in captured.err
