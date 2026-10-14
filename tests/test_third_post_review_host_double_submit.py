"""TPR-07: host actions are single-shot and inert while a confirmation is open."""

from __future__ import annotations

import asyncio
from pathlib import Path

from test_third_post_review_host_discard_scope import _run
from textual.pilot import Pilot
from textual.widgets import Button, Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard


async def _repeated_create_makes_one_host(
    wizard: GuidedEpisodeWizard, pilot: Pilot, service: DeeperDiveService, project_id: str
) -> None:
    repository = service.hosts(project_id)
    before = len(repository.list_hosts(project_id))

    assert wizard.action_create_host() is True
    assert wizard.action_create_host() is False  # repeated Enter/click, same form
    await pilot.pause()

    assert len(repository.list_hosts(project_id)) == before + 1


async def _actions_inert_under_open_prompt(
    wizard: GuidedEpisodeWizard, pilot: Pilot, service: DeeperDiveService, project_id: str
) -> None:
    repository = service.hosts(project_id)
    hosts_before = [host.id for host in repository.list_hosts(project_id)]
    wizard.query_one("#guided-host-instructions", Input).value = "Unsaved profile edit"
    wizard.query_one("#guided-host-picker", Select).value = "second"
    await pilot.pause()
    assert wizard._exit_confirmation_pending
    order_before = list(wizard._selected_host_ids)

    wizard.action_select_host()
    wizard.action_remove_selected_host()
    wizard._move_selected_host(1)
    assert wizard.action_save_host() is False
    assert wizard.action_save_host_order() is False
    assert wizard.action_create_host() is False
    wizard.action_create_recommended_hosts()
    await pilot.pause()

    assert wizard._selected_host_ids == order_before
    assert [host.id for host in repository.list_hosts(project_id)] == hosts_before
    mutating = [b for b in wizard.query(Button) if b.name in wizard._MUTATING_HOST_BUTTONS]
    assert mutating and all(button.disabled for button in mutating)

    wizard.action_cancel_exit_confirmation()
    await pilot.pause()
    assert not any(button.disabled for button in mutating)
    wizard._move_selected_host(1)
    assert wizard._selected_host_ids != order_before


def test_repeated_create_host_creates_exactly_one(tmp_path: Path) -> None:
    asyncio.run(_run(tmp_path, _repeated_create_makes_one_host, with_episode=True))


def test_mutating_actions_are_inert_under_an_open_prompt_and_resume_after_cancel(
    tmp_path: Path,
) -> None:
    asyncio.run(_run(tmp_path, _actions_inert_under_open_prompt, with_episode=True))
