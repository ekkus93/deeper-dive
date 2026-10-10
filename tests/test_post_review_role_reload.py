"""Persisted non-default model-role assignments survive reload and retain parity."""

from __future__ import annotations

from pathlib import Path

from deeper_dive.guided_readiness import _assignment_targets_ready_llm
from deeper_dive.llm import FakeLLMProvider, LLMModel, LLMProviderRegistry
from deeper_dive.model_roles import (
    ModelRole,
    ModelRoleAssignments,
    effective_model_role_assignments,
    preflight_model_roles,
)
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


class TwoModelProvider(FakeLLMProvider):
    def models(self) -> tuple[LLMModel, ...]:
        return (
            LLMModel(self.provider_id, "model-a"),
            LLMModel(self.provider_id, "model-b"),
        )


def test_non_default_role_assignment_survives_config_reload_and_preflight(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    store.save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="model-a")
            },
            defaults={ModelRole.EPISODE_PLANNING.value: "planner:model-b"},
        )
    )

    # Reload through a new store instance, just as a fresh application process does.
    reloaded = UserConfigStore(path).load()
    assignments, errors = effective_model_role_assignments(user_defaults=reloaded.defaults)
    assert not errors
    assignment = assignments.resolve(ModelRole.EPISODE_PLANNING)
    assert assignment is not None
    assert assignment.provider == "planner"
    assert assignment.model == "model-b"

    registry = LLMProviderRegistry()
    runtime = TwoModelProvider(provider_id="planner", model="model-a")
    registry.register(runtime)
    discovered = frozenset(model.model for model in runtime.models())
    controller = ProviderController(UserConfigStore(path), registry, {})
    assert _assignment_targets_ready_llm(
        controller,
        reloaded.providers,
        {"planner": discovered},
        assignment,
    )
    assert preflight_model_roles(
        ModelRoleAssignments(user={ModelRole.EPISODE_PLANNING: assignment}),
        registry,
        required_roles=(ModelRole.EPISODE_PLANNING,),
    ).ready
