from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import UserConfigStore


@dataclass(slots=True)
class _PreflightApp:
    service: DeeperDiveService
    provider_controller: ProviderController
    preflight_controller: PreflightController
    current_project_id: str | None
    current_project_name: str | None
    current_episode_id: str | None = None

    def action_navigate(self, destination: str) -> None:  # pragma: no cover
        raise AssertionError(destination)


def test_preflight_reports_project_default_assignment_before_user_default(
    tmp_path: Path,
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    instructions = '{"model_defaults":{"episode_planning":"project-provider:project-v1"}}'
    project = service.create_project("Preflight Project Defaults", instructions=instructions)
    service.hosts(project.id).create_host(
        HostProfile("h1", project.id, "Host One").to_record()
    )
    controller = PreflightController()
    app = _PreflightApp(
        service=service,
        provider_controller=_provider_controller(tmp_path),
        preflight_controller=controller,
        current_project_id=project.id,
        current_project_name=project.name,
    )

    presentation = controller.build(app)

    assert "episode_planning: project-provider:project-v1" in presentation.llm_rows


def _provider_controller(tmp_path: Path) -> ProviderController:
    registry = LLMProviderRegistry()
    registry.register(FakeLLMProvider(provider_id="user-provider", model="user-v1"))
    registry.register(FakeLLMProvider(provider_id="project-provider", model="project-v1"))
    store = UserConfigStore(tmp_path / "config.json")
    config = store.load()
    config.defaults["episode_planning"] = "user-provider:user-v1"
    store.save(config)
    return ProviderController(store, registry, {})
