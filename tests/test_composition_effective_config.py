from __future__ import annotations

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.composition import ProductionComposition
from deeper_dive.model_roles import ModelAssignment, ModelRole
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import UserConfigStore


def test_composition_resolves_model_roles_with_documented_precedence(tmp_path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    service.workspaces.initialize()
    store = UserConfigStore(service.workspaces.data_dir / "config.json")
    config = store.load()
    config.defaults["episode_planning"] = "user-provider:user-model"
    config.defaults["host_generation"] = "user-provider:user-host-model"
    store.save(config)
    project = service.create_project(
        "Precedence",
        instructions=(
            '{"model_defaults":{"episode_planning":"project-provider:project-model",'
            '"directing":"project-provider:project-directing-model"}}'
        ),
    )
    composition = ProductionComposition.build(service=service)

    assignments, errors = composition.effective_model_role_assignments(
        project.id,
        episode_overrides={
            "episode_planning": {
                "provider": "episode-provider",
                "model": "episode-model",
            }
        },
    )

    assert not errors
    assert assignments.resolve(ModelRole.EPISODE_PLANNING) == ModelAssignment(
        "episode-provider", "episode-model"
    )
    assert assignments.resolve(ModelRole.DIRECTING) == ModelAssignment(
        "project-provider", "project-directing-model"
    )
    assert assignments.resolve(ModelRole.HOST_GENERATION) == ModelAssignment(
        "user-provider", "user-host-model"
    )
