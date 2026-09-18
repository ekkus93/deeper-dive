"""Provider/model assignments for generation roles with explicit override precedence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from deeper_dive.llm import LLMProviderRegistry


class ModelRole(StrEnum):
    CORPUS_ANALYSIS = "corpus_analysis"
    RESEARCH_PLANNING = "research_planning"
    SOURCE_ANALYSIS = "source_analysis"
    EPISODE_PLANNING = "episode_planning"
    DIRECTING = "directing"
    HOST_GENERATION = "host_generation"
    VERIFICATION = "verification"


REQUIRED_MODEL_ROLES = tuple(ModelRole)


@dataclass(frozen=True, slots=True)
class ModelAssignment:
    provider: str
    model: str

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("provider and model must not be empty")


@dataclass(frozen=True, slots=True)
class ModelRoleAssignments:
    """Assignments at user, project, and episode scopes."""

    user: Mapping[ModelRole, ModelAssignment] = field(default_factory=dict)
    project: Mapping[ModelRole, ModelAssignment] = field(default_factory=dict)
    episode: Mapping[ModelRole, ModelAssignment] = field(default_factory=dict)

    def resolve(self, role: ModelRole) -> ModelAssignment | None:
        """Resolve episode > project > user precedence."""

        return self.episode.get(role) or self.project.get(role) or self.user.get(role)

    def resolved(self) -> dict[ModelRole, ModelAssignment]:
        return {
            role: assignment
            for role in REQUIRED_MODEL_ROLES
            if (assignment := self.resolve(role)) is not None
        }


@dataclass(frozen=True, slots=True)
class ModelRoleBlocker:
    role: ModelRole
    message: str


@dataclass(frozen=True, slots=True)
class ModelRolePreflight:
    assignments: Mapping[ModelRole, ModelAssignment]
    blockers: tuple[ModelRoleBlocker, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers


def preflight_model_roles(
    assignments: ModelRoleAssignments,
    registry: LLMProviderRegistry,
    *,
    required_roles: tuple[ModelRole, ...] = REQUIRED_MODEL_ROLES,
) -> ModelRolePreflight:
    """Resolve roles and report missing providers/models as actionable blockers."""

    resolved: dict[ModelRole, ModelAssignment] = {}
    blockers: list[ModelRoleBlocker] = []
    discovered: dict[str, set[str]] = {}
    for role in required_roles:
        assignment = assignments.resolve(role)
        if assignment is None:
            blockers.append(ModelRoleBlocker(role, f"no provider/model assignment for {role.value}"))
            continue
        try:
            provider = registry.get(assignment.provider)
        except KeyError:
            blockers.append(
                ModelRoleBlocker(role, f"unknown provider {assignment.provider!r} for {role.value}")
            )
            continue
        if assignment.provider not in discovered:
            discovered[assignment.provider] = {model.model for model in provider.models()}
        if assignment.model not in discovered[assignment.provider]:
            blockers.append(
                ModelRoleBlocker(
                    role,
                    f"model {assignment.model!r} is unavailable from provider {assignment.provider!r}",
                )
            )
            continue
        resolved[role] = assignment
    return ModelRolePreflight(resolved, tuple(blockers))
