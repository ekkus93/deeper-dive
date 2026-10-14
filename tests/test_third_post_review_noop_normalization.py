"""TPR-13: equivalent configuration spellings are no-ops that preserve the plan."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest
from test_episode_planner import _service

from deeper_dive.episode_config import EpisodeConfiguration

Variant = Callable[[EpisodeConfiguration], EpisodeConfiguration]

NOOP_VARIANTS: dict[str, Variant] = {
    "title whitespace": lambda c: replace(c, title=f"  {c.title}\t"),
    "focus none-like blank": lambda c: replace(c, focus="   "),
    "host list not tuple": lambda c: replace(c, host_ids=list(c.host_ids)),  # type: ignore[arg-type]
    "host id whitespace": lambda c: replace(c, host_ids=tuple(f" {h} " for h in c.host_ids)),
    "blank must_cover entries": lambda c: replace(c, must_cover=("", "  ")),
    "blank research override": lambda c: replace(c, research_overrides={"policy": None}),
}

REAL_CHANGES: dict[str, Variant] = {
    "title": lambda c: replace(c, title="Different"),
    "duration": lambda c: replace(c, target_duration_seconds=c.target_duration_seconds + 60),
    "host order": lambda c: replace(c, host_ids=tuple(reversed(c.host_ids))),
    "must cover": lambda c: replace(c, must_cover=("something",)),
}


@pytest.mark.parametrize("name", sorted(NOOP_VARIANTS))
def test_equivalent_spellings_preserve_the_plan(tmp_path, name: str) -> None:
    service, episode_id, _ = _service(tmp_path)
    plan = service.build_plan(episode_id)
    configurations = service.configurations
    current = configurations.load_configuration(episode_id)
    before = service.repository.get_episode(episode_id)

    configurations.edit(episode_id, NOOP_VARIANTS[name](current))

    assert service.repository.get_episode(episode_id) == before
    assert service.load_plan(episode_id) == plan


@pytest.mark.parametrize("name", sorted(REAL_CHANGES))
def test_real_changes_still_invalidate_the_plan(tmp_path, name: str) -> None:
    service, episode_id, _ = _service(tmp_path)
    service.build_plan(episode_id)
    configurations = service.configurations
    current = configurations.load_configuration(episode_id)

    configurations.edit(episode_id, REAL_CHANGES[name](current))

    with service.database.connection() as db:
        plans = db.execute(
            "SELECT COUNT(*) FROM episode_plans WHERE episode_id=?", (episode_id,)
        ).fetchone()[0]
    assert plans == 0


def test_stored_title_is_canonical_after_a_whitespace_create(tmp_path) -> None:
    service, episode_id, _ = _service(tmp_path)
    created = service.configurations.create(
        "p1",
        EpisodeConfiguration(title="  Padded  ", host_ids=("h1", "h2")),
    )
    assert created.title == "Padded"
    assert service.repository.get_episode(created.id).title == "Padded"  # type: ignore[union-attr]
