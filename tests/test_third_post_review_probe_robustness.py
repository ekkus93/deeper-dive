"""TPR-16: readiness probes stay bounded for subclasses and degrade per provider."""

from __future__ import annotations

from pathlib import Path

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_factory import ProviderBuildResult, ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _config(**providers: ProviderConfig) -> UserConfig:
    config = UserConfig()
    config.providers.update(providers)
    return config


def test_one_unbuildable_provider_does_not_hide_the_others() -> None:
    factory = ProviderFactory(environ={})
    config = _config(
        good=ProviderConfig(provider_type="fake", default_model="m"),
        needs_key=ProviderConfig(provider_type="openai", default_model="gpt"),
    )
    probe = factory.build(config, probe_timeout_seconds=0.5)
    assert "good" in probe.llm_registry.provider_ids()
    assert "needs_key" in probe.build_failures
    assert "needs_key" not in probe.llm_registry.provider_ids()


def test_production_build_still_fails_closed_on_unbuildable_provider() -> None:
    import pytest

    from deeper_dive.provider_factory import ProviderConfigurationError

    factory = ProviderFactory(environ={})
    config = _config(needs_key=ProviderConfig(provider_type="openai", default_model="gpt"))
    with pytest.raises(ProviderConfigurationError):
        factory.build(config)


def test_factory_subclass_still_receives_bounded_probes(tmp_path: Path) -> None:
    seen: list[float | None] = []

    class Custom(ProviderFactory):
        def build(
            self, config: UserConfig, *, probe_timeout_seconds: float | None = None
        ) -> ProviderBuildResult:
            seen.append(probe_timeout_seconds)
            return super().build(config, probe_timeout_seconds=probe_timeout_seconds)

    store = UserConfigStore(tmp_path / "config.json")
    controller = ProviderController(store, LLMProviderRegistry(), {}, provider_factory=Custom())
    isolated = controller.readiness_probe_controller(request_timeout_seconds=0.25)
    assert isolated is not controller
    assert seen == [0.25]


def test_aggregate_probe_budget_fails_remaining_providers_fast(tmp_path: Path) -> None:
    import pytest

    store = UserConfigStore(tmp_path / "config.json")
    store.save(_config(good=ProviderConfig(provider_type="fake", default_model="m")))
    controller = ProviderController(
        store, LLMProviderRegistry(), {}, provider_factory=ProviderFactory(environ={})
    )
    within = controller.readiness_probe_controller(
        request_timeout_seconds=0.25, total_timeout_seconds=60
    )
    assert within.llm("good") is not None

    expired = controller.readiness_probe_controller(
        request_timeout_seconds=0.25, total_timeout_seconds=1e-9
    )
    with pytest.raises(TimeoutError):
        expired.llm("good")
    with pytest.raises(TimeoutError):
        expired.tts("good")
    # The live controller has no deadline.
    assert controller.llm_registry is not None and controller.probe_deadline is None
