"""Voice/default identifiers cannot persist terminal-control characters."""

from __future__ import annotations

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigError, UserConfigStore


@pytest.mark.parametrize(
    "field", ["tts_provider", "tts_voice", "tts_voice_host_1", "tts_voice_host_2"]
)
@pytest.mark.parametrize("control", ["\\n", "\\r", "\\t", "\\x00", "\\x7f"])
def test_voice_default_control_characters_rejected_without_echo(field: str, control: str) -> None:
    canary = "voice-default-canary"
    value = "valid-" + control.encode().decode("unicode_escape") + canary
    with pytest.raises(ValueError) as error:
        UserConfig(defaults={field: value})
    assert canary not in str(error.value)
    assert field in str(error.value)


@pytest.mark.parametrize("control", ["\\n", "\\r", "\\t", "\\x00", "\\x7f"])
def test_declared_provider_voices_reject_controls_without_echo(control: str) -> None:
    canary = "provider-voice-canary"
    value = "voice-" + control.encode().decode("unicode_escape") + canary
    with pytest.raises(ValueError) as error:
        ProviderConfig(provider_type="fake-tts", voices=("normal", value))
    assert canary not in str(error.value)
    assert "voices" in str(error.value)


def test_mutated_voice_controls_do_not_change_persisted_bytes(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(
        UserConfig(
            providers={"speech": ProviderConfig(provider_type="fake-tts", voices=("voice-a",))},
            defaults={"tts_voice": "voice-a"},
        )
    )
    original = store.path.read_bytes()

    first = store.load()
    first.defaults["tts_voice"] = "voice-a\\nAuthorization: Bearer canary".replace("\\n", "\n")
    with pytest.raises(UserConfigError, match="defaults") as error:
        store.save(first)
    assert "canary" not in str(error.value)
    assert store.path.read_bytes() == original

    second = store.load()
    second.providers["speech"].voices = ("voice-a\\nBearer canary".replace("\\n", "\n"),)
    with pytest.raises(UserConfigError, match="providers") as error:
        store.save(second)
    assert "canary" not in str(error.value)
    assert store.path.read_bytes() == original


def test_printable_voice_identifiers_and_optional_blank_values_remain_valid() -> None:
    config = UserConfig(
        providers={"speech": ProviderConfig(provider_type="fake-tts", voices=("Friendly Voice",))},
        defaults={"tts_voice": " Friendly Voice ", "tts_voice_host_1": ""},
    )
    assert config.providers["speech"].voices == ("Friendly Voice",)
    assert config.defaults["tts_voice"] == "Friendly Voice"
    assert config.defaults["tts_voice_host_1"] == ""



def test_settings_and_provider_mutations_reject_voice_controls_atomically(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(
        UserConfig(
            providers={
                "speech": ProviderConfig(provider_type="fake-tts", voices=("voice-a",))
            },
            defaults={"tts_provider": "speech", "tts_voice": "voice-a"},
        )
    )
    original = store.path.read_bytes()
    provider = ProviderController(
        store,
        LLMProviderRegistry(),
        {"speech": FakeTTSProvider()},
    )
    settings = SettingsController(provider)
    with pytest.raises(ValueError) as failure:
        settings.save_tts_defaults("speech", "voice-a\nBearer value-canary")
    assert "value-canary" not in str(failure.value)
    assert store.path.read_bytes() == original

    with pytest.raises(ValueError) as failure:
        provider.save_provider(
            "speech",
            "fake-tts",
            voices=("voice-a", "other\rAuthorization: value-canary"),
        )
    assert "value-canary" not in str(failure.value)
    assert store.path.read_bytes() == original
