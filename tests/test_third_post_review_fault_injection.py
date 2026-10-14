"""TPR-18: durable-write failures at the filesystem level keep edits and report the error."""

from __future__ import annotations

import asyncio
import errno
import os
from pathlib import Path

import pytest
from fault_injection import failing_replace
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import ProviderConfig, UserConfigStore


def test_fixture_only_fails_destinations_under_the_given_root(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "a.tmp").write_text("x")
    (tmp_path / "b.tmp").write_text("y")
    with failing_replace(blocked, code=errno.EACCES) as refused:
        with pytest.raises(OSError) as info:
            os.replace(blocked / "a.tmp", blocked / "a.txt")
        assert info.value.errno == errno.EACCES
        os.replace(tmp_path / "b.tmp", tmp_path / "b.txt")
    assert len(refused) == 1
    assert (tmp_path / "b.txt").exists() and (blocked / "a.tmp").exists()
    # The real os.replace is restored afterwards.
    os.replace(blocked / "a.tmp", blocked / "a.txt")
    assert (blocked / "a.txt").exists()


def test_config_store_save_failure_leaves_previous_file_untouched(tmp_path: Path) -> None:
    store = UserConfigStore(tmp_path / "cfg" / "config.json")
    first = store.load()
    first.providers["one"] = ProviderConfig(provider_type="fake", default_model="m")
    store.save(first)
    durable = store.path.read_bytes()
    second = store.load()
    second.providers["two"] = ProviderConfig(provider_type="fake", default_model="m")
    with failing_replace(store.path.parent) as refused, pytest.raises(OSError):
        store.save(second)
    assert refused
    assert store.path.read_bytes() == durable


def test_wizard_save_failure_keeps_edit_dirty_and_unsaved(tmp_path: Path) -> None:
    asyncio.run(_wizard_save_failure(tmp_path))


async def _wizard_save_failure(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 35)) as pilot:
        app._first_run_readiness.close()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        controller = app.provider_controller
        controller.save_provider(
            "local",
            "ollama",
            base_url="http://127.0.0.1:11434",
            default_model="m",
            network_scope="local",
        )
        durable = controller.config_store.path.read_bytes()
        wizard._load_existing_setup()
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "provider-config")
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()
        wizard._remember_current_form()

        wizard.query_one("#setup-provider-name", Input).value = "renamed"
        await pilot.pause()
        assert wizard._current_form_dirty()
        wizard.action_back()
        await pilot.pause()
        assert wizard.query_one("#wizard-exit-confirmation").display

        with failing_replace(controller.config_store.path.parent) as refused:
            wizard.action_confirm_save_exit()
            await pilot.pause()

        assert refused, "the durable write was never attempted"
        assert controller.config_store.path.read_bytes() == durable
        assert wizard.query_one("#setup-provider-name", Input).value == "renamed"
        assert wizard._current_form_dirty()
        assert wizard.context.state.current_step == "provider-config"
        assert isinstance(wizard.query_one("#setup-ai-choice", Select).value, str)
