from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App
from textual.widgets import Button, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.composition import ProductionComposition
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_shell import (
    FirstRunWizardShell,
    NewDeepDiveWizardShell,
    WizardShell,
)


def _composition(tmp_path: Path) -> ProductionComposition:
    return ProductionComposition.build(
        service=DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    )


class _WizardHarness(App[None]):
    def __init__(self, screen: FirstRunWizardShell | NewDeepDiveWizardShell) -> None:
        super().__init__()
        self.screen_to_test = screen

    def on_mount(self) -> None:
        self.push_screen(self.screen_to_test)


def test_both_workflows_use_the_same_wizard_shell_contract(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    first = FirstRunWizardShell(
        WizardContext(composition, WizardState(WizardKind.FIRST_RUN, "welcome")),
        lambda _key: True,
    )
    new = NewDeepDiveWizardShell(
        WizardContext(composition, WizardState(WizardKind.NEW_DEEP_DIVE, "project")),
        lambda _key: True,
    )

    assert isinstance(first, WizardShell)
    assert isinstance(new, WizardShell)
    assert first.context.composition is composition
    assert new.context.composition is composition


def test_wizard_shell_keyboard_navigation_focus_and_progress(tmp_path: Path) -> None:
    asyncio.run(_wizard_shell_keyboard_navigation_focus_and_progress(tmp_path))


async def _wizard_shell_keyboard_navigation_focus_and_progress(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    complete = {"project": True, "sources": False}
    screen = NewDeepDiveWizardShell(
        WizardContext(composition, WizardState(WizardKind.NEW_DEEP_DIVE, "project")),
        lambda key: complete.get(key, False),
    )
    app = _WizardHarness(screen)

    async with app.run_test(size=(100, 30)) as pilot:
        assert "Step 1 of 7" in str(screen.query_one("#wizard-heading", Static).render())
        assert "▶ Project Setup (current)" in str(
            screen.query_one("#wizard-progress", Static).render()
        )
        continue_button = screen.query_one("#wizard-continue", Button)
        assert continue_button.disabled is False

        await pilot.press("tab")
        assert screen.focused is continue_button
        await pilot.press("enter")
        await pilot.pause()

        assert screen.context.state.current_step == "sources"
        assert continue_button.disabled is True
        assert "Step 2 of 7" in str(screen.query_one("#wizard-heading", Static).render())
        assert "✓ Project Setup (complete)" in str(
            screen.query_one("#wizard-progress", Static).render()
        )

        await pilot.press("tab")
        assert screen.focused is screen.query_one("#wizard-save-exit", Button)
        await pilot.press("shift+tab")
        assert screen.focused is screen.query_one("#wizard-back", Button)


def test_wizard_shell_busy_state_blocks_duplicate_actions(tmp_path: Path) -> None:
    asyncio.run(_wizard_shell_busy_state_blocks_duplicate_actions(tmp_path))


async def _wizard_shell_busy_state_blocks_duplicate_actions(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    screen = NewDeepDiveWizardShell(
        WizardContext(composition, WizardState(WizardKind.NEW_DEEP_DIVE, "project")),
        lambda _key: True,
    )
    app = _WizardHarness(screen)

    async with app.run_test(size=(100, 30)):
        screen.set_busy(True, "Working")
        assert screen.query_one("#wizard-continue", Button).disabled is True
        assert screen.query_one("#wizard-save-exit", Button).disabled is True
        screen.action_continue()
        assert screen.context.state.current_step == "project"
        screen.set_busy(False)
        screen.action_continue()
        assert screen.context.state.current_step == "sources"


def test_wizard_shell_compact_and_below_minimum_layout(tmp_path: Path) -> None:
    asyncio.run(_wizard_shell_compact_and_below_minimum_layout(tmp_path))


async def _wizard_shell_compact_and_below_minimum_layout(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    compact = FirstRunWizardShell(
        WizardContext(composition, WizardState(WizardKind.FIRST_RUN, "welcome")),
        lambda _key: True,
    )
    compact_app = _WizardHarness(compact)
    async with compact_app.run_test(size=(80, 24)):
        assert compact.query_one("#wizard-content").display is True
        assert compact.query_one("#wizard-actions").display is True
        assert compact.query_one("#wizard-resize-message").display is False

    tiny = FirstRunWizardShell(
        WizardContext(composition, WizardState(WizardKind.FIRST_RUN, "welcome")),
        lambda _key: True,
    )
    tiny_app = _WizardHarness(tiny)
    async with tiny_app.run_test(size=(79, 23)):
        warning = tiny.query_one("#wizard-resize-message", Static)
        assert warning.display is True
        assert "80x24" in str(warning.render())
        assert tiny.query_one("#wizard-content").display is False
        assert tiny.query_one("#wizard-actions").display is False
        assert tiny.context.state.current_step == "welcome"


def test_wizard_shell_escape_is_safe_save_exit(tmp_path: Path) -> None:
    asyncio.run(_wizard_shell_escape_is_safe_save_exit(tmp_path))


async def _wizard_shell_escape_is_safe_save_exit(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    screen = FirstRunWizardShell(
        WizardContext(composition, WizardState(WizardKind.FIRST_RUN, "welcome")),
        lambda _key: True,
    )
    app = _WizardHarness(screen)

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert screen.save_exit_requested is True
        assert "safe to resume" in str(screen.query_one("#wizard-status", Static).render())
