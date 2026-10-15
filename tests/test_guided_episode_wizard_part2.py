"""Guided episode, plan, preflight, and generation-start acceptance."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from guided_episode_support import _prepare_to_plan, _service_and_config
from textual.widgets import Button, Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_library_screen import EpisodeLibraryController
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_draft import GuidedDraftStore
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_generation import GuidedGenerationMonitorScreen
from deeper_dive.guided_ready import GuidedEpisodeReadyScreen
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController


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
        original_ids = (
            EpisodeConfigurationService(app.composition.database_for_project(project_id))
            .load_configuration(episode_id)
            .host_ids
        )
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

        # Single-host selection remains valid and durable; re-add through
        # the friendly host picker without entering comma-separated raw IDs.
        picker.value = original_ids[0]
        await pilot.pause()
        screen.action_remove_selected_host()
        screen.action_save_host_order()
        single = EpisodeConfigurationService(
            app.composition.database_for_project(project_id)
        ).load_configuration(episode_id)
        assert single.host_ids == (original_ids[1],)
        screen.action_select_host()
        screen.action_save_host_order()

        picker.value = original_ids[1]
        await pilot.pause()
        screen.action_preview_host_voice()
        assert "Previewed" in str(screen.query_one("#wizard-status", Static).render())
        assert any((service.workspaces.data_dir / "voice-previews").iterdir())

        screen.query_one("#guided-host-name", Input).value = "Custom Evidence Host"
        # Creating a new host now confirms how to handle edits to the selected
        # existing profile before replacing the form with a new host.
        assert not screen.action_create_host()
        assert screen.query_one("#wizard-exit-confirmation").display
        screen.action_confirm_save_exit()
        assert any(
            host.display_name == "Custom Evidence Host"
            for host in service.hosts(project_id).list_hosts(project_id)
        )
        # A successfully persisted host form is clean; no discard modal is needed.
        assert not screen._current_form_dirty()
        screen.action_save_exit()
        assert not screen.query_one("#wizard-exit-confirmation").display
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
        assert "Custom Evidence Host" in str(
            wizard.query_one("#guided-host-order", Static).render()
        )


def test_guided_and_quick_runs_produce_isolated_durable_artifacts(tmp_path: Path) -> None:
    asyncio.run(_guided_and_quick_runs_produce_isolated_durable_artifacts(tmp_path))


async def _guided_and_quick_runs_produce_isolated_durable_artifacts(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    # Exercise real pipeline execution explicitly after the normal wizard creates
    # a durable pending run, avoiding a racing background monitor in this fixture.
    app.generation_monitor_controller.runner = None
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        project_id, guided_episode_id = await _prepare_to_plan(wizard, pilot)
        wizard.action_build_plan()
        wizard.action_continue()
        with patch("deeper_dive.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            wizard.action_check_preflight()
            assert wizard._preflight is not None and wizard._preflight.ready
            wizard.action_generate_deep_dive()
        await pilot.pause()
        guided_run_id = wizard.context.run_id
        assert guided_run_id is not None
        assert service.runs(project_id).get(guided_run_id).state == "pending"

        app.composition.run_generation(project_id, guided_run_id)
        completed_guided = service.runs(project_id).get(guided_run_id)
        assert completed_guided is not None and completed_guided.state == "completed"
        # Normal monitor completion hands off to the guided Ready screen.
        monitor = app.screen
        assert isinstance(monitor, GuidedGenerationMonitorScreen)
        monitor._route_completed_run()
        await pilot.pause()
        ready = app.screen
        assert isinstance(ready, GuidedEpisodeReadyScreen)
        assert "Regression Episode" in str(ready.query_one("#ready-summary", Static).render())
        ready.query_one("#ready-export", Button).press()
        await pilot.pause()
        assert "Exported" in str(ready.query_one("#ready-status", Static).render())
        ready.query_one("#ready-library", Button).press()
        await pilot.pause()
        assert app.screen.id == "screen-library"
        assert app.screen.selected_episode_id == guided_episode_id

        quick_episode = service.quick_deep_dive(project_id)
        assert quick_episode.id != guided_episode_id
        planner = app.composition.configured_planning_service(project_id, "fake", "fake-v1")
        planner.build_plan(quick_episode.id)
        with patch("deeper_dive.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            quick_run = (
                GenerationStartService(app.composition).start(project_id, quick_episode.id).run
            )
        app.composition.run_generation(project_id, quick_run.id)
        completed_quick = service.runs(project_id).get(quick_run.id)
        assert completed_quick is not None and completed_quick.state == "completed"

        database = app.composition.database_for_project(project_id)
        artifacts: dict[str, tuple[str, Path]] = {}
        for episode_id, run_id in (
            (guided_episode_id, guided_run_id),
            (quick_episode.id, quick_run.id),
        ):
            app.current_project_id = project_id
            app.current_episode_id = episode_id
            app.current_run_id = run_id
            turns = TranscriptReviewController().turns(app)
            assert len(turns) > 0
            assert AudioTimelineRepository(database).get(episode_id) is not None
            audio = service.workspaces.project_root(project_id) / "output" / f"{episode_id}.wav"
            assert audio.is_file()
            item = next(
                item
                for item in EpisodeLibraryController.items(app)
                if item.episode.id == episode_id
            )
            assert item.run is not None and item.run.id == run_id
            exported = EpisodeLibraryController.export(app, item)
            assert all(path.is_file() for path in exported.paths)
            assert exported.audio is not None
            artifacts[episode_id] = (str(exported.transcript), exported.audio)

        first_export = artifacts[guided_episode_id]
        second_export = artifacts[quick_episode.id]
        assert first_export != second_export
        assert all(
            first != second for first, second in zip(first_export, second_export, strict=True)
        )


def test_new_deep_dive_restarts_at_each_guided_wizard_boundary(tmp_path: Path) -> None:
    asyncio.run(_new_deep_dive_restarts_at_each_guided_wizard_boundary(tmp_path))


async def _new_deep_dive_restarts_at_each_guided_wizard_boundary(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        project_id, episode_id = await _prepare_to_plan(wizard, pilot)
        wizard.action_build_plan()
        assert wizard._plan is not None

        drafts = GuidedDraftStore(service.workspaces.data_dir)
        for step in (
            "project",
            "sources",
            "research",
            "hosts",
            "episode",
            "plan",
            "preflight",
        ):
            drafts.save(
                WizardContext(
                    app.composition,
                    WizardState(WizardKind.NEW_DEEP_DIVE, step),
                    project_id=project_id,
                    episode_id=episode_id,
                )
            )
            # Build a fresh production context each time, not merely a new
            # in-memory wizard: persisted prerequisites determine recovery.
            fresh_service = DeeperDiveService(WorkspaceManager(service.workspaces.data_dir))
            fresh = ProductionComposition.build(service=fresh_service)
            with patch("deeper_dive.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
                restored = drafts.load(fresh, WizardKind.NEW_DEEP_DIVE)
            assert restored is not None
            assert restored.project_id == project_id
            assert restored.episode_id == episode_id
            assert restored.state.current_step == step


def test_two_guided_episodes_within_one_project_keep_artifacts_isolated(
    tmp_path: Path,
) -> None:
    asyncio.run(_two_guided_episodes_within_one_project_keep_artifacts_isolated(tmp_path))


async def _two_guided_episodes_within_one_project_keep_artifacts_isolated(
    tmp_path: Path,
) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    app.generation_monitor_controller.runner = None
    completed: list[tuple[str, str, Path, Path, set[str]]] = []

    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        project_id, first_episode_id = await _prepare_to_plan(wizard, pilot)

        for ordinal in range(2):
            if ordinal:
                # Another guided episode in the SAME durable project and corpus.
                app.action_navigate("new")
                await pilot.pause()
                wizard = app.screen
                assert isinstance(wizard, GuidedEpisodeWizard)
                wizard.context.project_id = project_id
                wizard.context.episode_id = None
                wizard.context.run_id = None
                wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "hosts")
                wizard._selected_host_ids.clear()
                wizard._toggle()
                wizard._sync_text()
                wizard._remember_current_form()
                wizard.action_create_recommended_hosts()
                wizard.action_save_host_order()
                wizard.action_continue()
                assert wizard.context.state.current_step == "episode"
                wizard.query_one("#guided-episode-title", Input).value = "Second Guided Episode"
                wizard.query_one(
                    "#guided-episode-focus", Input
                ).value = "Independent second discussion"
                wizard.action_save_episode()
                wizard.action_continue()
                assert wizard.context.state.current_step == "plan"

            episode_id = wizard.context.episode_id
            assert episode_id is not None
            assert (episode_id == first_episode_id) == (ordinal == 0)
            wizard.action_build_plan()
            assert wizard._plan is not None
            wizard.action_continue()
            with patch("deeper_dive.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
                wizard.action_check_preflight()
                assert wizard._preflight is not None and wizard._preflight.ready
                wizard.action_generate_deep_dive()
            await pilot.pause()
            run_id = wizard.context.run_id
            assert run_id is not None
            app.composition.run_generation(project_id, run_id)
            run = service.runs(project_id).get(run_id)
            assert run is not None and run.state == "completed"
            monitor = app.screen
            assert isinstance(monitor, GuidedGenerationMonitorScreen)
            monitor._route_completed_run()
            await pilot.pause()
            ready = app.screen
            assert isinstance(ready, GuidedEpisodeReadyScreen)
            ready.query_one("#ready-export", Button).press()
            await pilot.pause()
            assert "Exported" in str(ready.query_one("#ready-status", Static).render())
            ready.query_one("#ready-library", Button).press()
            await pilot.pause()
            assert app.screen.selected_episode_id == episode_id

            turns = TranscriptReviewController().turns(app)
            assert len(turns) >= 2
            turn_ids = {turn.id for turn in turns}
            assert len(turn_ids) == len(turns)
            root = service.workspaces.project_root(project_id)
            audio_path = root / "output" / f"{episode_id}.wav"
            assert audio_path.is_file()
            assert (
                AudioTimelineRepository(app.composition.database_for_project(project_id)).get(
                    episode_id
                )
                is not None
            )
            selected = next(
                item
                for item in EpisodeLibraryController.items(app)
                if item.episode.id == episode_id
            )
            exported = EpisodeLibraryController.export(app, selected)
            assert exported.audio is not None
            assert all(path.is_file() for path in exported.paths)
            completed.append((episode_id, run_id, exported.transcript, exported.audio, turn_ids))

        first, second = completed
        assert first[0] != second[0] and first[1] != second[1]
        assert first[2] != second[2] and first[3] != second[3]
        assert first[4].isdisjoint(second[4])
        assert {item.episode.id for item in EpisodeLibraryController.items(app)} == {
            first[0],
            second[0],
        }


def test_guided_project_and_episode_local_errors_render_inline_without_losing_input(
    tmp_path: Path,
) -> None:
    asyncio.run(_guided_field_errors_render_inline(tmp_path))


async def _guided_field_errors_render_inline(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.query_one("#guided-project-topic", Input).value = "Preserved curiosity"
        wizard.action_create_project()
        assert "Project name is required" in str(
            wizard.query_one("#guided-project-validation", Static).render()
        )
        assert wizard.query_one("#guided-project-topic", Input).value == "Preserved curiosity"
        assert wizard.context.project_id is None

        project_id, episode_id = await _prepare_to_plan(wizard, pilot)
        wizard.context.state = wizard.context.state.moved_to("episode")
        wizard._toggle()
        wizard.query_one("#guided-episode-title", Input).value = "Preserved episode title"
        wizard.query_one("#guided-episode-focus", Input).value = "Preserved episode focus"
        wizard.query_one("#guided-episode-duration", Select).value = "custom"
        wizard.query_one("#guided-episode-custom-duration", Input).value = "invalid"
        wizard.action_save_episode()
        error = str(wizard.query_one("#guided-episode-validation", Static).render())
        assert error.startswith("Fix episode settings:")
        assert wizard.query_one("#guided-episode-title", Input).value == "Preserved episode title"
        assert wizard.query_one("#guided-episode-focus", Input).value == "Preserved episode focus"
        assert wizard.query_one("#guided-episode-custom-duration", Input).value == "invalid"
        assert wizard.context.project_id == project_id
        assert wizard.context.episode_id == episode_id

        wizard.query_one("#guided-episode-custom-duration", Input).value = "12"
        wizard.action_save_episode()
        assert str(wizard.query_one("#guided-episode-validation", Static).render()) == ""
        assert (
            EpisodeConfigurationService(app.composition.database_for_project(project_id))
            .load_configuration(episode_id)
            .target_duration_seconds
            == 720
        )
