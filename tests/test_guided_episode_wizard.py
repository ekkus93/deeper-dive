"""Guided episode, plan, preflight, and generation-start acceptance."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from textual.pilot import Pilot
from textual.widgets import Button, Input, Select, Static

from deeper_dive import cli as cli_module
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_generation import GuidedGenerationMonitorScreen
from deeper_dive.guided_ready import GuidedEpisodeReadyScreen
from deeper_dive.llm import LLMResponse
from deeper_dive.model_roles import ModelRole
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _service_and_config(tmp_path: Path) -> DeeperDiveService:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "fake": ProviderConfig(
                    provider_type="fake",
                    default_model="fake-v1",
                    network_scope="local",
                ),
                "speech": ProviderConfig(
                    provider_type="fake-tts",
                    network_scope="local",
                    voices=("voice-a", "voice-b"),
                ),
            },
            defaults={
                ModelRole.EPISODE_PLANNING.value: "fake:fake-v1",
                ModelRole.HOST_GENERATION.value: "fake:fake-v1",
                ModelRole.DIRECTING.value: "fake:fake-v1",
                ModelRole.VERIFICATION.value: "fake:fake-v1",
                "speech_setup": "configured",
                "tts_provider": "speech",
                "tts_voice": "voice-a",
                "tts_voice_host_1": "voice-a",
                "tts_voice_host_2": "voice-b",
                "quick_deep_dive_duration_minutes": "20",
                "research_policy": "useful",
            },
        )
    )
    return DeeperDiveService(WorkspaceManager(data_dir))


def test_guided_episode_plan_preflight_and_generation_start(tmp_path: Path) -> None:
    asyncio.run(_episode_plan_preflight_and_generation_start(tmp_path))


async def _episode_plan_preflight_and_generation_start(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedEpisodeWizard)

        screen.query_one("#guided-project-name", Input).value = "Oceans"
        screen.query_one("#guided-project-topic", Input).value = "How do oceans store heat?"
        screen.query_one("#guided-project-audience", Select).value = "technical"
        screen.action_create_project()
        project_id = screen.context.project_id
        assert project_id is not None
        screen.action_continue()

        screen.query_one("#guided-source-title", Input).value = "Notes"
        screen.query_one("#guided-source-text", Input).value = "Oceans store and move heat."
        for button in screen.query("Button"):
            if button.name == "add-source":
                button.press()
                break
        await pilot.pause()
        screen.action_continue()

        screen.query_one("#guided-research-policy", Select).value = "useful"
        screen.action_save_research()
        screen.action_continue()

        screen.action_create_recommended_hosts()
        screen.action_save_host_order()
        episode_id = screen.context.episode_id
        assert episode_id is not None
        screen.action_continue()
        assert screen.context.state.current_step == "episode"

        screen.query_one("#guided-episode-title", Input).value = "Ocean Heat"
        screen.query_one("#guided-episode-focus", Input).value = "Where does the heat go?"
        screen.query_one("#guided-episode-duration", Select).value = "10"
        screen.query_one("#guided-episode-audience", Select).value = "technical"
        screen.query_one("#guided-episode-depth", Select).value = "deep"
        screen.query_one("#guided-episode-must-cover", Input).value = "circulation, storage"
        screen.query_one("#guided-episode-avoid", Input).value = "speculation"
        screen.action_save_episode()

        saved = EpisodeConfigurationService(
            app.composition.database_for_project(project_id)
        ).load_configuration(episode_id)
        assert saved.title == "Ocean Heat"
        assert saved.focus == "Where does the heat go?"
        assert saved.target_duration_seconds == 600
        assert saved.must_cover == ("circulation", "storage")
        assert saved.avoid_topics == ("speculation",)

        screen.action_continue()
        assert screen.context.state.current_step == "plan"
        screen.action_build_plan()
        assert screen._plan is not None
        assert screen._plan.target_duration_seconds == 600
        assert "Overview" in str(screen.query_one("#guided-plan-summary", Static).render())

        screen.action_continue()
        assert screen.context.state.current_step == "preflight"
        with patch("deeper_dive.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            screen.action_check_preflight()
            assert screen._preflight is not None
            assert screen._preflight.ready
            assert "Sources: Ready" in str(
                screen.query_one("#guided-preflight-summary", Static).render()
            )
            screen.action_generate_deep_dive()
        await pilot.pause()
        assert isinstance(app.screen, GuidedGenerationMonitorScreen)

        assert screen.context.run_id is not None
        run = service.runs(project_id).get(screen.context.run_id)
        assert run is not None
        assert run.episode_id == episode_id
        assert run.state == "pending"


def test_guided_episode_validation_preserves_typed_input(tmp_path: Path) -> None:
    asyncio.run(_episode_validation_preserves_typed_input(tmp_path))


async def _episode_validation_preserves_typed_input(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedEpisodeWizard)
        screen.context.state = screen.context.state.moved_to("episode")
        screen._toggle()
        assert screen.query_one("#guided-episode-depth", Select).display is False
        screen.action_toggle_episode_advanced()
        assert screen.query_one("#guided-episode-depth", Select).display is True
        assert screen.query_one("#guided-episode-must-cover", Input).display is True
        assert screen.query_one("#guided-episode-avoid", Input).display is True
        screen.query_one("#guided-episode-title", Input).value = "Typed title"
        screen.query_one("#guided-episode-focus", Input).value = "Typed focus"
        screen.query_one("#guided-episode-duration", Select).value = "custom"
        screen.query_one("#guided-episode-custom-duration", Input).value = "bad"
        screen.action_save_episode()
        assert screen.query_one("#guided-episode-title", Input).value == "Typed title"
        assert screen.query_one("#guided-episode-focus", Input).value == "Typed focus"


async def _prepare_to_plan(
    screen: GuidedEpisodeWizard,
    pilot: Pilot[None],
) -> tuple[str, str]:
    screen.query_one("#guided-project-name", Input).value = "Regression"
    screen.query_one("#guided-project-topic", Input).value = "What should we understand?"
    screen.action_create_project()
    project_id = screen.context.project_id
    assert project_id is not None
    screen.action_continue()

    screen.query_one("#guided-source-title", Input).value = "Notes"
    screen.query_one("#guided-source-text", Input).value = "Evidence for the regression."
    for button in screen.query(Button):
        if button.name == "add-source":
            button.press()
            break
    await pilot.pause()
    screen.action_continue()

    screen.query_one("#guided-research-policy", Select).value = "useful"
    screen.action_save_research()
    screen.action_continue()

    screen.action_create_recommended_hosts()
    screen.action_save_host_order()
    episode_id = screen.context.episode_id
    assert episode_id is not None
    screen.action_continue()

    screen.query_one("#guided-episode-title", Input).value = "Regression Episode"
    screen.query_one("#guided-episode-focus", Input).value = "Explain the evidence"
    screen.query_one("#guided-episode-duration", Select).value = "10"
    screen.action_save_episode()
    screen.action_continue()
    assert screen.context.state.current_step == "plan"
    return project_id, episode_id


def test_guided_planner_invalid_output_is_actionable_and_retryable(tmp_path: Path) -> None:
    asyncio.run(_planner_invalid_output_is_actionable_and_retryable(tmp_path))


async def _planner_invalid_output_is_actionable_and_retryable(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedEpisodeWizard)
        await _prepare_to_plan(screen, pilot)

        provider = app.composition.provider_controller.llm("fake")
        with patch.object(
            provider,
            "generate",
            return_value=LLMResponse('{"segments":[]}', "fake-v1"),
        ):
            screen.action_build_plan()

        assert screen._plan is None
        status = str(screen.query_one("#wizard-status", Static).render())
        assert "Episode planning failed" in status
        assert "non-empty segments list" in status
        assert screen.context.state.current_step == "plan"

        screen.action_build_plan()
        assert screen._plan is not None
        assert screen.query_one("#wizard-continue", Button).disabled is False


def test_guided_invalid_persisted_plan_blocks_continue(tmp_path: Path) -> None:
    asyncio.run(_invalid_persisted_plan_blocks_continue(tmp_path))


async def _invalid_persisted_plan_blocks_continue(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedEpisodeWizard)
        project_id, _episode_id = await _prepare_to_plan(screen, pilot)
        screen.action_build_plan()
        assert screen._plan is not None

        database = app.composition.database_for_project(project_id)
        with database.transaction() as connection:
            connection.execute(
                "UPDATE segment_plans SET target_duration_seconds=0 "
                "WHERE episode_plan_id=(SELECT id FROM episode_plans LIMIT 1)"
            )

        screen._sync_text()
        assert screen.query_one("#wizard-continue", Button).disabled is True
        screen.action_continue()
        assert screen.context.state.current_step == "plan"


def test_guided_post_start_plan_mutation_is_rejected(tmp_path: Path) -> None:
    asyncio.run(_post_start_plan_mutation_is_rejected(tmp_path))


async def _post_start_plan_mutation_is_rejected(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedEpisodeWizard)
        _project_id, _episode_id = await _prepare_to_plan(screen, pilot)
        screen.action_build_plan()
        assert screen._plan is not None
        original_plan_id = screen._plan.id

        screen.action_continue()
        with patch("deeper_dive.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            screen.action_check_preflight()
            assert screen._preflight is not None and screen._preflight.ready
            screen.action_generate_deep_dive()
        await pilot.pause()
        assert screen.context.run_id is not None

        screen.action_back()
        assert screen.context.state.current_step == "plan"
        screen.action_regenerate_plan()

        status = str(screen.query_one("#wizard-status", Static).render())
        assert "frozen" in status.lower()
        assert screen._plan is not None
        assert screen._plan.id == original_plan_id


def test_guided_and_cli_preflight_report_same_blocker(
    tmp_path: Path,
    capsys,
) -> None:
    asyncio.run(_guided_and_cli_preflight_report_same_blocker(tmp_path, capsys))


async def _guided_and_cli_preflight_report_same_blocker(tmp_path: Path, capsys) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedEpisodeWizard)
        project_id, episode_id = await _prepare_to_plan(screen, pilot)
        screen.action_build_plan()
        screen.action_continue()

        with patch("deeper_dive.ffmpeg.shutil.which", return_value=None):
            screen.action_check_preflight()
            assert screen._preflight is not None
            blockers = {issue.code: issue.message for issue in screen._preflight.blockers}
            assert "ffmpeg_unavailable" in blockers

            direct = GenerationStartService(app.composition).preflight(project_id, episode_id)
            assert direct == screen._preflight
            screen.action_fix_preflight()
            await pilot.pause()
            assert app.screen.id == "screen-wizard-first-run"

    with (
        patch("deeper_dive.ffmpeg.shutil.which", return_value=None),
        patch.object(
            cli_module.ProductionComposition,
            "build",
            return_value=app.composition,
        ),
    ):
        code = cli_module.main(
            [
                "--data-dir",
                str(service.workspaces.data_dir),
                "episode",
                "generate",
                project_id,
                episode_id,
            ]
        )

    assert code == 2
    captured = capsys.readouterr()
    assert blockers["ffmpeg_unavailable"] in captured.err


def test_guided_generate_opens_production_monitor_and_confirmed_cancel(
    tmp_path: Path,
) -> None:
    asyncio.run(_guided_generate_opens_production_monitor(tmp_path))


async def _guided_generate_opens_production_monitor(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    # Keep this test deterministic: run creation must be durable, but a
    # live executor is neither needed nor started in this focused test.
    app.generation_monitor_controller.runner = None
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        project_id, episode_id = await _prepare_to_plan(wizard, pilot)
        wizard.action_build_plan()
        wizard.action_continue()
        with patch("deeper_dive.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            wizard.action_check_preflight()
            assert wizard._preflight is not None and wizard._preflight.ready
            wizard.action_generate_deep_dive()
        await pilot.pause()
        assert isinstance(app.screen, GuidedGenerationMonitorScreen)
        monitor = app.screen
        run_id = wizard.context.run_id
        assert run_id is not None
        assert app.current_project_id == project_id
        assert app.current_episode_id == episode_id
        assert app.current_run_id == run_id
        assert "elapsed" in str(monitor.query_one("#generation-state", Static).render())
        monitor.action_cancel()
        before = service.runs(project_id).get(run_id)
        assert before is not None and not before.cancel_requested
        monitor.action_cancel()
        after = service.runs(project_id).get(run_id)
        assert after is not None and after.cancel_requested


def test_guided_completed_run_shows_episode_ready_and_routes_to_library(tmp_path: Path) -> None:
    asyncio.run(_guided_completed_run_shows_episode_ready(tmp_path))


async def _guided_completed_run_shows_episode_ready(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    app.generation_monitor_controller.runner = None
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        project_id, episode_id = await _prepare_to_plan(wizard, pilot)
        wizard.action_build_plan()
        wizard.action_continue()
        with patch("deeper_dive.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            wizard.action_check_preflight()
            wizard.action_generate_deep_dive()
        await pilot.pause()
        run_id = wizard.context.run_id
        assert run_id is not None
        repository = service.runs(project_id)
        run = repository.get(run_id)
        assert run is not None
        repository.update(replace(run, state="completed"))
        app.action_navigate("ready")
        await pilot.pause()
        ready = app.screen
        assert isinstance(ready, GuidedEpisodeReadyScreen)
        summary = str(ready.query_one("#ready-summary", Static).render())
        assert "Regression Episode" in summary
        assert "Generation status: completed" in summary
        ready.query_one("#ready-library", Button).press()
        await pilot.pause()
        assert app.screen.id == "screen-library"
        assert app.screen.selected_episode_id == episode_id


def test_guided_hosts_reorder_edit_and_restart_from_production_state(tmp_path: Path) -> None:
    asyncio.run(_guided_hosts_reorder_edit_and_restart(tmp_path))


async def _guided_hosts_reorder_edit_and_restart(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedEpisodeWizard)
        project_id, episode_id = await _prepare_to_plan(screen, pilot)
        original_ids = EpisodeConfigurationService(
            app.composition.database_for_project(project_id)
        ).load_configuration(episode_id).host_ids
        assert len(original_ids) == 2
        screen.context.state = screen.context.state.moved_to("hosts")
        screen._toggle()
        picker = screen.query_one("#guided-host-picker", Select)
        picker.value = original_ids[1]
        await pilot.pause()
        screen._move_selected_host(-1)
        screen.action_save_host_order()
        saved = EpisodeConfigurationService(
            app.composition.database_for_project(project_id)
        ).load_configuration(episode_id)
        assert saved.host_ids == (original_ids[1], original_ids[0])

        screen.query_one("#guided-host-name", Input).value = "Reordered Evidence Host"
        screen.action_save_host()
        updated = service.hosts(project_id).get_host(original_ids[1])
        assert updated is not None
        assert updated.display_name == "Reordered Evidence Host"
        order = str(screen.query_one("#guided-host-order", Static).render())
        assert "Reordered Evidence Host" in order
        assert original_ids[1] not in order

        screen.action_save_exit()
        await pilot.pause()
        assert app.screen.id == "screen-home"

    restarted = GuidedDeeperDiveApp(service)
    async with restarted.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        restarted.screen.query_one("#action-resume-deep-dive", Button).press()
        await pilot.pause()
        wizard = restarted.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        assert wizard.context.project_id == project_id
        assert wizard.context.episode_id == episode_id
        assert wizard._selected_host_ids == [original_ids[1], original_ids[0]]
        assert "Reordered Evidence Host" in str(
            wizard.query_one("#guided-host-order", Static).render()
        )
