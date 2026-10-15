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


def test_noop_compares_against_the_row_it_read_even_if_another_writer_lands(tmp_path) -> None:
    """5PR-11: discriminating version of the no-op revision check.

    Another writer edits the episode right after ``edit`` read it. The no-op must be
    judged against that row (and return it), not against a second, newer read that
    would make the unchanged form look like a change and then lose the CAS.
    """

    from unittest.mock import patch

    from deeper_dive.storage.episode_repositories import HostEpisodeRepository

    service, episode_id, _ = _service(tmp_path)
    configurations = service.configurations
    current = configurations.load_configuration(episode_id)
    original = service.repository.get_episode(episode_id)
    real = HostEpisodeRepository.get_episode
    calls = {"n": 0}

    def get_then_bump(self, requested_id):  # type: ignore[no-untyped-def]
        record = real(self, requested_id)
        calls["n"] += 1
        if calls["n"] == 1:
            configurations.edit(episode_id, replace(current, title="Edited elsewhere"))
        return record

    with patch.object(HostEpisodeRepository, "get_episode", get_then_bump):
        returned = configurations.edit(episode_id, current)

    assert returned == original
    assert calls["n"] >= 1
