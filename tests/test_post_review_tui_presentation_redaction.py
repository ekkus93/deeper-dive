"""Regression coverage for runtime-derived advanced TUI presentation boundaries."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.providers_screen import ProvidersScreen
from deeper_dive.research_screen import ResearchScreen
from deeper_dive.settings_screen import SettingsController
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp


def test_advanced_screen_presentation_redacts_provider_runtime_canaries(tmp_path: Path) -> None:
    asyncio.run(_check_advanced_screen_presentation(tmp_path))


async def _check_advanced_screen_presentation(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Security presentation fixture")
    app = DeeperDiveApp(service)
    with (
        patch.object(
            SettingsController,
            "summary",
            return_value=("Authorization: Token settings-summary-secret",),
        ),
        patch.object(
            SettingsController,
            "readiness_summary",
            return_value=("authorization=Basic settings-readiness-secret",),
        ),
        patch.object(
            ProvidersScreen,
            "_list_text",
            return_value="Authorization: Token provider-list-secret",
        ),
        patch.object(
            ProvidersScreen,
            "_details_text",
            return_value="Authorization: Basic provider-details-secret",
        ),
        patch.object(
            ResearchScreen,
            "_candidate_text",
            return_value="authorization=Digest response=research-candidate-secret; status=401",
        ),
    ):
        async with app.run_test(size=(100, 30)) as pilot:
            app.action_navigate("settings")
            await pilot.pause()
            assert "settings-summary-secret" not in str(
                app.screen.query_one("#settings-summary", Static).render()
            )
            assert "settings-readiness-secret" not in str(
                app.screen.query_one("#readiness-status", Static).render()
            )

            app.action_navigate("providers")
            await pilot.pause()
            for selector, secret in (
                ("#llm-provider-list", "provider-list-secret"),
                ("#tts-provider-list", "provider-list-secret"),
                ("#provider-details", "provider-details-secret"),
            ):
                shown = str(app.screen.query_one(selector, Static).render())
                assert secret not in shown
                assert "[REDACTED]" in shown

            app.current_project_id = project.id
            app.current_project_name = project.name
            app.action_navigate("research")
            await pilot.pause()
            shown = str(app.screen.query_one("#research-candidates", Static).render())
            assert "research-candidate-secret" not in shown
            assert "[REDACTED]" in shown
