"""Guided research hydration must preserve pending selections."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.research_policy import ResearchMode, ResearchPolicy, ResearchPolicyStore
from deeper_dive.storage.workspace import WorkspaceManager


def test_dirty_research_selection_survives_refresh_and_clean_refresh_rehydrates(
    tmp_path: Path,
) -> None:
    asyncio.run(_verify_research_refresh(tmp_path))


async def _verify_research_refresh(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Research refresh")
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "research")
        wizard._refresh_research_choice()
        wizard._toggle()
        wizard._remember_current_form()
        picker = wizard.query_one("#guided-research-policy", Select)
        assert picker.value == "useful"

        picker.value = "off"
        assert wizard._current_form_dirty()
        wizard._refresh_research_choice()
        assert picker.value == "off"
        assert wizard._current_form_dirty()

        assert wizard.action_save_research()
        assert not wizard._current_form_dirty()
        store = ResearchPolicyStore(wizard.context.composition.database_for_project(project.id))
        assert store.project(project.id).mode == ResearchMode.OFF

        wizard.context.composition.research_controller.save_policy(
            project.id, ResearchPolicy(mode=ResearchMode.AGGRESSIVE), ""
        )
        wizard._refresh_research_choice()
        assert picker.value == "aggressive"
        assert not wizard._current_form_dirty()
