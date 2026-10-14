"""TPR-18: plan-step dirty guards driven only by real clicks, typing and keys.

Each test builds its plan through the production planner (a fake model assigned to
the episode-planning role), so nothing seeds ``context.state``, ``_plan`` or baselines.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from guided_pilot import choose_option, click, reach_plan, type_into
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_planner import EpisodePlannerService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.storage.workspace import WorkspaceManager


def _app(tmp_path: Path) -> GuidedDeeperDiveApp:
    return GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))


def _persisted_plan(wizard: GuidedEpisodeWizard):
    episode_id = wizard.context.episode_id
    assert episode_id is not None
    return wizard._planning_service().load_plan(episode_id)


def test_typed_segment_edit_blocks_reselect_until_explicit_discard(tmp_path: Path) -> None:
    asyncio.run(_reselect(tmp_path))


async def _reselect(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 45)) as pilot:
        await reach_plan(pilot)
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        durable = _persisted_plan(wizard)
        title = wizard.query_one("#guided-plan-title", Input)
        picker = wizard.query_one("#guided-plan-segment-picker", Select)
        assert title.value == durable.segments[0].title

        await type_into(pilot, "#guided-plan-title", "Unsaved opening title")
        first = picker.value
        await choose_option(pilot, "#guided-plan-segment-picker", 1)

        assert picker.value == first
        assert title.value == "Unsaved opening title"
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert wizard.focused is wizard.query_one("#wizard-confirm-cancel")

        await click(pilot, "#wizard-confirm-cancel")
        assert picker.value == first
        assert title.value == "Unsaved opening title"
        assert not wizard.query_one("#wizard-exit-confirmation").display

        await choose_option(pilot, "#guided-plan-segment-picker", 1)
        await click(pilot, "#wizard-confirm-discard")
        assert picker.value != first
        assert title.value == durable.segments[1].title
        assert _persisted_plan(wizard).segments[0].title == durable.segments[0].title


@pytest.mark.parametrize("operation", ("build", "regenerate", "regenerate-segment"))
@pytest.mark.parametrize("resolution", ("discard", "save", "invalid-save"))
def test_typed_segment_edit_guards_plan_operations(
    tmp_path: Path, operation: str, resolution: str
) -> None:
    asyncio.run(_operation(tmp_path, operation, resolution))


_BUTTONS = {
    "build": "#guided-plan-build",
    "regenerate": "#guided-plan-regenerate",
    "regenerate-segment": "#guided-plan-regenerate-segment",
}


async def _operation(tmp_path: Path, operation: str, resolution: str) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(100, 45)) as pilot:
        await reach_plan(pilot)
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        original = _persisted_plan(wizard)
        changed = "Do not silently overwrite this draft title"
        title = wizard.query_one("#guided-plan-title", Input)
        await type_into(pilot, "#guided-plan-title", changed)
        button = _BUTTONS[operation]

        with patch.object(
            EpisodePlannerService,
            "edit_segment",
            autospec=True,
            side_effect=EpisodePlannerService.edit_segment,
        ) as edit:
            await click(pilot, button)
            assert wizard.query_one("#wizard-exit-confirmation").display
            assert wizard.focused is wizard.query_one("#wizard-confirm-cancel")
            await click(pilot, button)  # a repeated click must not bypass the prompt
            assert wizard.query_one("#wizard-exit-confirmation").display
            assert title.value == changed
            assert _persisted_plan(wizard).id == original.id

            await click(pilot, "#wizard-confirm-cancel")
            assert title.value == changed
            assert _persisted_plan(wizard).id == original.id

            if resolution == "invalid-save":
                await type_into(pilot, "#guided-plan-duration", "invalid")
            await click(pilot, button)
            if resolution == "discard":
                await click(pilot, "#wizard-confirm-discard")
            else:
                await click(pilot, "#wizard-confirm-save")

            assert not wizard.query_one("#wizard-exit-confirmation").display
            if resolution == "invalid-save":
                assert edit.call_count == 0
                assert title.value == changed
                assert _persisted_plan(wizard).id == original.id
                assert wizard._current_form_dirty()
            else:
                assert _persisted_plan(wizard).id != original.id
                assert title.value != changed
                assert edit.call_count == (1 if resolution == "save" else 0)
                if resolution == "save":
                    assert edit.call_args.args[-1].title == changed


@pytest.mark.parametrize("resolution", ("save", "discard"))
def test_typed_segment_edit_guards_continue_to_preflight(tmp_path: Path, resolution: str) -> None:
    asyncio.run(_continue(tmp_path, resolution))


async def _continue(tmp_path: Path, resolution: str) -> None:
    # Generate Deep Dive and Fix First Blocker exist only on the preflight step, so a
    # pointer cannot reach them with a dirty plan form; their direct-call guard stays
    # covered by test_second_post_review_dirty_navigation.py. Continue is the real path.
    app = _app(tmp_path)
    async with app.run_test(size=(100, 45)) as pilot:
        await reach_plan(pilot)
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        original = _persisted_plan(wizard)
        edited = "Unsaved plan edit before continuing"
        await type_into(pilot, "#guided-plan-title", edited)

        await click(pilot, "#wizard-continue")
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert wizard.context.state.current_step == "plan"
        assert wizard.context.run_id is None
        assert _persisted_plan(wizard).id == original.id

        await click(pilot, "#wizard-confirm-cancel")
        assert wizard.context.state.current_step == "plan"
        assert wizard.query_one("#guided-plan-title", Input).value == edited

        await click(pilot, "#wizard-continue")
        await click(pilot, f"#wizard-confirm-{resolution}")
        assert wizard.context.state.current_step == "preflight"
        titles = [segment.title for segment in _persisted_plan(wizard).segments]
        assert (edited in titles) == (resolution == "save")
