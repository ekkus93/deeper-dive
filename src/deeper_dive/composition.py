"""Production dependency composition for Deeper Dive surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.generation_monitor import GenerationMonitorController
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_factory import ProviderBuildResult, ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.research_controller import PersistentResearchController
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import UserConfigStore


@dataclass(slots=True)
class ProductionComposition:
    """Application-wide services constructed through one production path."""

    service: DeeperDiveService
    config_store: UserConfigStore
    providers: ProviderBuildResult
    provider_controller: ProviderController
    research_controller: PersistentResearchController
    preflight_controller: PreflightController
    generation_monitor_controller: GenerationMonitorController

    @classmethod
    def build(
        cls,
        data_dir: Path | None = None,
        *,
        service: DeeperDiveService | None = None,
        provider_factory: ProviderFactory | None = None,
    ) -> ProductionComposition:
        app_service = service or DeeperDiveService(WorkspaceManager(data_dir))
        app_service.workspaces.initialize()
        config_store = UserConfigStore(
            app_service.workspaces.data_dir / "config.json"
        )
        providers = (provider_factory or ProviderFactory()).build(config_store.load())
        provider_controller = ProviderController(
            config_store,
            providers.llm_registry,
            providers.tts_providers,
        )
        research_controller = PersistentResearchController(
            lambda project_id: (
                app_service.workspaces.project_root(project_id) / "project.db"
            )
        )
        return cls(
            service=app_service,
            config_store=config_store,
            providers=providers,
            provider_controller=provider_controller,
            research_controller=research_controller,
            preflight_controller=PreflightController(),
            generation_monitor_controller=GenerationMonitorController(),
        )
