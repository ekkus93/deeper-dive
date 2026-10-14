"""TPR-17: Save/Discard refuse to act when the edited target drifted under an open prompt."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from test_third_post_review_host_discard_scope import _run
from textual.pilot import Pilot
from textual.widgets import Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard


async def _drift_scenario(
    wizard: GuidedEpisodeWizard,
    pilot: Pilot,
    service: DeeperDiveService,
    project_id: str,
    *,
    confirm: str,
) -> None:
    wizard.query_one("#guided-host-instructions", Input).value = "Unsaved profile edit"
    wizard.query_one("#guided-host-picker", Select).value = "second"
    await pilot.pause()
    assert wizard._exit_confirmation_pending
    assert wizard._pending_snapshot is not None

    # The edited target changes underneath the open prompt.
    wizard._loaded_host_id = "second"

    if confirm == "discard":
        wizard.action_confirm_discard_exit()
    else:
        wizard.action_confirm_save_exit()
    await pilot.pause()

    assert not wizard._exit_confirmation_pending
    assert wizard.query_one("#guided-host-instructions", Input).value == "Unsaved profile edit"
    status = str(wizard.query_one("#wizard-status", Static).render())
    assert "changed while the prompt was open" in status
    stored = service.hosts(project_id).get_host("first")
    assert stored is not None and stored.instructions != "Unsaved profile edit"


@pytest.mark.parametrize("confirm", ["discard", "save"])
def test_confirmation_refuses_when_the_target_drifted(tmp_path: Path, confirm: str) -> None:
    async def scenario(wizard, pilot, service, project_id):  # type: ignore[no-untyped-def]
        await _drift_scenario(wizard, pilot, service, project_id, confirm=confirm)

    asyncio.run(_run(tmp_path, scenario, with_episode=True))
