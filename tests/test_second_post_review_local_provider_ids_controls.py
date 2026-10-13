"""Local provider defaults cannot smuggle terminal controls through normalization."""

from __future__ import annotations

import pytest

from deeper_dive.user_config import UserConfig, UserConfigError, UserConfigStore


@pytest.mark.parametrize("control", ["\\n", "\\r", "\\t", "\\x00", "\\x1b", "\\x7f"])
def test_local_provider_ids_reject_controls_before_trimming(control: str) -> None:
    canary = "provider-id-canary"
    unsafe = "ollama," + control.encode().decode("unicode_escape") + canary
    with pytest.raises(ValueError, match="local_provider_ids") as error:
        UserConfig(defaults={"local_provider_ids": unsafe})
    assert canary not in str(error.value)


def test_mutated_local_provider_ids_rejected_without_durable_write(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={"local_provider_ids": "ollama,llama-server"}))
    original = store.path.read_bytes()
    config = store.load()
    config.defaults["local_provider_ids"] = "ollama,\\nBearer provider-id-canary".replace(
        "\\n", "\n"
    )
    with pytest.raises(UserConfigError, match="defaults") as error:
        store.save(config)
    assert "provider-id-canary" not in str(error.value)
    assert store.path.read_bytes() == original


def test_local_provider_ids_preserve_printable_and_blank_compatibility() -> None:
    config = UserConfig(defaults={"local_provider_ids": " ollama, llama-server ,, custom.local "})
    assert config.defaults["local_provider_ids"] == "ollama,llama-server,custom.local"
    assert UserConfig(defaults={"local_provider_ids": ""}).defaults["local_provider_ids"] == ""
