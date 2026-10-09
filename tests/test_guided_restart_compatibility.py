"""Restart compatibility of guided navigation with existing durable configuration."""

from __future__ import annotations

import asyncio
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.model_roles import ModelRole
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_guided_home_reopens_persisted_project_and_provider_after_restart(
    tmp_path: Path,
) -> None:
    asyncio.run(_reopen_existing_project_and_provider(tmp_path))


async def _reopen_existing_project_and_provider(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    defaults = {
        role.value: "legacy:fake-v1"
        for role in (
            ModelRole.EPISODE_PLANNING,
            ModelRole.HOST_GENERATION,
            ModelRole.DIRECTING,
            ModelRole.VERIFICATION,
        )
    }
    defaults.update(
        {
            "speech_setup": "deferred",
            "quick_deep_dive_duration_minutes": "20",
            "research_policy": "useful",
        }
    )
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "legacy": ProviderConfig(
                    provider_type="fake",
                    default_model="fake-v1",
                    network_scope="local",
                )
            },
            defaults=defaults,
        )
    )
    service = DeeperDiveService(WorkspaceManager(data_dir))
    project = service.create_project("Persisted legacy project")

    # The second process must use disk-backed data, not the original service.
    restarted = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(data_dir)))
    async with restarted.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert restarted.screen.id == "screen-home"
        assert (
            restarted.provider_controller.config().providers["legacy"].provider_type
            == "fake"
        )
        assert "Persisted legacy project" in str(
            restarted.screen.query_one("#home-recent-projects").render()
        )
        restarted.current_project_id = project.id
        restarted.action_navigate("library")
        await pilot.pause()
        assert restarted.screen.id == "screen-library"
        restarted.action_navigate("home")
        await pilot.pause()
        assert "Persisted legacy project" in str(
            restarted.screen.query_one("#home-recent-projects").render()
        )
