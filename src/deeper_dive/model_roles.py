"""Provider/model assignments for generation roles with explicit override precedence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

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
PROJECT_MODEL_DEFAULTS_KEY = "model_defaults"


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


def project_model_defaults_from_instructions(instructions: str) -> dict[str, str]:
    """Extract project-level model defaults from a JSON project-instructions payload.

    Project instructions may remain ordinary freeform text. Only a top-level JSON object
    containing a ``model_defaults`` mapping participates in model-role resolution.
    """

    if not instructions.strip():
        return {}
    try:
        payload: object = json.loads(instructions)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    raw_defaults = payload.get(PROJECT_MODEL_DEFAULTS_KEY)
    if not isinstance(raw_defaults, Mapping):
        return {}
    return {
        str(role): value
        for role, value in raw_defaults.items()
        if isinstance(role, str) and isinstance(value, str)
    }


def effective_model_role_assignments(
    *,
    user_defaults: Mapping[str, str],
    project_defaults: Mapping[str, str] | None = None,
    episode_overrides: Mapping[str, Any] | None = None,
) -> tuple[ModelRoleAssignments, tuple[str, ...]]:
    """Parse and combine persisted assignment scopes using documented precedence."""

    user, user_errors = _assignments_from_default_strings(user_defaults, "default")
    project, project_errors = _assignments_from_default_strings(
        project_defaults or {}, "project default"
    )
    episode, episode_errors = _assignments_from_episode_overrides(episode_overrides or {})
    return (
        ModelRoleAssignments(user=user, project=project, episode=episode),
        (*user_errors, *project_errors, *episode_errors),
    )


def _assignments_from_default_strings(
    values: Mapping[str, str],
    label: str,
) -> tuple[dict[ModelRole, ModelAssignment], tuple[str, ...]]:
    assignments: dict[ModelRole, ModelAssignment] = {}
    errors: list[str] = []
    for role in ModelRole:
        raw = values.get(role.value)
        if raw is None:
            continue
        assignment, error = _assignment_from_identity(raw, role=role, label=label)
        if error is not None:
            errors.append(error)
            continue
        assert assignment is not None
        assignments[role] = assignment
    return assignments, tuple(errors)


def _assignments_from_episode_overrides(
    values: Mapping[str, Any],
) -> tuple[dict[ModelRole, ModelAssignment], tuple[str, ...]]:
    assignments: dict[ModelRole, ModelAssignment] = {}
    errors: list[str] = []
    for key, raw in values.items():
        try:
            role = ModelRole(key)
        except ValueError:
            errors.append(f"unknown episode model role {key!r}")
            continue
        assignment, error = _assignment_from_override(raw, role)
        if error is not None:
            errors.append(error)
            continue
        assert assignment is not None
        assignments[role] = assignment
    return assignments, tuple(errors)


def _assignment_from_override(
    raw: Any,
    role: ModelRole,
) -> tuple[ModelAssignment | None, str | None]:
    if isinstance(raw, str):
        return _assignment_from_identity(raw, role=role, label="episode override")
    if not isinstance(raw, Mapping):
        return (
            None,
            f"episode override {role.value} must be provider:model or provider/model fields",
        )
    provider = raw.get("provider")
    model = raw.get("model")
    if not isinstance(provider, str) or not isinstance(model, str):
        return None, f"episode override {role.value} must include provider and model"
    try:
        return ModelAssignment(provider.strip(), model.strip()), None
    except ValueError as exc:
        return None, f"episode override {role.value} is invalid: {exc}"


def _assignment_from_identity(
    raw: str,
    *,
    role: ModelRole,
    label: str,
) -> tuple[ModelAssignment | None, str | None]:
    try:
        provider, model = raw.split(":", 1)
    except ValueError:
        return None, f"{label} {role.value} assignment must use provider:model"
    try:
        return ModelAssignment(provider.strip(), model.strip()), None
    except ValueError as exc:
        return None, f"{label} {role.value} assignment is invalid: {exc}"


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
            blockers.append(
                ModelRoleBlocker(role, f"no provider/model assignment for {role.value}")
            )
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
                    f"model {assignment.model!r} is unavailable from provider "
                    f"{assignment.provider!r}",
                )
            )
            continue
        resolved[role] = assignment
    return ModelRolePreflight(resolved, tuple(blockers))
