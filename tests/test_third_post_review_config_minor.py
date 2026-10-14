"""TPR-19.7: scheme case-insensitivity and control-character validation parity."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from deeper_dive.user_config import ProviderConfig


def test_uppercase_scheme_is_accepted_and_normalized() -> None:
    config = ProviderConfig(provider_type="openai", base_url="HTTP://Example.com:8080/v1/")
    assert config.base_url == "http://Example.com:8080/v1"
    assert (
        ProviderConfig(provider_type="openai", base_url="HtTpS://example.com/v1").base_url
        == "https://example.com/v1"
    )


@pytest.mark.parametrize("value", ["ftp://example.com", "example.com", "HTTPX://example.com"])
def test_other_schemes_still_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(provider_type="openai", base_url=value)


@pytest.mark.parametrize("field", ["default_model", "credential_env", "response_format"])
def test_control_characters_still_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(provider_type="openai", **{field: "ab\ncd"})
