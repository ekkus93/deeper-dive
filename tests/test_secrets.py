from __future__ import annotations

import json

import pytest

from deeper_dive.secrets import (
    REDACTED,
    CredentialResolver,
    EnvironmentCredentialStore,
    redact_data,
    redact_text,
)
from deeper_dive.user_config import ProviderConfig, UserConfig


class MemoryCredentialStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, reference: str) -> str | None:
        return self.values.get(reference)

    def set(self, reference: str, secret: str) -> None:
        self.values[reference] = secret

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


def test_environment_references_and_keyring_fallback() -> None:
    env = EnvironmentCredentialStore({"OPENAI_API_KEY": "env-secret"})
    primary = MemoryCredentialStore()
    resolver = CredentialResolver(primary, env)

    assert resolver.get("env:OPENAI_API_KEY") == "env-secret"
    assert resolver.get("openai", environment_fallback="OPENAI_API_KEY") == "env-secret"
    primary.set("openai", "keyring-secret")
    assert resolver.get("openai", environment_fallback="OPENAI_API_KEY") == "keyring-secret"

    with pytest.raises(ValueError):
        env.get("env:not valid")
    with pytest.raises(NotImplementedError):
        env.set("env:OPENAI_API_KEY", "value")


def test_redaction_removes_injected_secret_from_representative_diagnostics() -> None:
    injected = "test-super-secret-123"
    diagnostic = {
        "message": f"provider failed with {injected}",
        "authorization": f"Bearer {injected}",
        "nested": [f"api_key={injected}", {"password": injected}],
    }
    sanitized = redact_data(diagnostic, [injected])
    serialized = json.dumps(sanitized)

    assert injected not in serialized
    assert REDACTED in serialized
    assert injected not in redact_text(f"token: {injected}", [injected])


def test_user_config_schema_cannot_serialize_provider_secret() -> None:
    config = UserConfig(providers={"openai": ProviderConfig(provider_type="openai")})
    payload = config.model_dump_json()
    assert "secret" not in payload.lower()
    assert "api_key" not in payload.lower()

    with pytest.raises(ValueError):
        ProviderConfig(provider_type="openai", api_key="must-not-persist")  # type: ignore[call-arg]
