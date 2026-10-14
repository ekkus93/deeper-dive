"""TPR-17: every declared form field resolves to a real Input/Select on its wizard."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_shell import _FORM_FIELDS


def _ids(kind: WizardKind) -> list[tuple[str, str]]:
    return [(step, key) for (k, step), keys in _FORM_FIELDS.items() if k == kind for key in keys]


def test_every_declared_form_field_resolves_on_its_wizard(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        first_run = app.screen
        assert isinstance(first_run, GuidedFirstRunWizard)
        for step, key in _ids(WizardKind.FIRST_RUN):
            widget = first_run.query_one(f"#{key}")
            assert isinstance(widget, (Input, Select)), (step, key)

        app.action_navigate("new")
        await pilot.pause()
        new_wizard = app.screen
        assert new_wizard.context.state.kind == WizardKind.NEW_DEEP_DIVE
        for step, key in _ids(WizardKind.NEW_DEEP_DIVE):
            widget = new_wizard.query_one(f"#{key}")
            assert isinstance(widget, (Input, Select)), (step, key)


def test_strict_mode_raises_for_an_unresolvable_field(tmp_path: Path) -> None:
    asyncio.run(_strict(tmp_path))


async def _strict(tmp_path: Path) -> None:
    from textual.css.query import NoMatches

    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.strict_form_fields = True
        # The welcome step declares no fields, so strict mode is silent there.
        wizard._editable_snapshot()
        # An undeclared-widget lookup for a real declared step still resolves.
        wizard._editable_snapshot("provider-config")
        _FORM_FIELDS[(WizardKind.FIRST_RUN, "provider-config")] = (
            *_FORM_FIELDS[(WizardKind.FIRST_RUN, "provider-config")],
            "does-not-exist",
        )
        try:
            with pytest.raises(NoMatches):
                wizard._editable_snapshot("provider-config")
        finally:
            _FORM_FIELDS[(WizardKind.FIRST_RUN, "provider-config")] = _FORM_FIELDS[
                (WizardKind.FIRST_RUN, "provider-config")
            ][:-1]
