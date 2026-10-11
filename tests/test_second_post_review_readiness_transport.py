"""Bound provider discovery I/O without altering generation runtime configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeper_dive.openai_llm import OpenAITimeoutError
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _controller(tmp_path: Path, provider_type: str) -> ProviderController:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(
        UserConfig(
            providers={
                "remote": ProviderConfig(
                    provider_type=provider_type,
                    default_model="model-v1",
                    timeout_seconds=600,
                )
            }
        )
    )
    factory = ProviderFactory(environ={"OPENAI_API_KEY": "fake-test-only"})
    configured = factory.build(store.load())
    return ProviderController(
        store,
        configured.llm_registry,
        configured.tts_providers,
        provider_factory=factory,
    )


@pytest.mark.parametrize("provider_type", ("ollama", "llama-server"))
def test_readiness_discovery_passes_real_bounded_transport_timeout(
    tmp_path: Path, provider_type: str
) -> None:
    controller = _controller(tmp_path, provider_type)
    probe = controller.readiness_probe_controller(request_timeout_seconds=1.0)
    assert probe is not controller
    assert probe.llm("remote") is not controller.llm("remote")
    assert probe.config().providers["remote"].timeout_seconds == 600

    observed: list[float] = []

    def request(_method: str, _url: str, _payload: object, timeout: float) -> dict:
        observed.append(timeout)
        return {"status": "ok", "models": []}

    # Exercise both discovery calls through the actual configured adapter's
    # normalized public boundary, without opening a socket.
    delegate = probe.llm("remote")._delegate
    delegate._request = request
    probe.llm("remote").health()
    probe.llm("remote").models()
    assert observed == [1.0, 1.0]
    assert controller.llm("remote")._delegate._timeout == 600


def test_openai_readiness_discovery_uses_one_bounded_attempt(tmp_path: Path) -> None:
    controller = _controller(tmp_path, "openai")
    probe = controller.readiness_probe_controller(request_timeout_seconds=1.0)
    delegate = probe.llm("remote")._delegate
    observed: list[float] = []

    def timeout_request(
        _method: str,
        _url: str,
        _payload: object,
        _headers: dict[str, str],
        timeout: float,
    ) -> dict:
        observed.append(timeout)
        raise OpenAITimeoutError("synthetic timeout")

    delegate._request = timeout_request
    with pytest.raises(OpenAITimeoutError, match="synthetic timeout"):
        probe.llm("remote").models()
    assert observed == [1.0]
    assert controller.llm("remote")._delegate._timeout == 600
    assert controller.llm("remote")._delegate._max_retries == 2


def test_readiness_probe_never_publishes_or_persists_timeout_change(tmp_path: Path) -> None:
    controller = _controller(tmp_path, "ollama")
    original_registry = controller.llm_registry
    original_bytes = (tmp_path / "config.json").read_bytes()
    for _ in range(5):
        scoped = controller.readiness_probe_controller(request_timeout_seconds=0.75)
        assert scoped.llm("remote")._delegate._timeout == 0.75
    assert controller.llm_registry is original_registry
    assert controller.llm("remote")._delegate._timeout == 600
    assert (tmp_path / "config.json").read_bytes() == original_bytes


def test_probe_timeout_must_be_positive(tmp_path: Path) -> None:
    factory = ProviderFactory()
    with pytest.raises(ValueError, match="probe timeout must be positive"):
        factory.build(UserConfig(), probe_timeout_seconds=0)
