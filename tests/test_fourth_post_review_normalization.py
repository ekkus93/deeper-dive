"""FPR-17: remaining normalization gaps and the no-op revision."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest
from test_episode_planner import _service

from deeper_dive.episode_config import EpisodeConfiguration

Variant = Callable[[EpisodeConfiguration], EpisodeConfiguration]

NOOP_VARIANTS: dict[str, Variant] = {
    "research override value whitespace": lambda c: replace(
        c, research_overrides={"policy": "  useful  "}
    ),
    "source override key whitespace": lambda c: replace(c, source_overrides={" s1 ": True}),
    "model override whitespace": lambda c: replace(
        c, model_overrides={" host_generation ": {"model": " m "}}
    ),
}


def _seed(configurations, episode_id: str, variant: str):  # type: ignore[no-untyped-def]
    """Store the canonical spelling first so the variant is a pure respelling."""

    current = configurations.load_configuration(episode_id)
    canonical = {
        "research override value whitespace": replace(
            current, research_overrides={"policy": "useful"}
        ),
        "source override key whitespace": replace(current, source_overrides={"s1": True}),
        "model override whitespace": replace(
            current, model_overrides={"host_generation": {"model": "m"}}
        ),
    }[variant]
    configurations.edit(episode_id, canonical)
    return configurations.load_configuration(episode_id)


@pytest.mark.parametrize("name", sorted(NOOP_VARIANTS))
def test_respelled_overrides_are_noops(tmp_path, name: str) -> None:
    service, episode_id, _ = _service(tmp_path)
    configurations = service.configurations
    canonical = _seed(configurations, episode_id, name)
    plan = service.build_plan(episode_id)
    before = service.repository.get_episode(episode_id)

    configurations.edit(episode_id, NOOP_VARIANTS[name](canonical))

    assert service.repository.get_episode(episode_id) == before
    assert service.load_plan(episode_id) == plan


@pytest.mark.parametrize("field", ["title", "focus", "audience", "technical_depth", "style"])
def test_non_text_fields_raise_value_error_not_attribute_error(field: str) -> None:
    config = EpisodeConfiguration(title="T")
    with pytest.raises(ValueError, match=field):
        replace(config, **{field: None}).normalized()  # type: ignore[arg-type]


def test_noop_returns_the_record_it_compared_against(tmp_path) -> None:
    service, episode_id, _ = _service(tmp_path)
    configurations = service.configurations
    current = configurations.load_configuration(episode_id)
    existing = service.repository.get_episode(episode_id)
    returned = configurations.edit(episode_id, current)
    assert returned == existing
    # The compared configuration comes from the same row as the returned revision.
    assert configurations.load_with_revision(episode_id)[1] == returned.config_json
