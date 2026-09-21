from __future__ import annotations

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.generation_monitor import GenerationMonitorController
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_tui import ProviderController
from deeper_dive.research_controller import PersistentResearchController
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp


def test_tui_uses_production_composed_controllers_by_default(tmp_path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))

    app = DeeperDiveApp(service)

    assert isinstance(app.provider_controller, ProviderController)
    assert isinstance(app.research_controller, PersistentResearchController)
    assert isinstance(app.preflight_controller, PreflightController)
    assert isinstance(app.generation_monitor_controller, GenerationMonitorController)
    assert app.generation_monitor_controller.runner is not None
