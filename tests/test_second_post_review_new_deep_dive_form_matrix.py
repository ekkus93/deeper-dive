"""Cross-step New Deep Dive dirty-form navigation matrix using real services."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_planner import EpisodePlannerService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager


class _FixturePlanGenerator:
    def generate_plan(self, _request: object) -> dict[str, object]:
        return {
            "segments": [
                {
                    "title": "Opening",
                    "purpose": "Introduce the topic",
                    "target_duration_seconds": 600,
                    "questions": [],
                    "evidence_ids": [],
                    "lead_host_ids": [],
                },
                {
                    "title": "Discussion",
                    "purpose": "Review the evidence",
                    "target_duration_seconds": 600,
                    "questions": [],
                    "evidence_ids": [],
                    "lead_host_ids": [],
                },
            ]
        }


_FORM_CASES = (
    ("project", "guided-project-name"),
    ("project", "guided-project-topic"),
    ("project", "guided-project-audience"),
    ("project", "guided-project-description"),
    ("sources", "guided-source-title"),
    ("sources", "guided-source-text"),
    ("sources", "guided-source-paths"),
    ("sources", "guided-source-urls"),
    ("research", "guided-research-policy"),
    ("hosts", "guided-host-name"),
    ("hosts", "guided-host-role"),
    ("hosts", "guided-host-expertise"),
    ("hosts", "guided-host-instructions"),
    ("episode", "guided-episode-title"),
    ("episode", "guided-episode-focus"),
    ("episode", "guided-episode-duration"),
    ("episode", "guided-episode-custom-duration"),
    ("episode", "guided-episode-audience"),
    ("episode", "guided-episode-depth"),
    ("episode", "guided-episode-must-cover"),
    ("episode", "guided-episode-avoid"),
    ("plan", "guided-plan-title"),
    ("plan", "guided-plan-purpose"),
    ("plan", "guided-plan-duration"),
)


@pytest.mark.parametrize(("step", "field_id"), _FORM_CASES)
def test_new_deep_dive_dirty_back_cancel_and_discard_matrix(
    tmp_path: Path, step: str, field_id: str
) -> None:
    asyncio.run(_check_dirty_step(tmp_path, step, field_id))


async def _check_dirty_step(tmp_path: Path, step: str, field_id: str) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Form matrix")
    hosts = service.hosts(project.id)
    for host_id in ("host-one", "host-two"):
        hosts.create_host(HostProfile(host_id, project.id, host_id).to_record())
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    episode = EpisodeConfigurationService(database).create(
        project.id,
        EpisodeConfiguration(
            title="Original episode",
            focus="Original focus",
            target_duration_seconds=1200,
            host_ids=("host-one", "host-two"),
        ),
    )
    plan = None
    if step == "plan":
        plan = EpisodePlannerService(database, _FixturePlanGenerator()).build_plan(episode.id)

    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.episode_id = episode.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, step)
        wizard._load_episode_host_order()
        if step == "sources":
            wizard._refresh_sources()
        elif step == "research":
            wizard._refresh_research_choice()
        elif step == "hosts":
            wizard._refresh_hosts("host-one")
        elif step == "episode":
            wizard._load_episode_form()
        elif step == "plan":
            assert plan is not None
            wizard._plan = plan
            wizard._selected_segment_ordinal = 0
            wizard._render_plan()
        wizard._toggle()
        await pilot.pause()
        wizard._remember_current_form()

        widget = wizard.query_one(f"#{field_id}")
        assert isinstance(widget, (Input, Select))
        original = widget.value
        if isinstance(widget, Input):
            widget.value = f"{original} pending form edit"
        else:
            alternatives = {
                "guided-project-audience": ("technical", "expert"),
                "guided-research-policy": ("off", "aggressive"),
                "guided-episode-duration": ("30", "10"),
                "guided-episode-audience": ("technical", "expert"),
                "guided-episode-depth": ("deep", "accessible"),
            }
            options = alternatives[field_id]
            widget.value = options[0] if original != options[0] else options[1]
        await pilot.pause()

        pending = widget.value
        assert pending != original
        assert wizard._current_form_dirty(), (step, field_id)
        assert wizard.action_back() is False
        assert wizard.context.state.current_step == step
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert widget.value == pending
        wizard.action_cancel_exit_confirmation()
        assert not wizard.query_one("#wizard-exit-confirmation").display
        assert widget.value == pending
        assert wizard._current_form_dirty()

        assert wizard.action_back() is False
        wizard.action_confirm_discard_exit()
        await pilot.pause()
        assert widget.value == original
        assert not wizard._current_form_dirty()
        assert not wizard.query_one("#wizard-exit-confirmation").display
        if step == "episode":
            assert EpisodeConfigurationService(database).load_configuration(episode.id).title == (
                "Original episode"
            )
        if step == "plan":
            assert EpisodePlannerService(database, _FixturePlanGenerator()).load_plan(
                episode.id
            ).segments[0].title == "Opening"
