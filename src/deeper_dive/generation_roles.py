"""Derive model roles executed by production generation."""

from __future__ import annotations

from dataclasses import dataclass

from deeper_dive.model_roles import ModelRole, ModelRoleAssignments


@dataclass(frozen=True, slots=True)
class GenerationRoleContext:
    """Inputs for production generation model-role derivation."""

    valid_plan_exists: bool
    conversation_work_remains: bool
    assignments: ModelRoleAssignments
    additional_roles: tuple[ModelRole, ...] = ()


def required_generation_model_roles(context: GenerationRoleContext) -> tuple[ModelRole, ...]:
    """Return model roles the selected episode generation path will execute.

    The helper keeps the role derivation extensible: future source/research roles can
    be added by supplying ``additional_roles`` without duplicating the base logic.
    """

    roles: list[ModelRole] = []
    if not context.valid_plan_exists:
        roles.append(ModelRole.EPISODE_PLANNING)
    if context.conversation_work_remains:
        roles.append(ModelRole.HOST_GENERATION)
    if context.conversation_work_remains and context.assignments.resolve(ModelRole.DIRECTING):
        roles.append(ModelRole.DIRECTING)
    if context.assignments.resolve(ModelRole.VERIFICATION) is not None:
        roles.append(ModelRole.VERIFICATION)
    roles.extend(context.additional_roles)
    return _dedupe(roles)


def _dedupe(roles: list[ModelRole]) -> tuple[ModelRole, ...]:
    deduped: list[ModelRole] = []
    for role in roles:
        if role not in deduped:
            deduped.append(role)
    return tuple(deduped)
