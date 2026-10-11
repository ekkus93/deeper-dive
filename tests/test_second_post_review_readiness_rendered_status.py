"""First-run readiness errors appear as actionable Textual content."""

import asyncio

from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_async_readiness import FirstRunReadinessCoordinator
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.storage.workspace import WorkspaceManager


def test_readiness_failure_is_rendered_with_retry_guidance(tmp_path) -> None:
    asyncio.run(_run_case(tmp_path))


async def _run_case(tmp_path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))

    def unavailable():
        raise OSError("provider is temporarily unavailable")

    async with app.run_test(size=(100, 35)) as pilot:
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        app._first_run_readiness.close()
        coordinator = FirstRunReadinessCoordinator(
            wizard.context, probe=unavailable, fingerprint=lambda: "fixed"
        )
        app._first_run_readiness = coordinator
        try:
            assert wizard.action_continue()
            wizard._request_runtime_readiness()
            for _ in range(60):
                await pilot.pause()
                if coordinator.view.state == "failed":
                    break
                await asyncio.sleep(0.01)
            assert coordinator.view.state == "failed"
            await pilot.pause()
            content = str(wizard.query_one("#wizard-step-content", Static).render())
            assert "needs attention" in content
            assert "provider is temporarily unavailable" in content
            assert "retry" in content.lower()
        finally:
            coordinator.close()
