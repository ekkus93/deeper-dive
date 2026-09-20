from __future__ import annotations

import json
import os

import pytest

from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigError, UserConfigStore


def test_user_config_round_trip_is_separate_and_versioned(tmp_path) -> None:
    path = tmp_path / "user" / "config.json"
    project = tmp_path / "projects" / "p" / "project.db"
    store = UserConfigStore(path)
    config = UserConfig(
        providers={
            "local": ProviderConfig(
                provider_type="llama-server",
                base_url="http://127.0.0.1:8080/",
                default_model="model.gguf",
                network_policy="local",
            )
        },
        defaults={"host_generation": "local"},
    )
    store.save(config)
    loaded = store.load()
    assert loaded.schema_version == 1
    assert loaded.providers["local"].base_url == "http://127.0.0.1:8080"
    assert loaded.providers["local"].network_policy == "local"
    assert loaded.defaults["host_generation"] == "local"
    assert path != project
    assert not project.exists()


def test_saved_config_is_owner_only_on_posix(tmp_path) -> None:
    path = tmp_path / "config.json"
    UserConfigStore(path).save(UserConfig())
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600


def test_invalid_endpoint_fails_with_clear_validation_message() -> None:
    with pytest.raises(ValueError, match="base_url must use"):
        ProviderConfig(provider_type="ollama", base_url="file:///tmp/socket")


def test_invalid_network_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="network_policy"):
        ProviderConfig(provider_type="ollama", network_policy="unrestricted")


def test_invalid_persisted_config_fails_before_provider_use(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"schema_version": 99, "providers": {}}))
    with pytest.raises(UserConfigError, match="schema_version"):
        UserConfigStore(path).load()


def test_unknown_or_secret_like_fields_are_rejected() -> None:
    with pytest.raises(ValueError):
        ProviderConfig.model_validate({"provider_type": "openai", "api_key": "secret"})
