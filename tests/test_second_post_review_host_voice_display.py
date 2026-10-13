"""Host voice display must not make hidden cloud requests from Textual refreshes."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import ProviderConfig


def test_rendering_host_voice_does_not_discover_remote_elevenlabs_voices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
        app = GuidedDeeperDiveApp(service)
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_navigate("new")
            await pilot.pause()
            wizard = app.screen
            assert isinstance(wizard, GuidedEpisodeWizard)

            store = app.composition.config_store
            candidate = store.load()
            candidate.providers["elevenlabs-cloud"] = ProviderConfig(
                provider_type="elevenlabs", credential_env="ELEVENLABS_API_KEY"
            )
            store.save(candidate)

            attempts: list[str] = []

            def unexpected_network_adapter(provider_id: str) -> None:
                attempts.append(provider_id)
                raise AssertionError("host rendering must not request remote voices")

            monkeypatch.setattr(
                app.composition.provider_controller, "tts", unexpected_network_adapter
            )
            assert wizard._voice_label("elevenlabs-cloud", "voice-id") == (
                "ElevenLabs voice (voice-id)"
            )
            assert wizard._voice_label("elevenlabs-cloud", "another-voice") == (
                "ElevenLabs voice (another-voice)"
            )
            assert attempts == []

    asyncio.run(exercise())
