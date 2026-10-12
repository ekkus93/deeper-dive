"""Textual acceptance for immutable historical episode configuration."""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.episode_repositories import EpisodePlanRecord, HostEpisodeRepository
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize("state", ["planned", "running", "paused", "failed", "completed"])
def test_guided_edit_of_frozen_episode_is_actionable_and_preserves_history(
    tmp_path, state: str
) -> None:
    asyncio.run(_assert_guided_frozen_episode(tmp_path, state))


async def _assert_guided_frozen_episode(tmp_path, state: str) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Historical episode")
    app = GuidedDeeperDiveApp(service)
    database = app.composition.database_for_project(project.id)
    configurations = EpisodeConfigurationService(database)
    episode = configurations.create(
        project.id,
        EpisodeConfiguration(title="Historical title", focus="Historical focus"),
    )
    repository = HostEpisodeRepository(database)
    repository.save_plan(
        EpisodePlanRecord(
            id="historical-plan",
            episode_id=episode.id,
            created_at="now",
            modified_at="now",
        ),
        [],
    )
    with database.transaction(immediate=True) as connection:
        connection.execute("UPDATE episodes SET state=? WHERE id=?", (state, episode.id))
    original = repository.get_episode(episode.id)
    original_plan = repository.get_plan(episode.id)
    assert original is not None and original_plan is not None

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.episode_id = episode.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "episode")
        wizard._load_episode_form()
        wizard._toggle()
        wizard._remember_current_form()

        title = wizard.query_one("#guided-episode-title", Input)
        title.value = "Unsaved revision"
        assert not wizard.action_save_episode()
        assert title.value == "Unsaved revision"
        validation = str(wizard.query_one("#guided-episode-validation", Static).render())
        assert "create a new episode" in validation
        assert "frozen after generation starts" in validation

        assert repository.get_episode(episode.id) == original
        assert repository.get_plan(episode.id) == original_plan
        assert configurations.load_configuration(episode.id).title == "Historical title"

        assert not wizard.action_back()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_cancel_exit_confirmation()
        assert title.value == "Unsaved revision"
