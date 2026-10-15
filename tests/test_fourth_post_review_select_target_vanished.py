"""FPR-05: executing a select transition after its target vanished must not crash."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import choose_option, click, reach_hosts, type_into
from textual.widgets import Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_transitions import Transition, TransitionKind


def test_save_then_select_when_the_other_host_was_deleted(tmp_path: Path) -> None:
    asyncio.run(_hosts(tmp_path))


async def _hosts(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 45)) as pilot:
        await reach_hosts(pilot)
        wizard = app.screen
        await click(pilot, "#guided-host-recommended")
        picker = wizard.query_one("#guided-host-picker", Select)
        first_host = picker.value
        assert isinstance(first_host, str)
        project_id = wizard.context.project_id
        assert project_id is not None
        others = [
            record.id
            for record in service.hosts(project_id).list_hosts(project_id)
            if record.id != first_host
        ]
        assert others

        await type_into(pilot, "#guided-host-name", "Saved Before Vanish")
        await choose_option(pilot, "#guided-host-picker", 1)
        assert wizard._exit_confirmation_pending
        # Another surface deletes every other host while the prompt is open.
        for host_id in others:
            service.hosts(project_id).delete_host(host_id)

        executed: list[object] = []
        original = type(wizard)._execute_custom_transition

        def counting(self, transition):  # type: ignore[no-untyped-def]
            executed.append(transition)
            return original(self, transition)

        type(wizard)._execute_custom_transition = counting  # type: ignore[method-assign]
        try:
            await click(pilot, "#wizard-confirm-save")  # must not crash
        finally:
            type(wizard)._execute_custom_transition = original  # type: ignore[method-assign]

        # 5PR-11: the pending transition ran exactly once and the user was told why the
        # picker did not move.
        assert len(executed) == 1, executed
        status = str(wizard.query_one("#wizard-status").render()).lower()
        assert "no longer available" in status, status

        assert app.is_running
        assert not wizard._exit_confirmation_pending
        record = service.hosts(project_id).get_host(first_host)
        assert record is not None and record.display_name == "Saved Before Vanish"


def test_plan_and_speech_selects_ignore_unavailable_targets(tmp_path: Path) -> None:
    asyncio.run(_deterministic(tmp_path))


async def _deterministic(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        first_run = app.screen
        # Speech choice that is not offered (service-side option lists can shrink).
        first_run._execute_custom_transition(Transition(TransitionKind.SPEECH_CHOICE, "nonesuch"))
        assert app.is_running
        # Direct calls below are deliberate: the target can only vanish in a race that
        # no UI path holds still. The status is asserted so the user is not left guessing.
        assert "no longer available" in str(first_run.query_one("#wizard-status").render()).lower()
        app._first_run_readiness.close()
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        wizard._execute_custom_transition(Transition(TransitionKind.PLAN_SELECT, "99"))
        assert app.is_running
        assert "no longer available" in str(wizard.query_one("#wizard-status").render()).lower()
        wizard._execute_custom_transition(Transition(TransitionKind.HOST_SELECT, "vanished-host"))
        assert app.is_running
        status = str(wizard.query_one("#wizard-status").render()).lower()
        assert "no longer available" in status
