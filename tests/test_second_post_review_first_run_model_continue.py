"""Regression for dirty first-run model-role Continue precedence."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize("synthetic_test_passed", [False, True])
def test_model_role_continue_guards_unsaved_input_before_test_prerequisite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_test_passed: bool,
) -> None:
    asyncio.run(
        _model_role_continue_guards_unsaved_input(tmp_path, monkeypatch, synthetic_test_passed)
    )


async def _model_role_continue_guards_unsaved_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_test_passed: bool,
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "model-test")
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()
        wizard._remember_current_form()

        identity = "fixture-provider:fixture-model"
        monkeypatch.setattr(wizard, "_current_llm_identity", lambda: identity)
        wizard._model_test_identity = identity if synthetic_test_passed else None

        field = wizard.query_one("#setup-role-episode-planning", Input)
        baseline = field.value
        changed = baseline + "-unsaved"
        field.value = changed
        assert wizard._current_form_dirty()

        # Even without a successful model test, the dirty transition must be
        # presented first rather than showing the prerequisite error.
        assert not wizard.action_continue()
        assert wizard.context.state.current_step == "model-test"
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert "Unsaved changes" in str(wizard.query_one("#wizard-status", Static).render())
        assert field.value == changed

        wizard.action_cancel_exit_confirmation()
        assert field.value == changed
        assert wizard._current_form_dirty()
        assert not wizard.query_one("#wizard-exit-confirmation").display

        assert not wizard.action_continue()
        assert wizard.query_one("#wizard-exit-confirmation").display
        if not synthetic_test_passed:
            wizard.action_confirm_discard_exit()
            assert field.value == baseline
            assert not wizard._current_form_dirty()
            assert wizard.context.state.current_step == "model-test"
            assert "Run the synthetic model test" in str(
                wizard.query_one("#wizard-status", Static).render()
            )
        else:
            wizard.action_cancel_exit_confirmation()


def test_clean_model_role_continue_still_requires_synthetic_test(tmp_path: Path) -> None:
    asyncio.run(_clean_model_role_continue_still_requires_synthetic_test(tmp_path))


async def _clean_model_role_continue_still_requires_synthetic_test(
    tmp_path: Path,
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "model-test")
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()
        wizard._remember_current_form()

        assert not wizard._current_form_dirty()
        assert not wizard.action_continue()
        assert wizard.context.state.current_step == "model-test"
        assert not wizard.query_one("#wizard-exit-confirmation").display
        assert "Run the synthetic model test" in str(
            wizard.query_one("#wizard-status", Static).render()
        )
