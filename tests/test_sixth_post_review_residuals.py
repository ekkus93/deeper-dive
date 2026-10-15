"""6PR-09: lock side effect at a dangling symlink, refusal ids, monitor notice."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from test_fifth_post_review_stopping_run import _legacy_database
from textual.widgets import Select, Static

from deeper_dive.generation_start import select_or_create_generation_run
from deeper_dive.storage.episode_errors import GenerationRunStillStopping
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfig, UserConfigError, UserConfigStore


@pytest.mark.skipif(not hasattr(os, "symlink") or sys.platform == "win32", reason="needs symlinks")
def test_a_dangling_symlink_config_path_creates_nothing_at_its_target(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere" / "deep" / "target.json"
    link = tmp_path / "config.json"
    link.symlink_to(target)

    with pytest.raises(UserConfigError):
        UserConfigStore(link).save(UserConfig())

    assert not (tmp_path / "elsewhere").exists()


def test_refusal_names_the_real_project_id_and_no_placeholder(tmp_path: Path) -> None:
    service, project_id, episode_id = _legacy_database(tmp_path)
    with pytest.raises(GenerationRunStillStopping) as raised:
        select_or_create_generation_run(service, project_id, episode_id)
    message = str(raised.value)
    assert f"episode cancel {project_id} {episode_id} --run r1" in message
    assert "<project_id>" not in message


def test_monitor_shows_the_older_run_that_blocks_a_start(tmp_path: Path) -> None:
    async def run() -> None:
        service, project_id, episode_id = _legacy_database(tmp_path)
        app = DeeperDiveApp(service)
        async with app.run_test(size=(120, 40)) as pilot:
            app.current_project_id = project_id
            app.current_episode_id = episode_id
            app.action_navigate("monitor")
            await pilot.pause()
            text = str(app.screen.query_one("#generation-state", Static).render())
            # The latest run (r2) is displayed; the older stopping run is called out.
            assert "Run: r2" in text
            assert f"episode cancel {project_id} {episode_id} --run r1" in text

    asyncio.run(run())


def test_reset_select_blanks_or_picks_the_first_option_by_blank_policy() -> None:
    async def run() -> None:
        from textual.app import App, ComposeResult

        from deeper_dive.wizard_shell import WizardShell

        class Host(App[None]):
            def compose(self) -> ComposeResult:
                yield Select([("A", "a"), ("B", "b")], value="b", allow_blank=False, id="fixed")
                yield Select([("A", "a"), ("B", "b")], value="b", allow_blank=True, id="open")

        app = Host()
        async with app.run_test() as pilot:
            await pilot.pause()
            fixed = app.query_one("#fixed", Select)
            blankable = app.query_one("#open", Select)
            WizardShell._reset_select(None, fixed)  # type: ignore[arg-type]
            WizardShell._reset_select(None, blankable)  # type: ignore[arg-type]
            assert fixed.value == "a"
            assert blankable.value is Select.BLANK

    asyncio.run(run())
