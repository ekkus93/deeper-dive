"""Shared effective provider/model assignment resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class EffectiveAssignment:
    """Resolved provider/model identity consumed by planning, preflight, and generation."""

    provider: str | None = None
    model: str | None = None


def resolve_assignment(
    role: str,
    *,
    episode: Mapping[str, Mapping[str, str]] | None = None,
    project: Mapping[str, Mapping[str, str]] | None = None,
    user: Mapping[str, Mapping[str, str]] | None = None,
    fallback: EffectiveAssignment | None = None,
) -> EffectiveAssignment:
    """Resolve one role with episode > project > user > explicit fallback precedence.

    Provider and model fields resolve independently so a higher-precedence layer may
    override only one field without discarding the lower-precedence value of the other.
    Empty strings are treated as unset.
    """

    layers = (episode or {}, project or {}, user or {})
    provider = _first(role, "provider", layers)
    model = _first(role, "model", layers)
    if fallback is not None:
        provider = provider or fallback.provider
        model = model or fallback.model
    return EffectiveAssignment(provider=provider, model=model)


def resolve_assignments(
    roles: tuple[str, ...],
    *,
    episode: Mapping[str, Mapping[str, str]] | None = None,
    project: Mapping[str, Mapping[str, str]] | None = None,
    user: Mapping[str, Mapping[str, str]] | None = None,
    fallbacks: Mapping[str, EffectiveAssignment] | None = None,
) -> dict[str, EffectiveAssignment]:
    """Resolve a set of roles through the same precedence algorithm."""

    fallback_map = fallbacks or {}
    return {
        role: resolve_assignment(
            role,
            episode=episode,
            project=project,
            user=user,
            fallback=fallback_map.get(role),
        )
        for role in roles
    }


def _first(
    role: str,
    field: str,
    layers: tuple[Mapping[str, Mapping[str, str]], ...],
) -> str | None:
    for layer in layers:
        value = layer.get(role, {}).get(field, "").strip()
        if value:
            return value
    return None
