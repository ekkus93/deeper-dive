"""TPR-05: Retry under a saturated worker budget shows a visible message in the real UI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event

import pytest
from guided_pilot import click
from test_second_post_review_readiness_ui_retry import _snapshot
from textual.widgets import Static

from deeper_dive import guided_app as guided_app_module
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_async_readiness import FirstRunReadinessCoordinator
from deeper_dive.storage.workspace import WorkspaceManager


def test_retry_with_all_workers_blocked_is_visible_then_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(_exercise(tmp_path, monkeypatch))


async def _exercise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started = Event()
    release = Event()
    attempts: list[int] = []

    def probe():  # type: ignore[no-untyped-def]
        attempts.append(1)
        started.set()
        assert release.wait(60)
        return _snapshot()

    def factory(context):  # type: ignore[no-untyped-def]
        return FirstRunReadinessCoordinator(
            context,
            probe=probe,
            fingerprint=lambda: "stable-config",
            timeout_seconds=0.3,
            max_workers=1,
        )

    monkeypatch.setattr(guided_app_module, "FirstRunReadinessCoordinator", factory)
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    try:
        async with app.run_test(size=(100, 40)) as pilot:
            wizard = app.screen
            await click(pilot, "#wizard-continue")
            assert wizard.context.state.current_step == "system-check"
            coordinator = app._first_run_readiness

            # The single worker blocks past the UI deadline: the check fails by timeout.
            for _ in range(200):
                await pilot.pause(0.02)
                if coordinator.view.state == "failed":
                    break
            assert "timed out" in (coordinator.view.message or "")
            assert coordinator.active_worker_count == 1

            # An explicit Retry cannot start a probe; the user must be told why.
            await click(pilot, "#setup-retry-readiness")
            content = str(wizard.query_one("#wizard-step-content", Static).render())
            assert "still finishing" in content
            assert attempts == [1]

            # Once the blocked worker returns, Retry runs exactly one new probe.
            release.set()
            for _ in range(200):
                await pilot.pause(0.02)
                if coordinator.active_worker_count == 0:
                    break
            assert coordinator.active_worker_count == 0
            started.clear()
            await click(pilot, "#setup-retry-readiness")
            for _ in range(200):
                await pilot.pause(0.02)
                if len(attempts) == 2:
                    break
            assert attempts == [1, 1]
    finally:
        release.set()
