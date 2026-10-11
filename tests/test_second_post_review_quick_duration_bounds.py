"""Storage-safe and nonleaking Quick duration validation at both config boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import MAX_QUICK_DURATION_MINUTES, UserConfig


def test_quick_duration_just_inside_storage_bound_is_accepted() -> None:
    config = UserConfig(
        defaults={"quick_deep_dive_duration_minutes": str(MAX_QUICK_DURATION_MINUTES)}
    )
    assert int(config.defaults["quick_deep_dive_duration_minutes"]) * 60 <= (1 << 63) - 1


def test_overflowing_global_quick_duration_is_rejected_before_storage() -> None:
    with pytest.raises(ValueError, match="supported storage range"):
        UserConfig(
            defaults={"quick_deep_dive_duration_minutes": str(MAX_QUICK_DURATION_MINUTES + 1)}
        )


@pytest.mark.parametrize(
    ("duration", "message"),
    (
        (str(MAX_QUICK_DURATION_MINUTES + 1), "supported storage range"),
        ("do-not-echo-secret-canary", "positive integer"),
    ),
)
def test_bad_project_quick_duration_cannot_create_hosts_or_episode(
    tmp_path: Path, duration: str, message: str
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project(
        "Quick duration guard",
        instructions=json.dumps({"quick_deep_dive": {"duration_minutes": duration}}),
    )
    repository = service.hosts(project.id)
    with pytest.raises(ValueError, match=message) as error:
        service.quick_deep_dive(project.id)

    assert "do-not-echo-secret-canary" not in str(error.value)
    assert repository.list_hosts(project.id) == []
    assert repository.list_episodes(project.id) == []
