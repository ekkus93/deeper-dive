"""Nested endpoint validation regression coverage."""

from urllib.parse import quote

import pytest

from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigError, UserConfigStore


@pytest.mark.parametrize("levels", [1, 2])
def test_sensitive_nested_endpoint_is_rejected(levels: int) -> None:
    nested = "https://nested.example/v1?api_key=sample-marker"
    for _ in range(levels):
        nested = quote(nested, safe="")
    endpoint = f"https://provider.example/v1?redirect={nested}"
    with pytest.raises(ValueError, match="sensitive nested endpoint") as caught:
        ProviderConfig(provider_type="openai", base_url=endpoint)
    assert "sample-marker" not in str(caught.value)


def test_benign_nested_endpoint_remains_valid() -> None:
    nested = quote("https://nested.example/docs?section=overview", safe="")
    endpoint = f"https://provider.example/v1?redirect={nested}"
    assert ProviderConfig(provider_type="openai", base_url=endpoint).base_url == endpoint


def test_mutated_nested_endpoint_is_revalidated_before_save(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(providers={"remote": ProviderConfig(provider_type="openai")}))
    original = store.path.read_bytes()
    candidate = store.load()
    nested = quote("https://nested.example/v1?api_key=sample-marker", safe="")
    candidate.providers["remote"].base_url = f"https://provider.example/v1?redirect={nested}"
    with pytest.raises(UserConfigError, match="providers"):
        store.save(candidate)
    assert store.path.read_bytes() == original
