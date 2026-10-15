"""TPR-12: the guided episode save is guarded by the loaded revision, not just a pre-check."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from guided_episode_support import _prepare_to_plan, _service_and_config
from textual.widgets import Input, Static

from deeper_dive.episode_config import (
    EpisodeConfigurationConflict,
    EpisodeConfigurationService,
)
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard


def test_service_edit_rejects_a_stale_expected_revision(tmp_path: Path) -> None:
    asyncio.run(_service_level(tmp_path))


async def _service_level(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        project_id, episode_id = await _prepare_to_plan(wizard, pilot)
        episodes = EpisodeConfigurationService(app.composition.database_for_project(project_id))
        loaded, revision = episodes.load_with_revision(episode_id)
        episodes.edit(episode_id, replace(loaded, title="Interloper"))
        with pytest.raises(EpisodeConfigurationConflict):
            episodes.edit(
                episode_id, replace(loaded, title="Stale writer"), expected_revision=revision
            )
        assert episodes.load_configuration(episode_id).title == "Interloper"


def test_guided_save_does_not_overwrite_an_edit_that_lands_after_its_precheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(_guided_window(tmp_path, monkeypatch))


async def _guided_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        project_id, episode_id = await _prepare_to_plan(wizard, pilot)
        wizard.context.state = wizard.context.state.moved_to("episode")
        wizard._toggle()
        wizard.query_one("#guided-episode-title", Input).value = "Guided title"
        wizard.query_one("#guided-episode-focus", Input).value = "Guided focus"

        real_load = EpisodeConfigurationService.load_configuration
        fired = {"done": False}

        def load_then_interlope(self, requested_id):
            config = real_load(self, requested_id)
            if not fired["done"]:
                fired["done"] = True
                # The wizard's pre-check just passed; another surface edits now.
                self.edit(requested_id, replace(config, title="CLI edit"))
            return config

        monkeypatch.setattr(EpisodeConfigurationService, "load_configuration", load_then_interlope)
        assert wizard.action_save_episode() is False
        monkeypatch.setattr(EpisodeConfigurationService, "load_configuration", real_load)

        assert "Fix episode settings" in str(
            wizard.query_one("#guided-episode-validation", Static).render()
        )
        assert wizard.query_one("#guided-episode-title", Input).value == "Guided title"
        durable = EpisodeConfigurationService(
            app.composition.database_for_project(project_id)
        ).load_configuration(episode_id)
        assert durable.title == "CLI edit"
