"""Shared pilot helpers that drive the guided wizards through real clicks and key presses."""

from __future__ import annotations

from textual.pilot import Pilot
from textual.widgets import Input

# Textual ignores a second press on a Button while the first one's 0.2 s
# "active" animation is running, so every click waits a bit longer than that.
BUTTON_SETTLE_SECONDS = 0.3


async def click(pilot: Pilot[None], selector: str) -> None:
    """Click a widget the way a user would and let the UI settle."""

    assert await pilot.click(selector), f"click on {selector} did not hit a widget"
    await pilot.pause(BUTTON_SETTLE_SECONDS)


async def type_into(pilot: Pilot[None], selector: str, text: str) -> None:
    """Focus an Input by clicking it and type ``text`` one key at a time."""

    widget = pilot.app.screen.query_one(selector, Input)
    widget.value = ""
    assert await pilot.click(selector), f"click on {selector} did not hit a widget"
    await pilot.press(*text)
    await pilot.pause()
    assert widget.value == text, (selector, widget.value)


async def create_project(pilot: Pilot[None], name: str, topic: str) -> str:
    """Create a project through the project step's own controls."""

    await type_into(pilot, "#guided-project-name", name)
    await type_into(pilot, "#guided-project-topic", topic)
    await click(pilot, "#guided-project-create")
    project_id = pilot.app.screen.context.project_id  # type: ignore[attr-defined]
    assert project_id is not None
    return str(project_id)


async def add_pasted_source(pilot: Pilot[None], title: str, text: str) -> None:
    await type_into(pilot, "#guided-source-title", title)
    await type_into(pilot, "#guided-source-text", text)
    await click(pilot, "#guided-source-add-paste")


async def continue_step(pilot: Pilot[None], expected_step: str) -> None:
    """Press Continue and assert it moved exactly to ``expected_step``."""

    await click(pilot, "#wizard-continue")
    current = pilot.app.screen.context.state.current_step  # type: ignore[attr-defined]
    assert current == expected_step, (current, expected_step)
