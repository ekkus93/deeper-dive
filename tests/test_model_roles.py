from __future__ import annotations

from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.model_roles import (
    REQUIRED_MODEL_ROLES,
    ModelAssignment,
    ModelRole,
    ModelRoleAssignments,
    effective_model_role_assignments,
    preflight_model_roles,
)


def test_episode_project_user_precedence() -> None:
    user = ModelAssignment("fake", "user-model")
    project = ModelAssignment("fake", "project-model")
    episode = ModelAssignment("fake", "episode-model")
    role = ModelRole.HOST_GENERATION

    assert ModelRoleAssignments(user={role: user}).resolve(role) == user
    assert ModelRoleAssignments(user={role: user}, project={role: project}).resolve(role) == project
    assert (
        ModelRoleAssignments(
            user={role: user}, project={role: project}, episode={role: episode}
        ).resolve(role)
        == episode
    )


def test_effective_assignment_parser_applies_episode_project_user_precedence() -> None:
    assignments, errors = effective_model_role_assignments(
        user_defaults={
            "episode_planning": "user-provider:user-model",
            "host_generation": "user-provider:user-host-model",
            "local_only": "true",
        },
        project_defaults={
            "episode_planning": "project-provider:project-model",
            "directing": "project-provider:project-directing-model",
        },
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


def test_effective_assignment_parser_reports_actionable_errors() -> None:
    assignments, errors = effective_model_role_assignments(
        user_defaults={"episode_planning": "missing-separator"},
        episode_overrides={
            "unknown_role": {"provider": "fake", "model": "fake-v1"},
            "directing": {"provider": "fake"},
        },
    )

    assert assignments.resolve(ModelRole.EPISODE_PLANNING) is None
    assert "default episode_planning assignment must use provider:model" in errors
    assert "unknown episode model role 'unknown_role'" in errors
    assert "episode override directing must include provider and model" in errors


def test_all_documented_roles_are_required() -> None:
    assert {role.value for role in REQUIRED_MODEL_ROLES} == {
        "corpus_analysis",
        "research_planning",
        "source_analysis",
        "episode_planning",
        "directing",
        "host_generation",
        "verification",
    }


def test_preflight_resolves_all_roles_or_reports_blockers() -> None:
    registry = LLMProviderRegistry()
    registry.register(FakeLLMProvider(model="fake-v1"))
    assignment = ModelAssignment("fake", "fake-v1")
    complete = ModelRoleAssignments(user={role: assignment for role in REQUIRED_MODEL_ROLES})
    result = preflight_model_roles(complete, registry)
    assert result.ready
    assert set(result.assignments) == set(REQUIRED_MODEL_ROLES)

    incomplete = ModelRoleAssignments(user={ModelRole.CORPUS_ANALYSIS: assignment})
    blocked = preflight_model_roles(incomplete, registry)
    assert not blocked.ready
    assert {item.role for item in blocked.blockers} == set(REQUIRED_MODEL_ROLES) - {
        ModelRole.CORPUS_ANALYSIS
    }


def test_preflight_reports_unknown_provider_and_model() -> None:
    registry = LLMProviderRegistry()
    registry.register(FakeLLMProvider(model="available"))
    assignments = ModelRoleAssignments(
        user={
            ModelRole.CORPUS_ANALYSIS: ModelAssignment("missing", "m"),
            ModelRole.RESEARCH_PLANNING: ModelAssignment("fake", "missing-model"),
        }
    )
    result = preflight_model_roles(
        assignments,
        registry,
        required_roles=(ModelRole.CORPUS_ANALYSIS, ModelRole.RESEARCH_PLANNING),
    )
    assert not result.ready
    assert "unknown provider" in result.blockers[0].message
    assert "unavailable" in result.blockers[1].message
