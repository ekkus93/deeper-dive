from __future__ import annotations

import pytest

from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigError, UserConfigStore


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("timeout_seconds", -1.0),
        ("response_format", "invalid-format"),
        ("network_scope", "invalid-scope"),
    ],
)
def test_store_revalidates_mutated_provider_without_changing_disk(
    tmp_path, field: str, invalid: object
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(providers={"local": ProviderConfig(provider_type="fake")}))
    original = store.path.read_bytes()
    candidate = store.load()
    setattr(candidate.providers["local"], field, invalid)

    with pytest.raises(UserConfigError, match="providers") as error:
        store.save(candidate)

    assert field in str(error.value)
    assert str(invalid) not in str(error.value)
    assert store.path.read_bytes() == original


def test_store_revalidates_mutated_network_default_without_changing_disk(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={"network_policy": "local-only"}))
    original = store.path.read_bytes()
    candidate = store.load()
    candidate.defaults["network_policy"] = "invalid-network-default"

    with pytest.raises(UserConfigError, match="defaults") as error:
        store.save(candidate)

    assert "invalid-network-default" not in str(error.value)
    assert store.path.read_bytes() == original
