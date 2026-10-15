"""FPR-04: fail-closed discard never raises, on any step, including non-blank Selects."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_transitions import _FORM_FIELDS

CASES = sorted(_FORM_FIELDS, key=lambda key: (key[0].name, key[1]))


@pytest.mark.parametrize("kind,step", CASES, ids=[f"{k.name}-{s}" for k, s in CASES])
def test_discard_without_baseline_never_raises_and_retains_no_input(
    tmp_path: Path, kind: WizardKind, step: str
) -> None:
    asyncio.run(_exercise(tmp_path, kind, step))


async def _exercise(tmp_path: Path, kind: WizardKind, step: str) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        if kind is WizardKind.NEW_DEEP_DIVE:
            app._first_run_readiness.close()
            app.action_navigate("new")
            await pilot.pause()
        wizard = app.screen
        # A missing baseline is a race (a step left before its scheduled baseline
        # ran), so the state is set directly: no UI path holds it still.
        wizard.context.state = WizardState(kind, step)
        keys = _FORM_FIELDS[(kind, step)]
        inputs = []
        for key in keys:
            widget = wizard.query_one(f"#{key}")
            if isinstance(widget, Input):
                widget.value = "CANARY-UNSAVED"
                inputs.append(widget)
        wizard._form_baselines.pop(step, None)
        wizard._form_baseline_targets.pop(step, None)

        wizard._restore_discarded_form()  # must not raise

        assert all(widget.value == "" for widget in inputs)
        assert wizard._discard_baseline_missing
        for key in keys:
            widget = wizard.query_one(f"#{key}")
            if isinstance(widget, Select):
                assert widget.value is not None


def test_discard_without_baseline_tells_the_user_and_a_later_save_is_not_unasked(
    tmp_path: Path,
) -> None:
    """5PR-11: the status is user-visible, and the cleared form is not silently saved."""

    from guided_pilot import click, type_into, wait_until

    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)) as pilot:
            app._first_run_readiness.close()
            app.action_navigate("new")
            await pilot.pause()
            wizard = app.screen
            await type_into(pilot, "#guided-project-name", "CANARY-UNSAVED")
            # Seeded: a missing baseline is a race no UI path holds still.
            wizard._form_baselines.pop("project", None)
            wizard._form_baseline_targets.pop("project", None)
            await pilot.press("escape")
            await wait_until(pilot, lambda: wizard._exit_confirmation_pending)
            await click(pilot, "#wizard-confirm-discard")
            status = str(wizard.query_one("#wizard-status").render())
            assert "unsaved input was cleared" in status, status
            assert wizard.query_one("#guided-project-name", Input).value == ""
            # Nothing was created by discarding.
            assert wizard.context.project_id is None

    asyncio.run(run())
