"""Shared pilot helpers that drive the guided wizards through real clicks and key presses."""

from __future__ import annotations

import json
import time
from collections.abc import Callable

from textual.pilot import Pilot
from textual.widgets import Input

from deeper_dive.llm import FakeLLMProvider, LLMRequest

# Textual ignores a second press on a Button while the first one's 0.2 s
# "active" animation is running, so every click waits a bit longer than that.
BUTTON_SETTLE_SECONDS = 0.3


async def wait_until(
    pilot: Pilot[None], condition: Callable[[], bool], *, timeout: float = 10.0
) -> None:
    """Let the app run until ``condition()`` holds, instead of sleeping a fixed time."""

    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached within the timeout")
        await pilot.pause(0.02)


async def click(pilot: Pilot[None], selector: str) -> None:
    """Click a widget the way a user would and let the UI settle."""

    pilot.app.screen.query_one(selector).scroll_visible(animate=False)
    await pilot.pause()
    assert await pilot.click(selector), f"click on {selector} did not hit a widget"
    await pilot.pause(BUTTON_SETTLE_SECONDS)


async def type_into(pilot: Pilot[None], selector: str, text: str) -> None:
    """Focus an Input by clicking it and type ``text`` one key at a time."""

    widget = pilot.app.screen.query_one(selector, Input)
    widget.scroll_visible(animate=False)
    await pilot.pause()
    assert await pilot.click(selector), f"click on {selector} did not hit a widget"
    if widget.value:
        # Clear the way a user would: jump to the end, then delete everything before it.
        await pilot.press("end", "ctrl+u")
        assert widget.value == "", (selector, widget.value)
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


async def reach_hosts(pilot: Pilot[None]) -> None:
    """Walk a new Deep Dive to the hosts step with real input only.

    Two setup calls are deliberately not real input, and neither is a step of the
    flow under test: ``_first_run_readiness.close()`` stops the background readiness
    probe so it cannot race the clicks, and ``action_navigate("new")`` is the app's
    own routing entry. A fresh data directory starts in first-run setup, whose
    prerequisites (a live provider) cannot be satisfied without network or a model,
    so the Home screen's "New Deep Dive" button is not reachable from there.
    """

    pilot.app._first_run_readiness.close()  # type: ignore[attr-defined]
    await pilot.pause()
    pilot.app.action_navigate("new")  # type: ignore[attr-defined]
    await pilot.pause()
    await create_project(pilot, "Real input", "Does typing work")
    await continue_step(pilot, "sources")
    await add_pasted_source(pilot, "Notes", "Evidence for the real input flow.")
    await continue_step(pilot, "research")
    await click(pilot, "#guided-research-save")
    await continue_step(pilot, "hosts")


async def choose_option(pilot: Pilot[None], selector: str, steps_down: int = 1) -> None:
    """Open a Select by focusing it and move ``steps_down`` options by keyboard."""

    widget = pilot.app.screen.query_one(selector)
    widget.scroll_visible(animate=False)
    widget.focus()
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()
    # The overlay opens on the current value; move down ``steps_down`` options.
    for _ in range(steps_down):
        await pilot.press("down")
    await pilot.press("enter")
    await pilot.pause()


def _plan_json(titles: tuple[str, ...]) -> str:
    return json.dumps(
        {
            "segments": [
                {
                    "title": title,
                    "purpose": f"Purpose of {title}",
                    "target_duration_seconds": 600,
                    "questions": [],
                    "evidence_ids": [],
                    "lead_host_ids": [],
                }
                for title in titles
            ]
        }
    )


class PlanningLLM(FakeLLMProvider):
    """Fake planning model: a full plan normally, one replacement segment on request."""

    def __init__(self) -> None:
        super().__init__(response=_plan_json(("Opening", "Analysis")))
        self.plan_requests = 0

    def _response_for(self, request: LLMRequest) -> str:
        self.plan_requests += 1
        text = "\n".join(message.content for message in request.messages)
        if "regenerate_segment" in text:
            return _plan_json(("Regenerated opening",))
        return self.response


async def reach_plan(pilot: Pilot[None]) -> PlanningLLM:
    """Walk a new Deep Dive to a built two-segment plan using only real input.

    Configures a fake provider as the episode-planning model through the
    production provider controller, then drives every step by click and typing.
    """

    app = pilot.app
    controller = app.provider_controller  # type: ignore[attr-defined]
    controller.save_provider(
        "fake",
        "fake",
        default_model="fake-v1",
        network_scope="local",
        default_updates={"episode_planning": "fake:fake-v1"},
    )
    llm = PlanningLLM()
    controller.llm_registry.register(llm)
    await reach_hosts(pilot)
    await click(pilot, "#guided-host-recommended")
    await click(pilot, "#guided-host-order-save")
    await continue_step(pilot, "episode")
    await type_into(pilot, "#guided-episode-title", "Real title")
    await type_into(pilot, "#guided-episode-focus", "Real focus question")
    await click(pilot, "#guided-episode-save")
    await continue_step(pilot, "plan")
    await click(pilot, "#guided-plan-build")
    await wait_until(pilot, lambda: app.screen._plan is not None)  # type: ignore[attr-defined]
    wizard = app.screen
    assert wizard._plan is not None and len(wizard._plan.segments) == 2  # type: ignore[attr-defined]
    return llm
