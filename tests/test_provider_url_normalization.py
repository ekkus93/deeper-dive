"""Regression coverage for provider endpoint path-only normalization."""

from __future__ import annotations

import pytest

from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.test/v1/", "https://example.test/v1"),
        ("https://example.test/v1/?page=2", "https://example.test/v1?page=2"),
        ("https://example.test/v1?prefix=folder/", "https://example.test/v1?prefix=folder/"),
        ("https://example.test/v1/?prefix=folder//", "https://example.test/v1?prefix=folder//"),
        ("http://[::1]:8080/v1/?next=/docs/", "http://[::1]:8080/v1?next=/docs/"),
        ("https://example.test/v1/?", "https://example.test/v1?"),
        (
            "https://example.test/v1/?redirect=https%3A%2F%2Fother.test%2F",
            "https://example.test/v1?redirect=https%3A%2F%2Fother.test%2F",
        ),
    ],
)
def test_provider_url_preserves_query_values(raw: str, expected: str) -> None:
    assert ProviderConfig(provider_type="openai", base_url=raw).base_url == expected


def test_provider_url_query_survives_config_round_trip(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    raw = "https://example.test/v1/?redirect=https%3A%2F%2Fother.test%2F"
    store.save(UserConfig(providers={"remote": ProviderConfig(provider_type="openai", base_url=raw)}))
    assert store.load().providers["remote"].base_url == (
        "https://example.test/v1?redirect=https%3A%2F%2Fother.test%2F"
    )
