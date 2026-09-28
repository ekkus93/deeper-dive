from __future__ import annotations

from deeper_dive.generation_roles import (
    GenerationRoleContext,
    required_generation_model_roles,
)
from deeper_dive.model_roles import ModelAssignment, ModelRole, ModelRoleAssignments


def test_required_generation_roles_follow_plan_conversation_and_configured_roles() -> None:
    assignments = ModelRoleAssignments(
        user={
            ModelRole.DIRECTING: ModelAssignment("fake", "fake-v1"),
            ModelRole.VERIFICATION: ModelAssignment("fake", "fake-v1"),
        },
    )

    roles = required_generation_model_roles(
        GenerationRoleContext(
            valid_plan_exists=False,
            conversation_work_remains=True,
            assignments=assignments,
        )
    )

    assert roles == (
        ModelRole.EPISODE_PLANNING,
        ModelRole.HOST_GENERATION,
        ModelRole.DIRECTING,
        ModelRole.VERIFICATION,
    )


def test_required_generation_roles_are_extensible_and_deduplicated() -> None:
    assignments = ModelRoleAssignments(
        user={ModelRole.DIRECTING: ModelAssignment("fake", "fake-v1")},
    )

    roles = required_generation_model_roles(
        GenerationRoleContext(
            valid_plan_exists=True,
            conversation_work_remains=False,
            assignments=assignments,
            additional_roles=(ModelRole.SOURCE_ANALYSIS, ModelRole.DIRECTING),
        )
    )

    assert roles == (ModelRole.DIRECTING, ModelRole.SOURCE_ANALYSIS)
