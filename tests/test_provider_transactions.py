from __future__ import annotations

from pathlib import Path

import pytest

from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.provider_factory import ProviderBuildResult, ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


class TransactionFactory(ProviderFactory):
    def __init__(self) -> None:
        super().__init__(environ={})
        self.fail_when_present: str | None = None
        self.builds: list[tuple[str, ...]] = []

    def build(self, config: UserConfig) -> ProviderBuildResult:
        names = tuple(sorted(config.providers))
        self.builds.append(names)
        if self.fail_when_present is not None and self.fail_when_present in config.providers:
            raise ValueError(f"synthetic invalid provider: {self.fail_when_present}")
        llm = LLMProviderRegistry()
        tts = TTSProviderRegistry()
        tts_providers = {}
        routes = {}
        for name, provider_config in config.providers.items():
            if provider_config.provider_type == "fake":
                llm.register(FakeLLMProvider(provider_id=name))
                routes[name] = "local"
            elif provider_config.provider_type == "fake-tts":
                provider = FakeTTSProvider(provider_id=name)
                tts.register(provider)
                tts_providers[name] = provider
                routes[name] = "local"
        return ProviderBuildResult(llm, tts, tts_providers, routes)


def _controller(tmp_path: Path) -> tuple[ProviderController, TransactionFactory]:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(
        UserConfig(
            providers={
                "stable": ProviderConfig(provider_type="fake"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            }
        )
    )
    factory = TransactionFactory()
    initial = factory.build(store.load())
    controller = ProviderController(
        store,
        initial.llm_registry,
        initial.tts_providers,
        provider_factory=factory,
    )
    return controller, factory


def test_failed_provider_save_preserves_durable_config_and_live_runtime(
    tmp_path: Path,
) -> None:
    controller, factory = _controller(tmp_path)
    previous_llm = controller.llm_registry
    previous_tts = controller.tts_providers
    factory.fail_when_present = "broken"

    with pytest.raises(ValueError, match="synthetic invalid provider"):
        controller.save_provider("broken", "fake")

    assert set(controller.config().providers) == {"stable", "speech"}
    assert controller.llm_registry is previous_llm
    assert controller.tts_providers is previous_tts
    assert controller.llm("stable").provider_id == "stable"


def test_successful_provider_save_publishes_built_candidate_after_persistence(
    tmp_path: Path,
) -> None:
    controller, factory = _controller(tmp_path)
    published: list[tuple[str, ...]] = []
    controller.on_reload = lambda providers: published.append(providers.llm_registry.provider_ids())

    controller.save_provider("next", "fake")

    assert set(controller.config().providers) == {"stable", "speech", "next"}
    assert controller.llm_registry.provider_ids() == ("next", "stable")
    assert published == [("next", "stable")]
    assert factory.builds[-1] == ("next", "speech", "stable")


def test_failed_provider_removal_preserves_durable_config_and_live_runtime(
    tmp_path: Path,
) -> None:
    controller, factory = _controller(tmp_path)
    previous_llm = controller.llm_registry

    class RemovalRejectingFactory(TransactionFactory):
        def build(self, config: UserConfig) -> ProviderBuildResult:
            if "speech" not in config.providers:
                raise ValueError("speech provider is required")
            return super().build(config)

    rejecting = RemovalRejectingFactory()
    controller.provider_factory = rejecting

    with pytest.raises(ValueError, match="speech provider is required"):
        controller.remove_provider("speech")

    assert set(controller.config().providers) == {"stable", "speech"}
    assert controller.llm_registry is previous_llm
    assert controller.tts("speech").provider_id == "speech"


def test_successful_provider_removal_drops_provider_from_live_runtime(tmp_path: Path) -> None:
    controller, _factory = _controller(tmp_path)

    controller.remove_provider("stable")

    assert set(controller.config().providers) == {"speech"}
    with pytest.raises(KeyError, match="unknown LLM provider"):
        controller.llm("stable")
