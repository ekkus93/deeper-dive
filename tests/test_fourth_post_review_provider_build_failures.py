"""FPR-15: unbuildable providers are named in readiness, never echo input, and isolate."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.provider_factory import ProviderBuildResult, ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _controller(tmp_path: Path, factory: ProviderFactory) -> ProviderController:
    store = UserConfigStore(tmp_path / "config.json")
    return ProviderController(
        store, ProviderFactory(environ={}).build(UserConfig()).llm_registry, {}, factory
    )


class _ExplodingFactory(ProviderFactory):
    """A factory whose adapter constructor raises a plain ValueError for one provider."""

    def _llm(self, kind, config, *, readiness_probe=False):  # type: ignore[no-untyped-def]
        if config.default_model == "boom":
            raise ValueError("constructor rejected the model")
        return super()._llm(kind, config, readiness_probe=readiness_probe)


def test_constructor_value_error_degrades_one_provider_in_probe_mode(tmp_path: Path) -> None:
    config = UserConfig(
        providers={
            "good": ProviderConfig(provider_type="fake", default_model="ok"),
            "bad": ProviderConfig(provider_type="fake", default_model="boom"),
        }
    )
    UserConfigStore(tmp_path / "config.json").save(config)
    factory = _ExplodingFactory(environ={})
    result = factory.build(config, probe_timeout_seconds=1.0)
    assert "bad" in result.build_failures and "good" not in result.build_failures
    assert result.llm_registry.get("good") is not None
    # Production builds still fail loudly.
    with pytest.raises(ValueError, match="constructor rejected"):
        factory.build(config)


def test_legacy_type_message_never_echoes_the_configured_value() -> None:
    config = UserConfig(providers={"p": ProviderConfig(provider_type="openai_compatible_CANARY9x")})
    try:
        result = ProviderFactory(environ={}).build(config, probe_timeout_seconds=1.0)
        text = " ".join(result.build_failures.values())
    except Exception as exc:  # unsupported type may raise at validation instead
        text = str(exc)
    assert "CANARY9x" not in text


def test_factory_overriding_build_without_the_keyword_is_not_probed(tmp_path: Path) -> None:
    class Legacy(ProviderFactory):
        def build(self, config):  # type: ignore[no-untyped-def,override]
            return super().build(config)

    store = UserConfigStore(tmp_path / "config.json")
    controller = ProviderController(
        store, ProviderFactory(environ={}).build(UserConfig()).llm_registry, {}, Legacy()
    )
    assert controller.readiness_probe_controller() is controller


def test_readiness_names_the_provider_that_could_not_be_built(tmp_path: Path) -> None:
    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)) as pilot:
            await pilot.pause()
            wizard = app.screen
            controller = app.provider_controller
            controller.save_provider("good", "fake", default_model="fake-v1")
            real = controller.provider_factory.build

            def build(config, *, probe_timeout_seconds=None):  # type: ignore[no-untyped-def]
                result = real(config, probe_timeout_seconds=probe_timeout_seconds)
                if probe_timeout_seconds is None:
                    return result
                return ProviderBuildResult(
                    result.llm_registry,
                    result.tts_registry,
                    result.tts_providers,
                    result.network_scopes,
                    {"broken": "adapter rejected its settings"},
                )

            controller.provider_factory.build = build  # type: ignore[method-assign]
            snapshot = wizard._runtime_readiness  # coordinator
            assert snapshot is not None
            result = snapshot._probe_runtime()
            assert result.provider_notes == (("broken", "adapter rejected its settings"),)
            rows = wizard._provider_note_rows(result)
            assert rows and "broken" in rows[0] and "adapter rejected" in rows[0]

    asyncio.run(run())


def test_legacy_type_names_only_the_normalized_member() -> None:
    config = UserConfig(providers={"p": ProviderConfig(provider_type="  LLM  ")})
    result = ProviderFactory(environ={}).build(config, probe_timeout_seconds=1.0)
    message = result.build_failures["p"]
    assert "'llm'" in message and "  LLM  " not in message
