from __future__ import annotations

from pathlib import Path

import pytest

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.provider_factory import ProviderBuildResult, ProviderFactory
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry
from deeper_dive.user_config import UserConfig, UserConfigStore


class _PlanGenerator:
    def generate_plan(self, request):
        _ = request
        return {"segments": [{"title": "Opening", "target_duration_seconds": 900}]}


class _RecordingFactory(ProviderFactory):
    def __init__(self, *, verifier_response: str | None = None) -> None:
        super().__init__(environ={})
        self.director = FakeLLMProvider(provider_id="director", model="fake-v1")
        self.hoster = FakeLLMProvider(provider_id="hoster", model="fake-v1")
        self.verifier = FakeLLMProvider(
            provider_id="verifier",
            model="fake-v1",
            response=verifier_response or FakeLLMProvider.DEFAULT_RESPONSE,
        )
        self.speech = FakeTTSProvider(provider_id="speech")

    def build(self, config: UserConfig) -> ProviderBuildResult:
        _ = config
        llm = LLMProviderRegistry()
        llm.register(self.director)
        llm.register(self.hoster)
        llm.register(self.verifier)
        tts = TTSProviderRegistry()
        tts.register(self.speech)
        return ProviderBuildResult(
            llm,
            tts,
            {"speech": self.speech},
            {
                "director": "local",
                "hoster": "local",
                "verifier": "local",
                "speech": "local",
            },
        )


def _composition(
    tmp_path: Path,
    *,
    verifier_response: str | None = None,
) -> tuple[ProductionComposition, _RecordingFactory, str, str]:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            defaults={
                "episode_planning": "director:fake-v1",
                "directing": "director:fake-v1",
                "host_generation": "hoster:fake-v1",
                "verification": "verifier:fake-v1",
            }
        )
    )
    factory = _RecordingFactory(verifier_response=verifier_response)
    composition = ProductionComposition.build(data_dir, provider_factory=factory)
    project = composition.service.create_project("Role-backed generation")
    host = create_host_from_preset("curious_explainer", project.id)
    host.tts_provider = "speech"
    host.tts_voice = "voice-a"
    composition.service.hosts(project.id).create_host(host.to_record())
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Role backed episode",
            focus="Exercise configured directing and verification roles",
            target_duration_seconds=900,
            host_ids=(host.id,),
        ),
    )
    composition.planning_service(project.id, _PlanGenerator()).build_plan(episode.id)
    return composition, factory, project.id, episode.id


def test_generation_uses_configured_directing_and_verification_roles(tmp_path: Path) -> None:
    composition, factory, project_id, episode_id = _composition(tmp_path)
    run = composition.create_generation_run(project_id, episode_id)

    result = composition.run_generation(project_id, run.id)

    assert result.run.state == "completed"
    turns = HostTurnService(composition.database_for_project(project_id)).list_turns(
        episode_id
    )
    assert len(turns) == 1
    assert "Configured fake provider host turn marker" in turns[0].text
    assert "Configured fake directing decision marker" in turns[0].text
    assert factory.director.requests
    assert factory.hoster.requests
    assert factory.verifier.requests
    assert factory.director.requests[0].model == "fake-v1"
    assert factory.hoster.requests[0].model == "fake-v1"
    assert factory.verifier.requests[0].model == "fake-v1"


def test_generation_fails_when_configured_verification_rejects_transcript(
    tmp_path: Path,
) -> None:
    composition, factory, project_id, episode_id = _composition(
        tmp_path,
        verifier_response='{"accepted": false, "notes": "reject marker"}',
    )
    run = composition.create_generation_run(project_id, episode_id)

    with pytest.raises(ValueError, match="verification provider rejected transcript"):
        composition.run_generation(project_id, run.id)

    failed = composition.generation_run_repository(project_id).get(run.id)
    assert failed is not None
    assert failed.state == "failed"
    assert failed.stage == "verification"
    assert failed.failure_message is not None
    assert "reject marker" in failed.failure_message
    assert factory.verifier.requests
    output = (
        composition.service.workspaces.project_root(project_id)
        / "output"
        / f"{episode_id}.wav"
    )
    assert not output.exists()
