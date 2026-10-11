"""An unrelated refresh cannot adopt dirty wizard controls as durable state."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from textual.widgets import Input

from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState


def test_scheduled_refresh_does_not_clear_dirty_episode_input(
    second_post_review_acceptance: Callable[[], Any],
) -> None:
    asyncio.run(_scheduled_refresh_does_not_clear_dirty_episode_input(second_post_review_acceptance))


async def _scheduled_refresh_does_not_clear_dirty_episode_input(
    second_post_review_acceptance: Callable[[], Any],
) -> None:
    fixture = second_post_review_acceptance()
    service = fixture.completed.first.service
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = fixture.pending_project_id
        wizard.context.episode_id = fixture.pending_episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "episode")
        wizard._load_episode_host_order()
        wizard._load_episode_form()
        wizard._toggle()
        wizard._remember_current_form()

        control = wizard.query_one("#guided-episode-title", Input)
        durable = control.value
        control.value = "Unsaved title must survive refresh"
        assert wizard._current_form_dirty()

        wizard._schedule_form_baseline()
        await pilot.pause()
        assert wizard._current_form_dirty()
        assert not wizard.action_back()
        assert control.value == "Unsaved title must survive refresh"
        wizard.action_cancel_exit_confirmation()

        # A second unrelated refresh must not clear the dirty state either.
        wizard._schedule_form_baseline()
        await pilot.pause()
        assert wizard._current_form_dirty()
        assert control.value != durable
