"""SPR-04: reject terminal controls in provider:model defaults before durable writes."""

from __future__ import annotations

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigError, UserConfigStore


@pytest.mark.parametrize(
    "role",
    [
        "corpus_analysis",
        "research_planning",
        "source_analysis",
        "episode_planning",
        "directing",
        "host_generation",
        "verification",
    ],
)
@pytest.mark.parametrize("control", ["\\n", "\\r", "\\t", "\\x00", "\\x1b", "\\x7f"])
@pytest.mark.parametrize("position", ["provider", "model", "suffix"])
def test_model_role_defaults_reject_controls_without_echo(
    role: str, control: str, position: str
) -> None:
    character = control.encode().decode("unicode_escape")
    canary = "untrusted-control-canary"
    identity = {
        "provider": f"local{character}{canary}:model",
        "model": f"local:model{character}{canary}",
        "suffix": f"local:model{canary}{character}",
    }[position]
    with pytest.raises(ValueError) as caught:
        UserConfig(defaults={role: identity})
    assert role in str(caught.value)
    assert canary not in str(caught.value)


def test_mutated_model_role_is_revalidated_and_does_not_replace_config(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={"host_generation": "local:working-model"}))
    original = store.path.read_bytes()
    config = store.load()
    config.defaults["host_generation"] = "local:working-model\\nBearer secret-canary".replace(
        "\\n", "\n"
    )
    with pytest.raises(UserConfigError, match="defaults") as caught:
        store.save(config)
    assert "secret-canary" not in str(caught.value)
    assert store.path.read_bytes() == original
    assert store.load().defaults["host_generation"] == "local:working-model"


def test_settings_model_default_control_is_rejected_without_changing_bytes(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(
        UserConfig(
            providers={"local": ProviderConfig(provider_type="ollama")},
            defaults={"host_generation": "local:working-model"},
        )
    )
    original = store.path.read_bytes()
    controller = SettingsController(ProviderController(store, LLMProviderRegistry(), {}))
    with pytest.raises(ValueError) as caught:
        controller.save_model_default("host_generation", "local:model\\x1b[31msecret-canary")
    assert "secret-canary" not in str(caught.value)
    assert store.path.read_bytes() == original
    assert store.load().defaults["host_generation"] == "local:working-model"


def test_printable_model_identifiers_and_legacy_bare_model_remain_compatible(tmp_path) -> None:
    config = UserConfig(defaults={"host_generation": " local:models/version-one "})
    assert config.defaults["host_generation"] == "local:models/version-one"
    store = UserConfigStore(tmp_path / "config.json")
    store.save(config)
    assert store.load().defaults["host_generation"] == "local:models/version-one"
