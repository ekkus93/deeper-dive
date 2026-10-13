"""Invalid V1 configuration reports safe recovery steps; legacy files remain usable."""

from __future__ import annotations

import json

import pytest

from deeper_dive.user_config import UserConfigError, UserConfigStore


@pytest.mark.parametrize(
    "payload",
    [
        "{ invalid-json-canary",
        json.dumps(
            {
                "schema_version": 99,
                "providers": {},
                "defaults": {"research_policy": "bad-value-canary"},
            }
        ),
        json.dumps(
            {
                "schema_version": 1,
                "providers": {},
                "defaults": {"network_policy": "invalid-network-canary"},
            }
        ),
    ],
)
def test_invalid_config_errors_are_actionable_and_never_echo_values(tmp_path, payload: str) -> None:
    path = tmp_path / "config.json"
    path.write_text(payload, encoding="utf-8")
    original = path.read_bytes()

    with pytest.raises(UserConfigError) as caught:
        UserConfigStore(path).load()
    message = str(caught.value)
    assert "repair the file or restore a valid backup" in message
    assert "canary" not in message
    assert path.read_bytes() == original


def test_legacy_bare_model_role_and_extension_survive_load_and_save(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": {},
                "defaults": {
                    "host_generation": "legacy-model.gguf",
                    "research_policy": "OFF",
                    "custom_legacy_extension": "retain-as-is",
                },
            }
        ),
        encoding="utf-8",
    )
    store = UserConfigStore(path)
    loaded = store.load()
    assert loaded.defaults["host_generation"] == "legacy-model.gguf"
    assert loaded.defaults["research_policy"] == "off"
    assert loaded.defaults["custom_legacy_extension"] == "retain-as-is"

    store.save(loaded)
    restarted = UserConfigStore(path).load()
    assert restarted.defaults == loaded.defaults


def test_new_bare_role_is_rejected_without_overwriting_loaded_legacy_file(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": {},
                "defaults": {"host_generation": "previous-model.gguf"},
            }
        ),
        encoding="utf-8",
    )
    store = UserConfigStore(path)
    loaded = store.load()
    original = path.read_bytes()
    loaded.defaults["host_generation"] = "new-bare-model"
    with pytest.raises(UserConfigError, match="defaults") as error:
        store.save(loaded)
    assert "new-bare-model" not in str(error.value)
    assert path.read_bytes() == original
