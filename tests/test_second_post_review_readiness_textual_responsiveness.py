"""Textual first-run navigation remains live under a noncooperative readiness probe."""

from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event
from typing import cast

from guided_pilot import BUTTON_SETTLE_SECONDS

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_async_readiness import (
    FirstRunReadinessCoordinator,
    FirstRunRuntimeSnapshot,
)
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.storage.workspace import WorkspaceManager


def test_first_run_navigation_remains_responsive_with_blocked_provider_probe(
    tmp_path: Path,
) -> None:
    asyncio.run(_first_run_navigation_with_blocked_provider_probe(tmp_path))


async def _first_run_navigation_with_blocked_provider_probe(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    release = Event()
    started = Event()

    def never_finishes_until_released() -> FirstRunRuntimeSnapshot:
        started.set()
        assert release.wait(60), "blocked provider probe was not released"
        return cast(FirstRunRuntimeSnapshot, object())

    try:
        async with app.run_test(size=(100, 35)) as pilot:
            wizard = app.screen
            assert isinstance(wizard, GuidedFirstRunWizard)
            app._first_run_readiness.close()
            coordinator = FirstRunReadinessCoordinator(
                wizard.context,
                probe=never_finishes_until_released,
                fingerprint=lambda: "fixed-provider-fingerprint",
                timeout_seconds=0.05,
                max_workers=1,
            )
            app._first_run_readiness = coordinator
            wizard._request_runtime_readiness()
            assert await asyncio.to_thread(started.wait, 3)
            assert coordinator.view.state == "checking"
            assert coordinator.active_worker_count == 1

            # Real clicks and key presses, not direct action calls. One click must
            # advance exactly one step; Textual ignores a press while the previous
            # one's 0.2 s button animation is still running, hence the pauses.
            await pilot.click("#wizard-continue")
            await pilot.pause(BUTTON_SETTLE_SECONDS)
            assert wizard.context.state.current_step == "system-check"
            await pilot.click("#wizard-continue")
            await pilot.pause(BUTTON_SETTLE_SECONDS)
            assert wizard.context.state.current_step == "ai-provider"
            await pilot.click("#wizard-back")
            await pilot.pause(BUTTON_SETTLE_SECONDS)
            assert wizard.context.state.current_step == "system-check"
            await pilot.press("tab")
            await pilot.pause()

            await pilot.press("h")
            await pilot.pause()
            assert app.screen.id == "screen-home"
            app.action_navigate("setup")
            await pilot.pause()
            assert app.screen is wizard
            assert wizard.action_continue()
            assert wizard.context.state.current_step == "ai-provider"
            app.action_navigate("home")
            await pilot.pause()
            assert app.screen.id == "screen-home"

            # The visible UI deadline can expire without joining the blocked
            # daemon thread; neither navigation nor repeat requests may wait.
            for _ in range(200):
                if coordinator.view.state == "failed":
                    break
                await pilot.pause(0.01)
            assert coordinator.view.state == "failed"
            assert "timed out" in (coordinator.view.message or "")
            for _ in range(20):
                assert not coordinator.request(app)
            assert coordinator.active_worker_count == 1
            assert coordinator.timeout_timer_count == 0
            assert app.screen.id == "screen-home"
    finally:
        release.set()
