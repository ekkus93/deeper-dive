"""FPR-19: mounting runs once per screen; only ``WizardShell`` defines ``on_mount``."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from unittest.mock import patch

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_new_deep_dive import GuidedProjectWizard
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_shell import WizardShell


def test_only_the_shell_defines_on_mount() -> None:
    for cls in (GuidedFirstRunWizard, GuidedEpisodeWizard):
        for klass in cls.__mro__:
            if klass is WizardShell or not issubclass(klass, WizardShell):
                continue
            assert "on_mount" not in klass.__dict__, f"{klass.__name__} defines on_mount"


def test_mount_logic_runs_exactly_once_per_wizard(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    shell_mounts: list[str] = []
    project_loads: list[str] = []
    real_mount = WizardShell.__dict__["on_mount"]
    real_load = GuidedProjectWizard._load_project_form

    def counting_mount(self) -> None:  # type: ignore[no-untyped-def]
        shell_mounts.append(type(self).__name__)
        real_mount(self)

    def counting_load(self) -> None:  # type: ignore[no-untyped-def]
        project_loads.append(type(self).__name__)
        real_load(self)

    with (
        patch.object(WizardShell, "on_mount", counting_mount),
        patch.object(GuidedProjectWizard, "_load_project_form", counting_load),
    ):
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)) as pilot:
            await pilot.pause()
            assert shell_mounts == ["GuidedFirstRunWizard"]
            shell_mounts.clear()
            app._first_run_readiness.close()
            app.action_navigate("new")
            await pilot.pause()
            await pilot.pause()
            assert shell_mounts == ["GuidedEpisodeWizard"]
            assert project_loads == ["GuidedEpisodeWizard"]
    assert inspect.signature(real_mount).parameters  # keeps the import of inspect honest
