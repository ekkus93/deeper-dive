"""Guided research policy precedence and durable selector hydration."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_source_wizard import GuidedSourceWizard
from deeper_dive.research_policy import ResearchPolicyStore
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import UserConfig, UserConfigStore


@pytest.mark.parametrize("global_mode", ["off", "useful", "aggressive"])
def test_guided_research_hydrates_global_then_durable_project_policy(
    tmp_path: Path, global_mode: str
) -> None:
    asyncio.run(_check_research_hydration(tmp_path, global_mode))


async def _check_research_hydration(tmp_path: Path, global_mode: str) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    UserConfigStore(service.workspaces.data_dir / "config.json").save(
        UserConfig(defaults={"research_policy": global_mode})
    )
    app = GuidedDeeperDiveApp(service)
    project_id: str
    selected = "off" if global_mode == "aggressive" else "aggressive"
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedSourceWizard)
        screen.query_one("#guided-project-name", Input).value = "Research policy"
        screen.query_one("#guided-project-topic", Input).value = "Which policy?"
        screen.action_create_project()
        project_id = screen.context.project_id or ""
        assert project_id
        screen.action_continue()
        screen.query_one("#guided-source-title", Input).value = "Corpus"
        screen.query_one("#guided-source-text", Input).value = "Indexed evidence."
        screen.action_add_pasted_source()
        screen.action_continue()
        assert screen.context.state.current_step == "research"
        policy_store = ResearchPolicyStore(app.composition.database_for_project(project_id))
        assert not policy_store.has_project_policy(project_id)
        assert screen.query_one("#guided-research-policy", Select).value == global_mode

        screen.query_one("#guided-research-policy", Select).value = selected
        await pilot.pause()
        screen.action_save_research()
        assert policy_store.project(project_id).mode.value == selected
        screen.action_back()
        screen.action_continue()
        assert screen.context.state.current_step == "research"
        assert screen.query_one("#guided-research-policy", Select).value == selected
        screen.action_save_exit()
        await pilot.pause()

    restarted = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with restarted.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        restarted.action_navigate("resume")
        await pilot.pause()
        screen = restarted.screen
        assert isinstance(screen, GuidedSourceWizard)
        assert screen.context.project_id == project_id
        assert screen.context.state.current_step == "research"
        assert screen.query_one("#guided-research-policy", Select).value == selected
        policy_store = ResearchPolicyStore(
            restarted.composition.database_for_project(project_id)
        )
        assert policy_store.project(project_id).mode.value == selected
