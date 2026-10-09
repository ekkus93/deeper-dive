from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import Button, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.composition import ProductionComposition
from deeper_dive.guided_workflow import SetupMode, WizardContext, WizardKind, WizardState
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
    def __init__(self, screen: WizardShell) -> None:
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


def test_wizard_mount_recovers_when_prior_production_state_is_invalid(tmp_path: Path) -> None:
    asyncio.run(_wizard_mount_recovers_when_prior_production_state_is_invalid(tmp_path))


async def _wizard_mount_recovers_when_prior_production_state_is_invalid(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    complete = {"project": True, "sources": False, "research": True, "hosts": True}
    screen = NewDeepDiveWizardShell(
        WizardContext(composition, WizardState(WizardKind.NEW_DEEP_DIVE, "episode")),
        lambda key: complete.get(key, False),
    )
    app = _WizardHarness(screen)

    async with app.run_test(size=(80, 24)):
        assert screen.context.state.current_step == "sources"
        assert "Step 2 of 7" in str(screen.query_one("#wizard-heading", Static).render())
        assert screen.query_one("#wizard-continue", Button).disabled


def test_first_run_welcome_mode_and_optional_system_check(tmp_path: Path) -> None:
    asyncio.run(_first_run_welcome_mode_and_optional_system_check(tmp_path))


async def _first_run_welcome_mode_and_optional_system_check(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    screen = FirstRunWizardShell(
        WizardContext(composition, WizardState(WizardKind.FIRST_RUN, "welcome")),
        lambda _key: True,
    )
    app = _WizardHarness(screen)
    async with app.run_test(size=(80, 24)) as pilot:
        assert "Quick Setup" in str(screen.query_one("#wizard-step-content", Static).render())
        selector = screen.query_one("#setup-mode", Select)
        selector.value = SetupMode.ADVANCED.value
        await pilot.pause()
        assert screen.context.state.setup_mode is SetupMode.ADVANCED
        screen.action_continue()
        await pilot.pause()
        assert screen.context.state.current_step == "system-check"
        assert "FFmpeg:" in str(screen.query_one("#wizard-step-content", Static).render())
        assert not selector.display


def test_first_run_system_check_details_are_explicit_and_safe(tmp_path: Path) -> None:
    asyncio.run(_first_run_system_check_details_are_explicit_and_safe(tmp_path))


async def _first_run_system_check_details_are_explicit_and_safe(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    screen = FirstRunWizardShell(
        WizardContext(composition, WizardState(WizardKind.FIRST_RUN, "system-check")),
        lambda _key: True,
    )
    app = _WizardHarness(screen)

    async with app.run_test(size=(100, 30)) as pilot:
        details = screen.query_one("#system-check-details", Button)
        assert details.display
        assert "Python/runtime: Ready" in str(
            screen.query_one("#wizard-step-content", Static).render()
        )
        details.press()
        await pilot.pause()
        text = str(screen.query_one("#wizard-step-content", Static).render())
        assert "Details:" in text
        assert "Remediation:" in text


class _DiagnosticWizard(WizardShell):
    def step_content(self, step_key: str) -> str:
        return "Diagnostic: api_key=example-value"


def test_wizard_shell_sanitizes_initial_and_updated_text(tmp_path: Path) -> None:
    asyncio.run(_wizard_shell_sanitizes_initial_and_updated_text(tmp_path))


async def _wizard_shell_sanitizes_initial_and_updated_text(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    screen = _DiagnosticWizard(
        WizardContext(composition, WizardState(WizardKind.NEW_DEEP_DIVE, "project")),
        lambda _key: True,
        title="Diagnostics",
        status_provider=lambda _key: "Provider: password=example-value",
    )
    async with _WizardHarness(screen).run_test(size=(80, 24)):
        content = str(screen.query_one("#wizard-step-content", Static).render())
        status = str(screen.query_one("#wizard-status", Static).render())
        assert "example-value" not in content
        assert "example-value" not in status
        assert "[REDACTED]" in content
        assert "[REDACTED]" in status
        screen.set_status("Failure: token=another-value")
        assert "another-value" not in str(screen.query_one("#wizard-status", Static).render())
        screen._sync_text()
        assert "example-value" not in str(screen.query_one("#wizard-status", Static).render())
        assert "example-value" not in str(screen.query_one("#wizard-step-content", Static).render())


def test_wizard_shell_native_select_arrow_and_space_activation(tmp_path: Path) -> None:
    asyncio.run(_wizard_shell_native_select_arrow_and_space_activation(tmp_path))


async def _wizard_shell_native_select_arrow_and_space_activation(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    screen = FirstRunWizardShell(
        WizardContext(composition, WizardState(WizardKind.FIRST_RUN, "welcome")),
        lambda _key: True,
    )
    app = _WizardHarness(screen)

    async with app.run_test(size=(100, 30)) as pilot:
        selector = screen.query_one("#setup-mode", Select)
        selector.focus()
        await pilot.press("enter")
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert selector.value == SetupMode.ADVANCED.value
        assert screen.context.state.setup_mode is SetupMode.ADVANCED

        continue_button = screen.query_one("#wizard-continue", Button)
        continue_button.focus()
        await pilot.press("space")
        await pilot.pause()
        assert screen.context.state.current_step == "system-check"


@pytest.mark.parametrize("kind", [WizardKind.FIRST_RUN, WizardKind.NEW_DEEP_DIVE])
@pytest.mark.parametrize("size", [(100, 30), (80, 24)])
def test_shared_wizard_action_geometry_and_text_progress_at_supported_sizes(
    tmp_path: Path, kind: WizardKind, size: tuple[int, int]
) -> None:
    asyncio.run(_shared_wizard_action_geometry(tmp_path, kind, size))


async def _shared_wizard_action_geometry(
    tmp_path: Path, kind: WizardKind, size: tuple[int, int]
) -> None:
    composition = _composition(tmp_path)
    context = WizardContext(
        composition, WizardState(kind, "welcome" if kind is WizardKind.FIRST_RUN else "project")
    )
    screen = (
        FirstRunWizardShell(context, lambda key: key in {"welcome", "project"})
        if kind is WizardKind.FIRST_RUN
        else NewDeepDiveWizardShell(context, lambda key: key in {"welcome", "project"})
    )
    async with _WizardHarness(screen).run_test(size=size) as pilot:
        await pilot.pause()
        assert screen.query_one("#wizard-actions").display
        assert not screen.query_one("#wizard-resize-message").display
        assert screen.query_one("#wizard-content").display
        progress = str(screen.query_one("#wizard-progress", Static).render())
        assert "(current)" in progress
        assert "(upcoming)" in progress
        for action in ("back", "continue", "save-exit", "help"):
            button = screen.query_one(f"#wizard-{action}", Button)
            assert button.region.width > 0
            assert button.region.right <= size[0]
            assert button.region.bottom <= size[1]


@pytest.mark.parametrize("kind", [WizardKind.FIRST_RUN, WizardKind.NEW_DEEP_DIVE])
def test_wizard_below_minimum_policy_restores_actions_without_losing_step(
    tmp_path: Path, kind: WizardKind
) -> None:
    asyncio.run(_wizard_resize_preserves_step(tmp_path, kind))


async def _wizard_resize_preserves_step(tmp_path: Path, kind: WizardKind) -> None:
    composition = _composition(tmp_path)
    step = "welcome" if kind is WizardKind.FIRST_RUN else "project"
    context = WizardContext(composition, WizardState(kind, step))
    screen = (
        FirstRunWizardShell(context, lambda _key: True)
        if kind is WizardKind.FIRST_RUN
        else NewDeepDiveWizardShell(context, lambda _key: True)
    )
    async with _WizardHarness(screen).run_test(size=(80, 24)):
        screen._apply_viewport_policy(79, 23)
        assert screen.query_one("#wizard-resize-message").display
        assert not screen.query_one("#wizard-actions").display
        assert not screen.query_one("#wizard-content").display
        assert screen.context.state.current_step == step
        screen._apply_viewport_policy(80, 24)
        assert not screen.query_one("#wizard-resize-message").display
        assert screen.query_one("#wizard-actions").display
        assert screen.query_one("#wizard-content").display
        assert screen.context.state.current_step == step
