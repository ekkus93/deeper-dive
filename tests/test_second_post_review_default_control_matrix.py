"""Regression tests for control bytes in normalized semantic defaults."""

from __future__ import annotations

import pytest

from deeper_dive.user_config import UserConfig, UserConfigError, UserConfigStore


@pytest.mark.parametrize(
    ("key", "valid"),
    [
        ("research_policy", "useful"),
        ("quick_deep_dive_research_policy", "off"),
        ("quick_deep_dive_duration_minutes", "20"),
        ("quick_deep_dive_host_presets", "curious_explainer,skeptic"),
        ("local_only", "true"),
        ("network_policy", "local-only"),
        ("diagnostic_logging", "normal"),
        ("speech_setup", "configured"),
    ],
)
@pytest.mark.parametrize("control_code", [0, 9, 10, 13, 27, 127])
@pytest.mark.parametrize("prefix", [False, True])
def test_semantic_defaults_reject_controls_before_normalization(
    key: str, valid: str, control_code: int, prefix: bool
) -> None:
    character = chr(control_code)
    value = character + valid if prefix else valid + character
    with pytest.raises(ValueError, match="single-line") as caught:
        UserConfig(defaults={key: value})
    assert value not in str(caught.value)


@pytest.mark.parametrize("key", ["ffmpeg_executable", "kitten_model_dir"])
@pytest.mark.parametrize("control_code", [0, 9, 10, 13, 27, 127])
def test_runtime_path_defaults_reject_trailing_controls(key: str, control_code: int) -> None:
    with pytest.raises(ValueError, match="single filesystem path"):
        UserConfig(defaults={key: "/path/to/tool" + chr(control_code)})


@pytest.mark.parametrize(
    ("key", "valid"),
    [
        ("network_policy", "local-only"),
        ("quick_deep_dive_duration_minutes", "20"),
        ("ffmpeg_executable", "ffmpeg"),
    ],
)
def test_mutated_defaults_revalidated_before_write(tmp_path, key: str, valid: str) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={key: valid}))
    original = store.path.read_bytes()
    candidate = store.load()
    candidate.defaults[key] = valid + chr(10)
    with pytest.raises(UserConfigError):
        store.save(candidate)
    assert store.path.read_bytes() == original
    assert store.load().defaults[key] == valid


def test_printable_normalization_and_legacy_extensions_remain_compatible() -> None:
    config = UserConfig(
        defaults={
            "network_policy": " Configured Providers ",
            "research_policy": " USEFUL ",
            "ffmpeg_executable": " /usr/local/bin/ffmpeg ",
            "extension_custom": "line one" + chr(10) + "line two",
        }
    )
    assert config.defaults["network_policy"] == "configured-providers"
    assert config.defaults["research_policy"] == "useful"
    assert config.defaults["ffmpeg_executable"] == "/usr/local/bin/ffmpeg"
    assert config.defaults["extension_custom"] == "line one" + chr(10) + "line two"
