"""Production Textual editing cannot rewrite a generated episode or exported media."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from textual.widgets import Input, Static

from deeper_dive.cli import main
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.database import Database


def test_completed_episode_tui_edit_requires_new_episode_without_mutating_artifacts(
    second_post_review_acceptance: Callable[[], Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    asyncio.run(_completed_episode_tui_edit_requires_new_episode(second_post_review_acceptance, capsys))


async def _completed_episode_tui_edit_requires_new_episode(
    second_post_review_acceptance: Callable[[], Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = second_post_review_acceptance()
    first = fixture.completed.first
    second = fixture.completed.second
    service = first.service
    repository = service.hosts(first.project_id)
    other_repository = service.hosts(second.project_id)
    configuration = EpisodeConfigurationService(
        Database(service.workspaces.project_root(first.project_id) / "project.db")
    )
    original_config = configuration.load_configuration(first.episode_id)
    original_episode = repository.get_episode(first.episode_id)
    original_plan = repository.get_plan(first.episode_id)
    original_run = service.runs(first.project_id).get(first.run_id)
    original_other = other_repository.get_episode(second.episode_id)
    assert original_episode is not None and original_episode.state == "completed"
    assert original_plan is not None
    assert original_run is not None and original_run.state == "completed"
    assert original_other is not None
    paths = (
        first.transcript_path,
        first.audio_path,
        first.manifest_path,
        first.metadata_path,
    )
    original_artifacts = tuple(path.read_bytes() for path in paths)

    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = first.project_id
        wizard.context.episode_id = first.episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "episode")
        wizard._load_episode_host_order()
        wizard._load_episode_form()
        wizard._toggle()
        wizard._remember_current_form()

        title_field = wizard.query_one("#guided-episode-title", Input)
        title_field.value = "Must create a new episode"
        assert not wizard.action_save_episode()
        validation = str(wizard.query_one("#guided-episode-validation", Static).render())
        assert "create a new episode" in validation
        assert title_field.value == "Must create a new episode"
        assert wizard._current_form_dirty()

    # The shared CLI service must reject the same edit and leave the durable
    # completed-episode identity untouched.
    assert main(
        [
            "--data-dir",
            str(service.workspaces.data_dir),
            "episode",
            "configure",
            first.project_id,
            first.episode_id,
            "--title",
            "Must create a separate CLI episode",
        ]
    ) == 2
    captured = capsys.readouterr()
    assert "create a new episode" in captured.err
    assert "Must create a separate CLI episode" not in captured.err

    assert configuration.load_configuration(first.episode_id) == original_config
    assert repository.get_episode(first.episode_id) == original_episode
    assert repository.get_plan(first.episode_id) == original_plan
    assert service.runs(first.project_id).get(first.run_id) == original_run
    assert other_repository.get_episode(second.episode_id) == original_other
    assert tuple(path.read_bytes() for path in paths) == original_artifacts
