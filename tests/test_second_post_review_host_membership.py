"""Host-order membership validation at shared service and guided TUI boundaries."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.hosts import HostProfile, create_host_from_preset
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    HostEpisodeRepository,
    SegmentPlanRecord,
)
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.fixture
def mixed_project_episode(tmp_path):
    """Keep distinct project identities in one database to test adversarial membership."""
    db = Database(tmp_path / "project.db")
    corpus = CorpusRepository(db)
    for project_id in ("project-a", "project-b"):
        corpus.create_project(ProjectRecord(project_id, project_id, "now", "now"))
    hosts = HostEpisodeRepository(db)
    for host_id, owner in (
        ("host-a", "project-a"),
        ("host-b", "project-a"),
        ("foreign", "project-b"),
    ):
        hosts.create_host(create_host_from_preset("skeptic", owner, host_id=host_id).to_record())
    service = EpisodeConfigurationService(db)
    first = service.create(
        "project-a", EpisodeConfiguration(title="Original", host_ids=("host-a", "host-b"))
    )
    second = service.create(
        "project-a", EpisodeConfiguration(title="Independent", host_ids=("host-b",))
    )
    hosts.save_plan(
        EpisodePlanRecord(id="plan-a", episode_id=first.id, created_at="now", modified_at="now"),
        [
            SegmentPlanRecord(
                id="segment-a",
                episode_plan_id="plan-a",
                ordinal=0,
                title="Opening",
            )
        ],
    )
    return service, hosts, first.id, second.id


@pytest.mark.parametrize(
    "bad_ids",
    (
        ("host-a", "host-a"),
        ("host-a", "does-not-exist"),
        ("host-a", "foreign"),
    ),
)
def test_rejected_host_order_edit_preserves_episode_plan_and_other_episode(
    mixed_project_episode, bad_ids
) -> None:
    service, hosts, first_id, second_id = mixed_project_episode
    original_first = hosts.get_episode(first_id)
    original_second = hosts.get_episode(second_id)
    original_first_config = service.load_configuration(first_id)
    original_second_config = service.load_configuration(second_id)
    original_plan = hosts.get_plan(first_id)
    assert original_first is not None and original_second is not None
    assert original_plan is not None

    with pytest.raises(ValueError, match="duplicate hosts|does not belong to project"):
        service.edit(first_id, replace(original_first_config, host_ids=bad_ids))

    assert hosts.get_episode(first_id) == original_first
    assert hosts.get_episode(second_id) == original_second
    assert service.load_configuration(first_id) == original_first_config
    assert service.load_configuration(second_id) == original_second_config
    assert hosts.get_plan(first_id) == original_plan
    assert [item.id for item in hosts.list_segments(original_plan.id)] == ["segment-a"]


@pytest.mark.parametrize(
    "bad_ids",
    (
        ("host-a", "host-a"),
        ("host-a", "does-not-exist"),
        ("host-a", "foreign"),
    ),
)
def test_rejected_host_order_create_does_not_insert_episode(mixed_project_episode, bad_ids) -> None:
    service, hosts, first_id, second_id = mixed_project_episode
    baseline = [item.id for item in hosts.list_episodes("project-a")]

    with pytest.raises(ValueError, match="duplicate hosts|does not belong to project"):
        service.create("project-a", EpisodeConfiguration(title="Invalid", host_ids=bad_ids))

    assert [item.id for item in hosts.list_episodes("project-a")] == baseline
    assert set(baseline) == {first_id, second_id}


def test_valid_host_order_rehydrates_from_new_service_instance(mixed_project_episode) -> None:
    service, hosts, first_id, second_id = mixed_project_episode
    updated = replace(service.load_configuration(first_id), host_ids=("host-b", "host-a"))
    service.edit(first_id, updated)
    restarted = EpisodeConfigurationService(service.database)

    assert restarted.load_configuration(first_id).host_ids == ("host-b", "host-a")
    assert restarted.load_configuration(second_id).host_ids == ("host-b",)
    assert hosts.list_episode_host_ids(first_id) == ["host-b", "host-a"]


def test_guided_rejected_missing_host_keeps_pending_order_and_durable_episode(
    tmp_path,
) -> None:
    asyncio.run(_guided_rejected_missing_host_preserves_edits(tmp_path))


async def _guided_rejected_missing_host_preserves_edits(tmp_path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Host order rejection")
    host_repo = service.hosts(project.id)
    host_repo.create_host(HostProfile("present", project.id, "Available").to_record())
    db = Database(service.workspaces.project_root(project.id) / "project.db")
    configs = EpisodeConfigurationService(db)
    episode = configs.create(
        project.id, EpisodeConfiguration(title="Existing", host_ids=("present",))
    )

    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.episode_id = episode.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "hosts")
        wizard._load_episode_host_order()
        wizard._refresh_hosts("present")
        wizard._toggle()
        wizard._remember_current_form()
        wizard._selected_host_ids.append("missing")
        wizard._refresh_host_order()

        assert wizard._host_order_dirty()
        assert wizard.action_save_host_order() is False
        assert wizard._selected_host_ids == ["present", "missing"]
        assert wizard._host_order_dirty()
        assert configs.load_configuration(episode.id).host_ids == ("present",)
