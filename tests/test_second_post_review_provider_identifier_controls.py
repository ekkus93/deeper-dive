"""Provider identifiers must not contain terminal-control characters."""

from __future__ import annotations

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigError, UserConfigStore


@pytest.mark.parametrize("codepoint", [0, 9, 10, 13, 27, 127])
def test_provider_identifiers_reject_controls_without_echo(codepoint: int) -> None:
    unsafe = "provider" + chr(codepoint) + "canary-identifier"
    with pytest.raises(ValueError, match="provider IDs") as error:
        UserConfig(providers={unsafe: ProviderConfig(provider_type="fake")})
    assert "canary-identifier" not in str(error.value)
    with pytest.raises(ValueError, match="provider_type") as error:
        ProviderConfig(provider_type=unsafe)
    assert "canary-identifier" not in str(error.value)


def test_mutated_provider_key_and_controller_rejected_without_write(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(providers={"local": ProviderConfig(provider_type="fake")}))
    original = store.path.read_bytes()
    config = store.load()
    config.providers["local" + chr(10) + "canary-identifier"] = config.providers.pop("local")
    with pytest.raises(UserConfigError, match="providers") as error:
        store.save(config)
    assert "canary-identifier" not in str(error.value)
    assert store.path.read_bytes() == original

    controller = ProviderController(store, LLMProviderRegistry(), {})
    with pytest.raises(UserConfigError, match="providers") as error:
        controller.save_provider("local" + chr(13) + "canary-identifier", "fake")
    assert "canary-identifier" not in str(error.value)
    assert store.path.read_bytes() == original


def test_printable_provider_identifiers_remain_valid() -> None:
    config = UserConfig(
        providers={
            "my-provider.v2": ProviderConfig(provider_type="fake"),
            "local_tts": ProviderConfig(provider_type="fake-tts"),
        }
    )
    assert set(config.providers) == {"my-provider.v2", "local_tts"}
