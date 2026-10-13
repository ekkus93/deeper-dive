"""Textual first-run readiness retry status regression."""

from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event

import pytest
from textual.widgets import Button, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.first_run import FirstRunSystemCheck
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_async_readiness import FirstRunReadinessCoordinator, FirstRunRuntimeSnapshot
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_readiness import FirstRunDerivedReadiness
from deeper_dive.storage.workspace import WorkspaceManager


def test_textual_readiness_failure_checking_retry_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = Event()
    attempts: list[int] = []
    credential = "readiness-provider-canary"

    def probe(self: FirstRunReadinessCoordinator) -> FirstRunRuntimeSnapshot:
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError(
                f"provider temporarily unavailable; Authorization: Bearer {credential}; status=503"
            )
        assert release.wait(5)
        return FirstRunRuntimeSnapshot(
            readiness=FirstRunDerivedReadiness(True, True, True, True, False, True, False, True),
            system_check=FirstRunSystemCheck("Python test", True, False, False, False, ()),
        )

    monkeypatch.setattr(FirstRunReadinessCoordinator, "_probe_runtime", probe)

    async def exercise() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 35)) as pilot:
            wizard = app.screen
            assert isinstance(wizard, GuidedFirstRunWizard)
            wizard.action_continue()
            coordinator = app._first_run_readiness
            for _ in range(100):
                if coordinator.view.state == "failed":
                    break
                await pilot.pause()
            assert coordinator.view.state == "failed"
            assert credential not in (coordinator.view.message or "")
            content = str(wizard.query_one("#wizard-step-content", Static).render())
            assert "needs attention" in content.lower()
            assert "retry" in content.lower()
            assert "status=503" in content
            assert credential not in content
            button = wizard.query_one("#setup-retry-readiness", Button)
            assert button.display
            button.press()
            await pilot.pause()
            assert coordinator.view.state == "checking"
            checking = str(wizard.query_one("#wizard-step-content", Static).render())
            assert "Checking provider" in checking
            assert credential not in checking
            release.set()
            for _ in range(100):
                if coordinator.view.state == "ready":
                    break
                await pilot.pause()
            assert coordinator.view.state == "ready"
            ready = str(wizard.query_one("#wizard-step-content", Static).render())
            assert "Python/runtime: Ready" in ready
            assert credential not in ready
            assert attempts == [1, 1]

    try:
        asyncio.run(exercise())
    finally:
        release.set()
