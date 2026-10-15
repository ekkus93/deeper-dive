"""6PR-08: model-override robustness and a repair path for unusable stored overrides."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from guided_pilot import click, continue_step, reach_hosts, type_into
from test_episode_planner import _service
from test_fifth_post_review_model_overrides import _store_raw_overrides
from test_fifth_post_review_stopping_run import _cancel  # noqa: F401  (shared helpers)
from test_fifth_post_review_stored_values_preserved import _app, _save_and_exit
from test_generation_start import _episode
from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.cli import main
from deeper_dive.episode_config import EpisodeConfiguration
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_errors import InvalidModelOverrides
from deeper_dive.storage.workspace import WorkspaceManager

VALID = {"episode_planning": {"provider": "fake", "model": "fake-v1"}}


class _Stub:
    current_episode_id = "e1"
    _override_notice = ""

    def __init__(self, config: EpisodeConfiguration) -> None:
        self._config = config

    def _configuration_service(self, _project_id: str):  # type: ignore[no-untyped-def]
        config = self._config

        class Service:
            def load_configuration(self, _episode_id: str) -> EpisodeConfiguration:
                return config

        return Service()


def test_setup_screen_keeps_valid_overrides_when_another_field_is_invalid() -> None:
    config = EpisodeConfiguration(
        title="T",
        model_overrides=dict(VALID),
        source_overrides={"s1": 1},  # type: ignore[dict-item]
    )
    stub = _Stub(config)
    assert EpisodeSetupScreen._existing_model_overrides(stub, "p1") == VALID  # type: ignore[arg-type]
    assert stub._override_notice == ""


def test_setup_screen_tells_the_user_which_override_was_dropped() -> None:
    config = EpisodeConfiguration(title="T", model_overrides={"episode_planning": "no-colon"})
    stub = _Stub(config)
    assert EpisodeSetupScreen._existing_model_overrides(stub, "p1") == {}  # type: ignore[arg-type]
    assert "episode_planning" in stub._override_notice


def test_null_stored_overrides_mean_none_and_other_shapes_are_typed_errors(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service, episode_id, _ = _service(tmp_path)
    configurations = service.configurations

    _store_raw_overrides(service, episode_id, None)
    assert configurations.load_configuration(episode_id).model_overrides == {}

    _store_raw_overrides(service, episode_id, "episode_planning=fake:fake-v1")
    with pytest.raises(InvalidModelOverrides, match="--clear-model-overrides") as raised:
        configurations.load_configuration(episode_id)
    assert isinstance(raised.value, ValueError)
    assert (
        configurations.load_configuration(
            episode_id, drop_invalid_model_overrides=True
        ).model_overrides
        == {}
    )


def test_invalid_override_shape_raises_the_typed_error_naming_the_role() -> None:
    config = EpisodeConfiguration(title="T", model_overrides={"episode_planning": 3})  # type: ignore[dict-item]
    with pytest.raises(InvalidModelOverrides, match="episode_planning"):
        config.normalized()


def test_describe_names_the_real_project_and_episode() -> None:
    text = InvalidModelOverrides("bad").describe("proj-1", "ep-2")
    assert "episode configure proj-1 ep-2 --clear-model-overrides" in text


def _store_raw_in_project(service, project_id: str, episode_id: str, overrides: object) -> None:  # type: ignore[no-untyped-def]
    database = Database(service.workspaces.project_root(project_id) / "project.db")
    with database.transaction() as db:
        row = db.execute("SELECT config_json FROM episodes WHERE id=?", (episode_id,)).fetchone()
        payload = json.loads(row["config_json"])
        payload["model_overrides"] = overrides
        db.execute(
            "UPDATE episodes SET config_json=? WHERE id=?",
            (json.dumps(payload, sort_keys=True), episode_id),
        )


@pytest.mark.parametrize("bad", ["episode_planning=fake", {"episode_planning": "no-colon"}])
def test_cli_configure_reports_the_repair_command_and_clear_repairs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], bad: object
) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    _store_raw_in_project(service, project_id, episode_id, bad)
    base = ["--data-dir", str(tmp_path / "data"), "episode", "configure", project_id, episode_id]

    assert main([*base, "--title", "Renamed", "--duration", "600"]) == 2
    err = capsys.readouterr().err
    assert f"episode configure {project_id} {episode_id} --clear-model-overrides" in err

    code = main([*base, "--title", "Renamed", "--duration", "600", "--clear-model-overrides"])
    assert code == 0, capsys.readouterr().err
    capsys.readouterr()
    assert (
        main(
            [
                "--data-dir",
                str(tmp_path / "data"),
                "--json",
                "episode",
                "show",
                project_id,
                episode_id,
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert "Renamed" in json.dumps(shown)
    assert shown["configuration"]["model_overrides"] == {}


def test_guided_save_names_the_repair_command(tmp_path: Path) -> None:
    asyncio.run(_guided(tmp_path))


async def _guided(tmp_path: Path) -> None:
    data = tmp_path / "data"
    first = _app(data)
    async with first.run_test(size=(100, 45)) as pilot:
        await reach_hosts(pilot)
        wizard = first.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        await click(pilot, "#guided-host-recommended")
        await click(pilot, "#guided-host-order-save")
        await click(pilot, "#guided-host-down")
        episode_id = wizard.context.episode_id
        project_id = wizard.context.project_id
        assert episode_id is not None and project_id is not None
        await _save_and_exit(pilot, wizard)

    service = DeeperDiveService(WorkspaceManager(data))
    _store_raw_in_project(service, project_id, episode_id, {"episode_planning": "no-colon"})

    second = _app(data)
    async with second.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        second.action_navigate("resume")
        await pilot.pause()
        await pilot.pause()
        resumed = second.screen
        assert isinstance(resumed, GuidedEpisodeWizard)
        await continue_step(pilot, "episode")
        await type_into(pilot, "#guided-episode-title", "T2")
        await type_into(pilot, "#guided-episode-focus", "A focus question")
        await click(pilot, "#guided-episode-save")
        message = str(resumed.query_one("#guided-episode-validation", Static).render())
        assert f"episode configure {project_id} {episode_id} --clear-model-overrides" in message
