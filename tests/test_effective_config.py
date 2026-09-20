from __future__ import annotations

from deeper_dive.effective_config import (
    EffectiveAssignment,
    resolve_assignment,
    resolve_assignments,
)


def test_episode_overrides_project_and_user_assignments() -> None:
    resolved = resolve_assignment(
        "planner",
        episode={"planner": {"provider": "episode-provider", "model": "episode-model"}},
        project={"planner": {"provider": "project-provider", "model": "project-model"}},
        user={"planner": {"provider": "user-provider", "model": "user-model"}},
    )

    assert resolved == EffectiveAssignment("episode-provider", "episode-model")


def test_project_overrides_user_when_episode_is_unset() -> None:
    resolved = resolve_assignment(
        "planner",
        project={"planner": {"provider": "project-provider", "model": "project-model"}},
        user={"planner": {"provider": "user-provider", "model": "user-model"}},
    )

    assert resolved == EffectiveAssignment("project-provider", "project-model")


def test_user_defaults_override_only_explicit_builtin_fallback() -> None:
    resolved = resolve_assignment(
        "planner",
        user={"planner": {"provider": "user-provider", "model": "user-model"}},
        fallback=EffectiveAssignment("builtin-provider", "builtin-model"),
    )

    assert resolved == EffectiveAssignment("user-provider", "user-model")


def test_fields_resolve_independently_across_layers() -> None:
    resolved = resolve_assignment(
        "dialogue",
        episode={"dialogue": {"model": "episode-model"}},
        project={"dialogue": {"provider": "project-provider"}},
        user={"dialogue": {"provider": "user-provider", "model": "user-model"}},
    )

    assert resolved == EffectiveAssignment("project-provider", "episode-model")


def test_resolve_assignments_uses_role_specific_fallbacks() -> None:
    resolved = resolve_assignments(
        ("planner", "dialogue"),
        user={"planner": {"provider": "configured"}},
        fallbacks={"dialogue": EffectiveAssignment("fallback", "fallback-model")},
    )

    assert resolved == {
        "planner": EffectiveAssignment("configured", None),
        "dialogue": EffectiveAssignment("fallback", "fallback-model"),
    }
