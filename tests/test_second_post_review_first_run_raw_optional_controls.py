"""First-run optional fields reject raw control bytes before normalization."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager


def test_first_run_raw_provider_and_speech_controls_do_not_reach_disk(tmp_path: Path) -> None:
    asyncio.run(_check_raw_provider_and_speech_controls(tmp_path))


async def _check_raw_provider_and_speech_controls(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 35)) as pilot:
        app._first_run_readiness.close()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)

        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "provider-config")
        wizard.query_one("#setup-ai-choice", Select).value = "manual"
        await pilot.pause()
        wizard.query_one("#setup-provider-name", Input).value = "llm-provider"
        wizard.query_one("#setup-provider-adapter", Input).value = "fake"
        wizard.query_one("#setup-provider-model", Input).value = "model"
        optional_provider = (
            ("#setup-provider-adapter", "fake"),
            ("#setup-provider-base-url", "https://localhost/v1"),
            ("#setup-provider-credential-env", "FAKE_KEY"),
            ("#setup-provider-network", "local"),
        )
        store = app.composition.config_store
        for selector, valid in optional_provider:
            widget = wizard.query_one(selector, Input)
            widget.value = valid + "\r"
            before = store.path.read_bytes() if store.path.exists() else None
            assert not wizard.action_save_provider()
            assert (store.path.read_bytes() if store.path.exists() else None) == before
            assert "single-line" in str(wizard.query_one("#wizard-status", Static).render())
            widget.value = valid

        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "speech")
        wizard.query_one("#setup-speech-choice", Select).value = "advanced"
        await pilot.pause()
        speech = (
            ("#setup-speech-name", "speech-service"),
            ("#setup-speech-adapter", "fake-tts"),
            ("#setup-speech-base-url", "https://localhost/v1"),
            ("#setup-speech-model", "model"),
            ("#setup-speech-credential-env", "SPEECH_KEY"),
            ("#setup-speech-network", "local"),
            ("#setup-speech-voices", "voice-1,voice-2"),
        )
        for selector, valid in speech:
            wizard.query_one(selector, Input).value = valid
        for selector, valid in speech:
            widget = wizard.query_one(selector, Input)
            widget.value = valid + "\r"
            before = store.path.read_bytes() if store.path.exists() else None
            assert not wizard.action_save_speech()
            assert (store.path.read_bytes() if store.path.exists() else None) == before
            assert "single-line" in str(wizard.query_one("#wizard-status", Static).render())
            widget.value = valid

        assert "llm-provider" not in store.load().providers
        assert "speech-service" not in store.load().providers
