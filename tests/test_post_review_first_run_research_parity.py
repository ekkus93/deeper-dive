"""First-run research defaults flow through the real New and Quick episode paths."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Button, Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_source_wizard import GuidedSourceWizard
from deeper_dive.research_policy import ResearchPolicyStore
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize("research_mode", ["off", "useful", "aggressive"])
def test_first_run_research_default_reaches_new_and_quick(
    tmp_path: Path, research_mode: str
) -> None:
    asyncio.run(_check_first_run_research_paths(tmp_path, research_mode))


async def _check_first_run_research_paths(tmp_path: Path, research_mode: str) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        setup = app.screen
        assert isinstance(setup, GuidedFirstRunWizard)
        setup.action_continue()
        setup.action_continue()
        setup.query_one("#setup-ai-choice", Select).value = "manual"
        await pilot.pause()
        setup.action_continue()
        setup.query_one("#setup-provider-name", Input).value = "fixture"
        setup.query_one("#setup-provider-adapter", Input).value = "fake"
        setup.query_one("#setup-provider-model", Input).value = "fake-v1"
        setup.query_one("#setup-provider-network", Input).value = "local"
        setup.query_one("#setup-save-provider", Button).press()
        await pilot.pause()
        setup.query_one("#setup-test-provider", Button).press()
        await pilot.pause()
        setup.action_continue()
        setup.query_one("#setup-run-model-test", Button).press()
        await pilot.pause()
        setup.query_one("#setup-recommended-roles", Button).press()
        await pilot.pause()
        setup.action_continue()
        setup.query_one("#setup-speech-choice", Select).value = "deferred"
        await pilot.pause()
        setup.query_one("#setup-save-speech", Button).press()
        await pilot.pause()
        setup.action_continue()
        setup.query_one("#setup-research-default", Select).value = research_mode
        await pilot.pause()
        setup.query_one("#setup-save-defaults", Button).press()
        await pilot.pause()
        assert app.provider_controller.config().defaults["research_policy"] == research_mode
        setup.action_continue()
        assert setup.context.state.current_step == "ready"
        setup.action_ready_new()
        await pilot.pause()

        wizard = app.screen
        assert isinstance(wizard, GuidedSourceWizard)
        wizard.query_one("#guided-project-name", Input).value = "Research parity"
        wizard.query_one("#guided-project-topic", Input).value = "Research default"
        wizard.action_create_project()
        project_id = wizard.context.project_id
        assert project_id is not None
        wizard.action_continue()
        wizard.query_one("#guided-source-title", Input).value = "Evidence"
        wizard.query_one("#guided-source-text", Input).value = "Indexed research corpus."
        wizard.action_add_pasted_source()
        wizard.action_continue()
        assert wizard.context.state.current_step == "research"
        policy_store = ResearchPolicyStore(app.composition.database_for_project(project_id))
        assert not policy_store.has_project_policy(project_id)
        assert wizard.query_one("#guided-research-policy", Select).value == research_mode

        # Quick Deep Dive must create a normal durable episode with the same
        # global default when no project or user Quick override exists.
        quick_episode = service.quick_deep_dive(project_id)
        assert policy_store.episode(project_id, quick_episode.id).mode.value == research_mode
