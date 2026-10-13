"""Regression coverage for persisted configuration key validation."""

import pytest

from deeper_dive.user_config import UserConfig


@pytest.mark.parametrize("key", ["research_policy", "network_policy"])
def test_known_default_keys_accept_valid_values(key: str) -> None:
    value = "useful" if key == "research_policy" else "local-only"
    assert UserConfig(defaults={key: value}).defaults[key] == value
