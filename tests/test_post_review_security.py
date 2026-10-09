"""Regressions discovered by the independent guided-workflow review."""

from __future__ import annotations

import json

import pytest

from deeper_dive.diagnostics import redact, sanitize_exception_message
from deeper_dive.secrets import redact_data, redact_text
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigError, UserConfigStore


@pytest.mark.parametrize(
    ("message", "canary"),
    [
        ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        ("Authorization: Token high-priority-credential", "high-priority-credential"),
        (
            "authorization=Digest username=alice, nonce=abcdef, response=supersecret; model=ok",
            "supersecret",
        ),
        ("Authorization: Custom scheme opaque-secret", "opaque-secret"),
        ("{'Authorization': 'Basic dXNlcjpwYXNz', 'status': 401}", "dXNlcjpwYXNz"),
        ('{"Authorization": "Token credential-123", "status": 401}', "credential-123"),
        ("authorization: Bearer value-123; status=401", "value-123"),
    ],
)
def test_authorization_forms_have_no_secret_tail(message: str, canary: str) -> None:
    for sanitizer in (redact, redact_text):
        result = str(sanitizer(message))
        assert canary not in result
        assert "[REDACTED]" in result


def test_nested_and_chained_exception_sanitization() -> None:
    secret = "secret-basic-value"
    nested = {"message": [f"Authorization: Basic {secret}", {"authorization": f"Token {secret}"}]}
    assert secret not in json.dumps(redact(nested))
    assert secret not in json.dumps(redact_data(nested))
    try:
        try:
            raise RuntimeError(f"Authorization: Basic {secret}")
        except RuntimeError as original:
            raise ValueError("failed request") from original
    except ValueError as error:
        assert secret not in sanitize_exception_message(error)


@pytest.mark.parametrize(
    "credential_env",
    ["sk-live-abc.def", "not valid", "BEARER abc", "not-an-env"],
)
def test_raw_credential_env_values_rejected(credential_env: str) -> None:
    with pytest.raises(ValueError):
        ProviderConfig(provider_type="openai", credential_env=credential_env)


def test_valid_credential_environment_variable_normalizes() -> None:
    config = ProviderConfig(provider_type="openai", credential_env=" OPENAI_API_KEY ")
    assert config.credential_env == "OPENAI_API_KEY"


@pytest.mark.parametrize(
    "url",
    [
        "https://alice:supersecret@example.test/v1",
        "https://bob@example.test/v1",
        "https://example.test/v1?api_key=supersecret",
        "https://example.test/v1?access_token=supersecret",
        "https://example.test/v1?PASSWORD=supersecret",
    ],
)
def test_credentials_in_provider_urls_rejected_without_echo(url: str) -> None:
    with pytest.raises(ValueError) as info:
        ProviderConfig(provider_type="openai", base_url=url)
    assert "supersecret" not in str(info.value)


def test_invalid_existing_configuration_fails_without_repeating_secret(tmp_path) -> None:
    secret = "sk-secret-do-not-echo-123"
    path = tmp_path / "config.json"
    payload = {
        "schema_version": 1,
        "providers": {"openai": {"provider_type": "openai", "credential_env": secret}},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(UserConfigError) as info:
        UserConfigStore(path).load()
    assert secret not in str(info.value)
    assert "credential_env" in str(info.value)
    assert secret in path.read_text()  # Invalid input is never silently rewritten.


def test_valid_provider_config_persists_only_reference(tmp_path) -> None:
    path = tmp_path / "config.json"
    UserConfigStore(path).save(
        UserConfig(
            providers={
                "openai": ProviderConfig(
                    provider_type="openai",
                    credential_env="OPENAI_API_KEY",
                    base_url="https://api.example.test/v1",
                )
            }
        )
    )
    text = path.read_text()
    assert "OPENAI_API_KEY" in text
    assert "supersecret" not in text


@pytest.mark.parametrize(
    ("field", "secret"),
    [
        ("credential_env", "sk-unsafe-mutated-secret.123"),
        ("base_url", "https://name:mutated-password@example.test/v1"),
        ("base_url", "https://example.test/v1?access_token=mutated-query-secret"),
    ],
)
def test_mutated_provider_cannot_bypass_validation_at_save(
    tmp_path, field: str, secret: str
) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    config = UserConfig(
        providers={"remote": ProviderConfig(provider_type="openai", credential_env="SAFE_ENV")}
    )
    store.save(config)
    original_bytes = path.read_bytes()

    setattr(config.providers["remote"], field, secret)
    with pytest.raises(UserConfigError) as info:
        store.save(config)

    assert str(secret) not in str(info.value)
    assert field in str(info.value)
    assert path.read_bytes() == original_bytes
    assert str(secret).encode() not in path.read_bytes()


def test_mutated_invalid_provider_is_rejected_before_initial_write(tmp_path) -> None:
    path = tmp_path / "no-config" / "config.json"
    config = UserConfig(providers={"remote": ProviderConfig(provider_type="openai")})
    config.providers["remote"].credential_env = "raw-secret.with-punctuation"

    with pytest.raises(UserConfigError):
        UserConfigStore(path).save(config)

    assert not path.exists()


def test_nested_exception_chain_redacts_every_level_and_terminates_on_cycle() -> None:
    inner = ValueError("Authorization: Basic deep-inner-secret")
    middle = RuntimeError("authorization=Token middle-level-secret")
    outer = OSError("request failed at provider")
    middle.__cause__ = inner
    outer.__cause__ = middle
    result = sanitize_exception_message(outer)
    assert "deep-inner-secret" not in result
    assert "middle-level-secret" not in result
    assert result.count("caused by:") == 2

    # Even malformed exception chains must not cause an infinite traversal.
    inner.__cause__ = outer
    cycle_result = sanitize_exception_message(outer)
    assert "deep-inner-secret" not in cycle_result
    assert "middle-level-secret" not in cycle_result
