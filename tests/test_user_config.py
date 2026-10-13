from __future__ import annotations

import json
import os

import pytest

from deeper_dive.user_config import (
    ProviderConfig,
    UserConfig,
    UserConfigConflictError,
    UserConfigError,
    UserConfigStore,
)


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
            )
        },
        defaults={"host_generation": "local:model.gguf"},
    )
    store.save(config)
    loaded = store.load()
    assert loaded.schema_version == 1
    assert loaded.providers["local"].base_url == "http://127.0.0.1:8080"
    assert loaded.defaults["host_generation"] == "local:model.gguf"
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


def test_invalid_persisted_config_fails_before_provider_use(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"schema_version": 99, "providers": {}}))
    with pytest.raises(UserConfigError, match="schema_version"):
        UserConfigStore(path).load()


def test_unknown_or_secret_like_fields_are_rejected() -> None:
    with pytest.raises(ValueError):
        ProviderConfig.model_validate({"provider_type": "openai", "api_key": "secret"})


def test_first_time_writer_does_not_overwrite_concurrent_creation(tmp_path) -> None:
    path = tmp_path / "user" / "config.json"
    first = UserConfigStore(path).load()
    second = UserConfigStore(path).load()
    first.defaults["research_policy"] = "off"
    second.defaults["research_policy"] = "useful"

    UserConfigStore(path).save(first)
    original = path.read_bytes()
    with pytest.raises(UserConfigConflictError, match="reload and retry"):
        UserConfigStore(path).save(second)

    assert path.read_bytes() == original
    assert UserConfigStore(path).load().defaults["research_policy"] == "off"


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("base_url", "https://example.test/v1#api_key=mutated-provider-canary"),
        ("credential_env", "INVALID ENV mutated-provider-canary"),
        ("timeout_seconds", 0),
        ("response_format", "not-a-real-audio-format"),
        ("voices", ("safe", "mutated-provider-canary\nunsafe")),
    ],
)
def test_store_revalidates_mutated_nested_provider_before_publication(
    tmp_path, field: str, invalid: object
) -> None:
    """Pydantic model_copy(update=...) skips field validators; persistence must not."""
    store = UserConfigStore(tmp_path / "user-config.json")
    store.save(
        UserConfig(
            providers={
                "local": ProviderConfig(
                    provider_type="ollama",
                    base_url="http://127.0.0.1:11434",
                    default_model="default",
                )
            }
        )
    )
    durable = store.path.read_bytes()
    candidate = store.load()
    candidate.providers["local"] = candidate.providers["local"].model_copy(
        update={field: invalid}
    )

    with pytest.raises(UserConfigError) as error:
        store.save(candidate)
    assert "mutated-provider-canary" not in str(error.value)
    assert store.path.read_bytes() == durable
    assert store.load().providers["local"].base_url == "http://127.0.0.1:11434"


@pytest.mark.parametrize(
    ("key", "invalid"),
    [
        ("research_policy", "mutated-settings-canary"),
        ("network_policy", "mutated-settings-canary"),
        ("quick_deep_dive_duration_minutes", "-1"),
        ("local_only", "mutated-settings-canary"),
    ],
)
def test_store_revalidates_mutated_semantic_defaults_before_publication(
    tmp_path, key: str, invalid: str
) -> None:
    store = UserConfigStore(tmp_path / "user-config.json")
    store.save(UserConfig(defaults={"research_policy": "off"}))
    durable = store.path.read_bytes()
    candidate = store.load()
    candidate.defaults[key] = invalid

    with pytest.raises(UserConfigError) as error:
        store.save(candidate)
    assert "mutated-settings-canary" not in str(error.value)
    assert store.path.read_bytes() == durable
    assert store.load().defaults == {"research_policy": "off"}
