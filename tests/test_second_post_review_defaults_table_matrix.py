"""Table-driven V1 defaults round-trip and single-write rollback qualification."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from deeper_dive.user_config import UserConfig, UserConfigError, UserConfigStore


_DEFAULT_CASES = [
    ("research_policy", " Useful ", "useful", "dangerous"),
    ("quick_deep_dive_research_policy", " OFF ", "off", "dangerous"),
    ("quick_deep_dive_duration_minutes", " 24 ", "24", "0"),
    (
        "quick_deep_dive_host_presets",
        "skeptic, moderator",
        "skeptic,moderator",
        "nonexistent",
    ),
    ("local_only", " YeS ", "yes", "sometimes"),
    ("network_policy", " Configured Providers ", "configured-providers", "unsupported"),
    ("diagnostic_logging", " VERBOSE ", "verbose", "trace"),
    ("speech_setup", " Deferred ", "deferred", "maybe"),
    ("ffmpeg_executable", " /bin/ffmpeg ", "/bin/ffmpeg", "/bin/\tescape"),
    ("kitten_model_dir", " /models/kitten ", "/models/kitten", "/models/\x1bescape"),
    ("tts_provider", " speech ", "speech", "speech\rsecret"),
    ("tts_voice", " voice-a ", "voice-a", "voice-a\nsecret"),
    ("tts_voice_host_1", " voice-1 ", "voice-1", "voice-1\x7fsecret"),
    ("tts_voice_host_2", " voice-2 ", "voice-2", "voice-2\tsecret"),
    ("host_generation", " llm:model-a ", "llm:model-a", "missing-provider"),
]


@pytest.mark.parametrize(("key", "valid", "expected", "invalid"), _DEFAULT_CASES)
def test_v1_defaults_good_bad_blank_restart_and_single_write(
    tmp_path, key: str, valid: str, expected: str, invalid: str
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={"legacy_extension": " keep exact legacy whitespace "}))

    candidate = store.load()
    candidate.defaults[key] = valid
    with patch.object(store, "_write_temporary", wraps=store._write_temporary) as writer:
        store.save(candidate)
        assert writer.call_count == 1

        persisted = store.load()
        assert persisted.defaults[key] == expected
        assert persisted.defaults["legacy_extension"] == " keep exact legacy whitespace "
        original_bytes = store.path.read_bytes()

        persisted.defaults[key] = invalid
        with pytest.raises(UserConfigError):
            store.save(persisted)
        assert writer.call_count == 1
        assert store.path.read_bytes() == original_bytes

        unchanged = store.load()
        unchanged.defaults[key] = ""
        store.save(unchanged)
        assert writer.call_count == 2
    reopened = UserConfigStore(store.path).load()
    assert reopened.defaults[key] == ""
    assert reopened.defaults["legacy_extension"] == " keep exact legacy whitespace "
