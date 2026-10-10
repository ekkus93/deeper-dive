from __future__ import annotations

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.diagnostics import export_diagnostic_bundle, redact
from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigError, UserConfigStore


@pytest.mark.parametrize(
    "key",
    ["research_policy", "quick_deep_dive_research_policy"],
)
def test_invalid_research_defaults_are_rejected(key: str) -> None:
    with pytest.raises(ValueError, match=key):
        UserConfig(defaults={key: "reckless"})


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_invalid_quick_duration_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        UserConfig(defaults={"quick_deep_dive_duration_minutes": value})


@pytest.mark.parametrize(
    "value",
    ["skeptic", "skeptic,not-a-preset", "not-a-preset,curious_explainer"],
)
def test_invalid_quick_host_presets_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="exactly two valid host presets"):
        UserConfig(defaults={"quick_deep_dive_host_presets": value})


def test_valid_semantic_defaults_are_normalized() -> None:
    config = UserConfig(
        defaults={
            "research_policy": " Useful ",
            "quick_deep_dive_research_policy": "OFF",
            "quick_deep_dive_duration_minutes": " 25 ",
            "quick_deep_dive_host_presets": "skeptic, curious_explainer",
            "local_only": " YES ",
            "legacy_free_form": " preserve me ",
        }
    )
    assert config.defaults["research_policy"] == "useful"
    assert config.defaults["quick_deep_dive_research_policy"] == "off"
    assert config.defaults["quick_deep_dive_duration_minutes"] == "25"
    assert config.defaults["quick_deep_dive_host_presets"] == "skeptic,curious_explainer"
    assert config.defaults["local_only"] == "yes"
    assert config.defaults["legacy_free_form"] == " preserve me "


def test_mutated_invalid_default_cannot_bypass_validation_at_save(tmp_path) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    config = UserConfig(defaults={"research_policy": "useful"})
    store.save(config)
    original = path.read_bytes()

    config.defaults["research_policy"] = "secretly-invalid"
    with pytest.raises(UserConfigError, match="defaults"):
        store.save(config)

    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/v1#access_token=fragment-secret",
        "https://example.test/v1#ACCESS_TOKEN=fragment-secret",
        "https://example.test/v1#%61ccess_token%3Dfragment-secret",
        "http://[::1]:8080/v1#section",
        "https://example.test/v1#",
    ],
)
def test_provider_base_url_rejects_fragments_without_echo(url: str) -> None:
    with pytest.raises(ValueError) as info:
        ProviderConfig(provider_type="openai", base_url=url)
    assert "fragment-secret" not in str(info.value)
    assert "fragment" in str(info.value).lower()


@pytest.mark.parametrize(
    "message",
    [
        "GET https://example.test/v1#access_token=fragment-canary",
        "GET https://example.test/v1#ACCESS_TOKEN=fragment-canary",
        "GET https://example.test/v1#%61ccess_token%3Dfragment-canary",
        "GET https://example.test/v1#safe=1&token=fragment-canary",
        "GET https://example.test/v1#client_secret%3Dfragment-canary",
        "GET https://example.test/v1#sessionToken%3Dfragment-canary",
        "GET https://example.test/v1#access-token%3Dfragment-canary",
    ],
)
def test_diagnostic_url_fragment_credentials_are_redacted(message: str) -> None:
    safe = str(redact(message))
    assert "fragment-canary" not in safe
    assert "#[REDACTED]" in safe


def test_benign_diagnostic_url_fragment_is_preserved() -> None:
    message = "See https://example.test/docs#installation for details"
    assert redact(message) == message


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("network_policy", "definitely-not-a-policy"),
        ("diagnostic_logging", "trace-every-secret"),
        ("speech_setup", "maybe"),
        ("local_only", "sometimes"),
        ("episode_planning", "missing-separator"),
        ("host_generation", ":missing-provider"),
        ("verification", "missing-model:"),
    ],
)
def test_documented_semantic_defaults_reject_invalid_values(key: str, value: str) -> None:
    with pytest.raises(ValueError):
        UserConfig(defaults={key: value})


def test_documented_defaults_normalize_without_rejecting_legacy_extension_keys() -> None:
    config = UserConfig(
        defaults={
            "network_policy": "Configured Providers",
            "diagnostic_logging": " VERBOSE ",
            "speech_setup": " CONFIGURED ",
            "ffmpeg_executable": " ffmpeg-custom ",
            "kitten_model_dir": " /models/kitten ",
            "local_provider_ids": " local-a, local-b ,",
            "episode_planning": " planner : model-a ",
            "legacy_extension": " preserve exact legacy value ",
        }
    )
    assert config.defaults["network_policy"] == "configured-providers"
    assert config.defaults["diagnostic_logging"] == "verbose"
    assert config.defaults["speech_setup"] == "configured"
    assert config.defaults["ffmpeg_executable"] == "ffmpeg-custom"
    assert config.defaults["kitten_model_dir"] == "/models/kitten"
    assert config.defaults["local_provider_ids"] == "local-a,local-b"
    assert config.defaults["episode_planning"] == "planner:model-a"
    assert config.defaults["legacy_extension"] == " preserve exact legacy value "


@pytest.mark.parametrize("key", ["ffmpeg_executable", "kitten_model_dir"])
@pytest.mark.parametrize("value", ["bad\x00path", "bad\npath", "bad\rpath"])
def test_path_defaults_reject_control_characters(key: str, value: str) -> None:
    with pytest.raises(ValueError, match="single filesystem path"):
        UserConfig(defaults={key: value})


def test_settings_accepted_quick_defaults_are_consumable_after_restart(tmp_path) -> None:
    data_dir = tmp_path / "data"
    store = UserConfigStore(data_dir / "config.json")
    controller = SettingsController(ProviderController(store, LLMProviderRegistry(), {}))
    controller.save_research_defaults("useful", "local-only")
    controller.save_quick_deep_dive_defaults(
        "25",
        "skeptic,curious_explainer",
        "off",
    )
    controller.save_runtime_defaults("ffmpeg", "/models/kitten", "verbose")

    # Re-open through production services rather than reusing the Settings object.
    service = DeeperDiveService(WorkspaceManager(data_dir))
    project = service.create_project("Quick defaults consumer")
    episode = service.quick_deep_dive(project.id)
    config = service.hosts(project.id).get_episode(episode.id)
    assert config is not None
    assert config.target_duration_seconds == 25 * 60
    hosts = service.hosts(project.id).list_hosts(project.id)
    assert [host.preset_origin for host in hosts] == ["curious_explainer", "skeptic"] or {
        host.preset_origin for host in hosts
    } == {"curious_explainer", "skeptic"}
    persisted = UserConfigStore(data_dir / "config.json").load()
    assert persisted.defaults["quick_deep_dive_research_policy"] == "off"
    assert persisted.defaults["network_policy"] == "local-only"
    assert persisted.defaults["diagnostic_logging"] == "verbose"


def test_multiple_and_encoded_fragment_canaries_redact_without_destroying_context() -> None:
    message = (
        "first=https://one.example/docs#install "
        "second=https://two.example/v1#%61ccess_token%3Dfragment-two "
        "third=https://three.example/v1#safe%3D1%26ToKeN%3Dfragment-three "
        "status=401"
    )
    safe = str(redact(message))
    assert "fragment-two" not in safe
    assert "fragment-three" not in safe
    assert "one.example/docs#install" in safe
    assert "two.example/v1#[REDACTED]" in safe
    assert "three.example/v1#[REDACTED]" in safe
    assert "status=401" in safe


def test_diagnostic_bundle_redacts_nested_fragment_credentials(tmp_path) -> None:
    secret = "fragment-bundle-canary"
    destination = export_diagnostic_bundle(
        tmp_path / "diagnostics.json",
        provider_diagnostics={
            "endpoint": f"https://example.test/v1#access_token={secret}",
            "nested": [
                f"https://example.test/v1#%61uthorization%3D{secret}",
                "https://example.test/docs#safe-anchor",
            ],
        },
        configuration={"safe": "context"},
    )
    payload = destination.read_bytes()
    assert secret.encode() not in payload
    assert b"safe-anchor" in payload
    assert b"[REDACTED]" in payload


def test_rejected_fragment_provider_mutation_never_reaches_config_bytes(tmp_path) -> None:
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    store.save(UserConfig(defaults={"research_policy": "useful"}))
    original = path.read_bytes()
    controller = ProviderController(store, LLMProviderRegistry(), {})
    secret = "fragment-save-canary"

    with pytest.raises(ValueError):
        controller.save_provider(
            "remote",
            "openai",
            base_url=f"https://example.test/v1#access_token={secret}",
            default_model="model-a",
        )

    assert path.read_bytes() == original
    assert secret.encode() not in path.read_bytes()


@pytest.mark.parametrize(
    "query",
    [
        "%61pi_key=encoded-query-canary",
        "api%5Fkey=encoded-query-canary",
        "%2561pi_key=encoded-query-canary",
        "session%54oken=encoded-query-canary",
        "safe=1&%61ccess_token=encoded-query-canary",
    ],
)
def test_encoded_credential_query_keys_redacted_without_leaking(query: str) -> None:
    message = f"request=https://example.test/v1?{query} status=401"
    sanitized = str(redact(message))
    assert "encoded-query-canary" not in sanitized
    assert "[REDACTED]" in sanitized
    assert "status=401" in sanitized


def test_benign_encoded_query_key_preserved() -> None:
    message = "request=https://example.test/docs?%73ection=overview&lang=en"
    assert redact(message) == message


def test_encoded_query_key_redacted_in_nested_diagnostic_bundle(tmp_path) -> None:
    secret = "encoded-bundle-canary"
    destination = export_diagnostic_bundle(
        tmp_path / "bundle.json",
        provider_diagnostics={
            "requests": [
                f"https://example.test/v1?api%5Fkey={secret}",
                "https://example.test/docs?%73ection=overview",
            ]
        },
    )
    payload = destination.read_text(encoding="utf-8")
    assert secret not in payload
    assert "section=overview" not in payload  # Original encoded spelling retained.
    assert "%73ection=overview" in payload


@pytest.mark.parametrize("mutation_path", ["store", "provider-controller"])
def test_mutated_provider_fragment_revalidated_before_any_write(
    tmp_path, mutation_path: str
) -> None:
    """Mutable Pydantic submodels must not bypass the original URL validator."""
    path = tmp_path / "config.json"
    store = UserConfigStore(path)
    store.save(
        UserConfig(
            providers={
                "remote": ProviderConfig(provider_type="openai", base_url="https://example.test/v1")
            }
        )
    )
    original = path.read_bytes()
    candidate = store.load()
    canary = "mutated-fragment-canary"
    candidate.providers["remote"].base_url = f"https://example.test/v1#access_token={canary}"
    with pytest.raises(UserConfigError, match="providers"):
        if mutation_path == "store":
            store.save(candidate)
        else:
            ProviderController(store, LLMProviderRegistry(), {})._commit_candidate(candidate)
    assert path.read_bytes() == original
    assert canary.encode() not in path.read_bytes()


def test_encoded_query_canaries_in_chained_errors_and_structured_log(tmp_path) -> None:
    from deeper_dive.diagnostics import (
        DiagnosticEvent,
        StructuredDiagnosticLog,
        sanitize_exception_message,
    )

    canary = "chained-query-canary"
    endpoint = f"https://example.test/v1?%2561pi_key={canary}"
    try:
        try:
            raise ValueError(f"provider request failed: {endpoint}")
        except ValueError as cause:
            raise RuntimeError("outer request failed") from cause
    except RuntimeError as exc:
        safe = sanitize_exception_message(exc)
    assert canary not in safe
    assert "outer request failed" in safe
    assert "caused by:" in safe
    assert "[REDACTED]" in safe

    path = tmp_path / "diagnostics.jsonl"
    StructuredDiagnosticLog(path).emit(
        DiagnosticEvent(
            level="error",
            event="provider_error",
            details={"nested": [{"endpoint": endpoint}]},
        )
    )
    log = path.read_text(encoding="utf-8")
    assert canary not in log
    assert "[REDACTED]" in log


@pytest.mark.parametrize(
    "query",
    [
        "api.key=dotted-query-canary",
        "api%2Ekey=dotted-query-canary",
        "api%252Ekey=dotted-query-canary",
        "client.secret=dotted-query-canary",
        "session.Token=dotted-query-canary",
    ],
)
def test_dotted_and_encoded_credential_query_keys_are_redacted(query: str) -> None:
    message = f"GET https://example.test/v1?{query} status=401"
    sanitized = str(redact(message))
    assert "dotted-query-canary" not in sanitized
    assert "[REDACTED]" in sanitized
    assert "status=401" in sanitized


def test_benign_dotted_query_key_is_preserved() -> None:
    message = "GET https://example.test/docs?release.version=1.2.3 status=200"
    assert redact(message) == message
