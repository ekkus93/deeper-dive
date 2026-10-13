"""SPR-07: guided TUI preserves frozen episode and generated artifact identity."""

from __future__ import annotations

import asyncio
from hashlib import sha256

from textual.widgets import Input, Static

from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.episode_repositories import HostEpisodeRepository


def test_completed_episode_tui_edit_requires_new_episode_without_artifact_loss(
    second_post_review_acceptance,
) -> None:
    asyncio.run(_exercise_completed_episode_tui_edit(second_post_review_acceptance()))


async def _exercise_completed_episode_tui_edit(fixture) -> None:
    item = fixture.completed.first
    service = item.service
    app = GuidedDeeperDiveApp(service)
    repository = HostEpisodeRepository(app.composition.database_for_project(item.project_id))
    episode_service = EpisodeConfigurationService(
        app.composition.database_for_project(item.project_id)
    )
    before = repository.get_episode(item.episode_id)
    plan = repository.get_plan(item.episode_id)
    run = service.runs(item.project_id).get(item.run_id)
    assert before is not None and plan is not None and run is not None
    audio_digest = sha256(item.audio_path.read_bytes()).hexdigest()
    transcript_digest = sha256(item.transcript_path.read_bytes()).hexdigest()
    config = episode_service.load_configuration(item.episode_id)

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = item.project_id
        wizard.context.episode_id = item.episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "episode")
        wizard._load_episode_host_order()
        wizard._load_episode_form()
        wizard._toggle()
        wizard._remember_current_form()

        focus = wizard.query_one("#guided-episode-focus", Input)
        attempted = "New question requires a new episode"
        focus.value = attempted
        assert wizard._current_form_dirty()
        assert not wizard.action_save_episode()
        assert wizard.context.state.current_step == "episode"
        assert focus.value == attempted
        message = str(wizard.query_one("#guided-episode-validation", Static).render())
        assert "create a new episode" in message
        assert wizard._current_form_dirty()
        assert repository.get_episode(item.episode_id) == before
        assert repository.get_plan(item.episode_id) == plan

        # Failed save cannot evade the common dirty-navigation confirmation.
        assert not wizard.action_back()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_cancel_exit_confirmation()
        assert focus.value == attempted
        assert wizard.context.state.current_step == "episode"

        wizard.action_back()
        wizard.action_confirm_discard_exit()
        await pilot.pause()
        assert wizard.context.state.current_step == "hosts"
        assert episode_service.load_configuration(item.episode_id) == config

    assert repository.get_episode(item.episode_id) == before
    assert repository.get_plan(item.episode_id) == plan
    assert service.runs(item.project_id).get(item.run_id) == run
    assert sha256(item.audio_path.read_bytes()).hexdigest() == audio_digest
    assert sha256(item.transcript_path.read_bytes()).hexdigest() == transcript_digest
