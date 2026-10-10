from __future__ import annotations

import pytest

from deeper_dive.diagnostics import redact
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigError, UserConfigStore


@pytest.mark.parametrize(
    "key",
    ["research_policy", "quick_deep_dive_research_policy"],
)
def test_invalid_research_defaults_are_rejected(key: str) -> None:
    with pytest.raises(ValueError, match=key):
        UserConfig(defaults={key: "reckless"})


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_invalid_quick_duration_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        UserConfig(defaults={"quick_deep_dive_duration_minutes": value})


@pytest.mark.parametrize(
    "value",
    ["skeptic", "skeptic,not-a-preset", "not-a-preset,curious_explainer"],
)
def test_invalid_quick_host_presets_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="exactly two valid host presets"):
        UserConfig(defaults={"quick_deep_dive_host_presets": value})


def test_valid_semantic_defaults_are_normalized() -> None:
    config = UserConfig(
        defaults={
            "research_policy": " Useful ",
            "quick_deep_dive_research_policy": "OFF",
            "quick_deep_dive_duration_minutes": " 25 ",
            "quick_deep_dive_host_presets": "skeptic, curious_explainer",
            "local_only": " YES ",
            "legacy_free_form": " preserve me ",
        }
    )
    assert config.defaults["research_policy"] == "useful"
    assert config.defaults["quick_deep_dive_research_policy"] == "off"
    assert config.defaults["quick_deep_dive_duration_minutes"] == "25"
    assert config.defaults["quick_deep_dive_host_presets"] == "skeptic,curious_explainer"
    assert config.defaults["local_only"] == "yes"
    assert config.defaults["legacy_free_form"] == " preserve me "


def test_mutated_invalid_default_cannot_bypass_validation_at_save(tmp_path) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    config = UserConfig(defaults={"research_policy": "useful"})
    store.save(config)
    original = path.read_bytes()

    config.defaults["research_policy"] = "secretly-invalid"
    with pytest.raises(UserConfigError, match="defaults"):
        store.save(config)

    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/v1#access_token=fragment-secret",
        "https://example.test/v1#ACCESS_TOKEN=fragment-secret",
        "https://example.test/v1#%61ccess_token%3Dfragment-secret",
        "http://[::1]:8080/v1#section",
    ],
)
def test_provider_base_url_rejects_fragments_without_echo(url: str) -> None:
    with pytest.raises(ValueError) as info:
        ProviderConfig(provider_type="openai", base_url=url)
    assert "fragment-secret" not in str(info.value)
    assert "fragment" in str(info.value).lower()


@pytest.mark.parametrize(
    "message",
    [
        "GET https://example.test/v1#access_token=fragment-canary",
        "GET https://example.test/v1#ACCESS_TOKEN=fragment-canary",
        "GET https://example.test/v1#%61ccess_token%3Dfragment-canary",
        "GET https://example.test/v1#safe=1&token=fragment-canary",
    ],
)
def test_diagnostic_url_fragment_credentials_are_redacted(message: str) -> None:
    safe = str(redact(message))
    assert "fragment-canary" not in safe
    assert "#[REDACTED]" in safe


def test_benign_diagnostic_url_fragment_is_preserved() -> None:
    message = "See https://example.test/docs#installation for details"
    assert redact(message) == message
