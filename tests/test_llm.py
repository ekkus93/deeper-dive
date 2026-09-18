from __future__ import annotations

import pytest

from deeper_dive.llm import (
    FakeLLMProvider,
    LLMMessage,
    LLMProviderRegistry,
    LLMRequest,
)


def test_fake_provider_deterministically_drives_generation_and_streaming() -> None:
    provider = FakeLLMProvider(response="hello deterministic world")
    request = LLMRequest((LLMMessage("user", "say hello"),))

    response = provider.generate(request)
    assert response.text == "hello deterministic world"
    assert response.model == "fake-v1"
    assert response.usage.input_tokens == 2
    assert response.usage.output_tokens == 3
    assert "".join(chunk.text for chunk in provider.stream(request)) == response.text
    assert provider.models()[0].capabilities.streaming
    assert provider.models()[0].capabilities.structured_output
    assert provider.health().healthy


def test_registry_normalizes_configuration_health_and_model_discovery() -> None:
    registry = LLMProviderRegistry()
    alpha = FakeLLMProvider(provider_id="alpha", model="a")
    beta = FakeLLMProvider(provider_id="beta", model="b")
    registry.register(beta)
    registry.register(alpha)

    assert registry.provider_ids() == ("alpha", "beta")
    assert registry.get("alpha") is alpha
    assert registry.health()["beta"].healthy
    assert registry.models()["alpha"][0].identity == "alpha:a"

    with pytest.raises(KeyError, match="unknown LLM provider"):
        registry.get("missing")
