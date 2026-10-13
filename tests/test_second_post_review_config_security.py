from __future__ import annotations

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.diagnostics import export_diagnostic_bundle, redact
from deeper_dive.hosts import preset_names
from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.research_policy import ResearchMode, ResearchPolicyStore
from deeper_dive.settings_screen import SettingsController
from deeper_dive.storage.database import Database
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


@pytest.mark.parametrize(
    "query",
    [
        "api.key=provider-query-canary",
        "api%2Ekey=provider-query-canary",
        "api%252Ekey=provider-query-canary",
        "session.Token=provider-query-canary",
        "client.secret=provider-query-canary",
        "safe=1&%2561pi_key=provider-query-canary",
        "safe=1&%252561pi_key=provider-query-canary",
    ],
)
def test_provider_rejects_encoded_and_dotted_credential_query_keys(query: str) -> None:
    with pytest.raises(ValueError, match="credential query") as error:
        ProviderConfig(provider_type="openai", base_url=f"https://example.test/v1?{query}")
    assert "provider-query-canary" not in str(error.value)


def test_mutated_provider_encoded_query_key_rejected_before_store_write(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(providers={"remote": ProviderConfig(provider_type="openai")}))
    original = store.path.read_bytes()
    candidate = store.load()
    candidate.providers[
        "remote"
    ].base_url = "https://example.test/v1?api%252Ekey=mutated-query-canary"
    with pytest.raises(UserConfigError, match="providers") as error:
        store.save(candidate)
    assert "mutated-query-canary" not in str(error.value)
    assert store.path.read_bytes() == original


def test_provider_accepts_benign_dotted_and_encoded_query_keys() -> None:
    url = "https://example.test/v1?release.version=1.2.3&%73ection=overview"
    assert ProviderConfig(provider_type="openai", base_url=url).base_url == url


@pytest.mark.parametrize(
    "query",
    [
        "api[key]=punctuation-query-canary",
        "api+key=punctuation-query-canary",
        "api/key=punctuation-query-canary",
        "client[secret]=punctuation-query-canary",
        "session+token=punctuation-query-canary",
        "access/token=punctuation-query-canary",
        "api%5Bkey%5D=punctuation-query-canary",
    ],
)
def test_punctuated_credential_query_keys_redacted_and_rejected(query: str) -> None:
    endpoint = f"https://example.test/v1?{query}"
    message = f"GET {endpoint} status=401"
    sanitized = str(redact(message))
    assert "punctuation-query-canary" not in sanitized
    assert "[REDACTED]" in sanitized
    assert "status=401" in sanitized
    with pytest.raises(ValueError, match="credential query") as error:
        ProviderConfig(provider_type="openai", base_url=endpoint)
    assert "punctuation-query-canary" not in str(error.value)


def test_punctuated_query_credentials_redacted_across_diagnostic_surfaces(tmp_path) -> None:
    from deeper_dive.diagnostics import (
        DiagnosticEvent,
        StructuredDiagnosticLog,
        sanitize_exception_message,
    )

    canary = "punctuation-diagnostics-canary"
    endpoint = f"https://example.test/v1?api[key]={canary}"
    benign = "https://example.test/docs?release.version=1.2.3&section=overview"
    nested = {"requests": [{"endpoint": endpoint}, {"endpoint": benign}]}
    sanitized = str(redact(nested))
    assert canary not in sanitized
    assert benign in sanitized

    try:
        try:
            raise ValueError(f"provider request failed: {endpoint}")
        except ValueError as cause:
            raise RuntimeError("outer request failed") from cause
    except RuntimeError as exc:
        safe = sanitize_exception_message(exc)
    assert canary not in safe
    assert "caused by:" in safe
    assert "[REDACTED]" in safe

    log_path = tmp_path / "events.jsonl"
    StructuredDiagnosticLog(log_path).emit(
        DiagnosticEvent(level="error", event="provider_error", details=nested)
    )
    log = log_path.read_text(encoding="utf-8")
    assert canary not in log
    assert benign in log

    bundle_path = export_diagnostic_bundle(
        tmp_path / "bundle.json",
        provider_diagnostics=nested,
    )
    bundle = bundle_path.read_text(encoding="utf-8")
    assert canary not in bundle
    assert benign in bundle


@pytest.mark.parametrize("mode", tuple(ResearchMode))
def test_research_mode_production_contract_round_trip(tmp_path, mode: ResearchMode) -> None:
    data_dir = tmp_path / "data"
    store = UserConfigStore(data_dir / "config.json")
    settings = SettingsController(ProviderController(store, LLMProviderRegistry(), {}))
    settings.save_research_defaults(mode.value, "local-only")
    settings.save_quick_deep_dive_defaults("15", "curious_explainer,skeptic", mode.value)

    reopened = UserConfigStore(data_dir / "config.json").load()
    assert reopened.defaults["research_policy"] == mode.value
    assert reopened.defaults["quick_deep_dive_research_policy"] == mode.value
    service = DeeperDiveService(WorkspaceManager(data_dir))
    project = service.create_project("Research contract round trip")
    episode = service.quick_deep_dive(project.id)
    persisted = ResearchPolicyStore(
        Database(service.workspaces.project_root(project.id) / "project.db")
    )
    assert persisted.episode(project.id, episode.id).mode is mode


@pytest.mark.parametrize("preset", preset_names())
def test_each_production_host_preset_is_valid_in_settings_and_quick(tmp_path, preset: str) -> None:
    data_dir = tmp_path / "data"
    store = UserConfigStore(data_dir / "config.json")
    settings = SettingsController(ProviderController(store, LLMProviderRegistry(), {}))
    settings.save_quick_deep_dive_defaults("20", f"{preset},skeptic", "useful")
    reopened = UserConfigStore(data_dir / "config.json").load()
    assert reopened.defaults["quick_deep_dive_host_presets"] == f"{preset},skeptic"

    service = DeeperDiveService(WorkspaceManager(data_dir))
    project = service.create_project("Preset contract round trip")
    episode = service.quick_deep_dive(project.id)
    config = service.hosts(project.id).get_episode(episode.id)
    assert config is not None and config.target_duration_seconds == 1200
    hosts = {host.id: host for host in service.hosts(project.id).list_hosts(project.id)}
    selected = service.hosts(project.id).list_episode_host_ids(episode.id)
    assert [hosts[host_id].preset_origin for host_id in selected] == [preset, "skeptic"]


@pytest.mark.parametrize(
    "query",
    [
        "safe=1;api%5Fkey=semicolon-query-canary",
        "safe=1;session.Token=semicolon-query-canary",
        "safe=1&lang=en;client%2Esecret=semicolon-query-canary",
        "safe=1;api[key]=semicolon-query-canary",
    ],
)
def test_semicolon_separated_credentials_rejected_and_redacted(query: str) -> None:
    endpoint = f"https://example.test/v1?{query}"
    sanitized = str(redact(f"GET {endpoint} status=401"))
    assert "semicolon-query-canary" not in sanitized
    assert "safe=1" in sanitized
    assert "status=401" in sanitized
    with pytest.raises(ValueError, match="credential query") as error:
        ProviderConfig(provider_type="openai", base_url=endpoint)
    assert "semicolon-query-canary" not in str(error.value)


def test_nested_semicolon_credential_url_redacted_in_diagnostic_bundle(tmp_path) -> None:
    canary = "nested-semicolon-canary"
    encoded_redirect = f"https%3A%2F%2Fother.example%2F%3Fsafe%3D1%3Bapi%255Fkey%3D{canary}"
    nested = f"https://example.test/v1?redirect={encoded_redirect}&section=overview"
    payload = export_diagnostic_bundle(
        tmp_path / "nested-semicolon.json",
        provider_diagnostics={"request": nested},
    ).read_text(encoding="utf-8")
    assert canary not in payload
    assert "[REDACTED]" in payload
    assert "section=overview" in payload


def test_benign_semicolon_query_preserved() -> None:
    endpoint = "https://example.test/docs?filter=kind;type&section=overview"
    assert ProviderConfig(provider_type="openai", base_url=endpoint).base_url == endpoint
    assert redact(f"GET {endpoint} status=200") == f"GET {endpoint} status=200"


@pytest.mark.parametrize(
    "fragment",
    [
        "api%5Fkey:colon-fragment-canary",
        "api%255Fkey%3Acolon-fragment-canary",
        "session.Token%3Acolon-fragment-canary",
        "safe=1;api%255Fkey%3Acolon-fragment-canary",
    ],
)
def test_encoded_colon_credential_fragments_are_redacted(fragment: str) -> None:
    url = f"https://example.test/v1#{fragment}"
    sanitized = str(redact(f"GET {url} status=401"))
    assert "colon-fragment-canary" not in sanitized
    assert "#[REDACTED]" in sanitized
    assert "status=401" in sanitized

    with pytest.raises(ValueError, match="fragments") as error:
        ProviderConfig(provider_type="openai", base_url=url)
    assert "colon-fragment-canary" not in str(error.value)


def test_colon_fragment_in_nested_encoded_redirect_is_redacted_in_bundle(tmp_path) -> None:
    nested = (
        "https://example.test/v1?redirect="
        "https%3A%2F%2Fother.example%2F%23api%255Fkey%3Aredirect-colon-canary"
        "&section=overview"
    )
    payload = export_diagnostic_bundle(
        tmp_path / "colon-fragment.json",
        provider_diagnostics={"request": nested},
    ).read_text(encoding="utf-8")
    assert "redirect-colon-canary" not in payload
    assert "[REDACTED]" in payload
    assert "section=overview" in payload


def test_benign_colon_fragment_is_preserved_in_diagnostics() -> None:
    url = "https://example.test/docs#section%3Aoverview"
    assert redact(f"GET {url} status=200") == f"GET {url} status=200"


@pytest.mark.parametrize("entry_point", ["load", "save", "provider-controller"])
def test_config_validation_error_locations_never_echo_provider_mapping_keys(
    tmp_path, entry_point: str
) -> None:
    import json

    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={"research_policy": "off"}))
    original_bytes = store.path.read_bytes()
    untrusted_provider = "https://provider.example.test/#access_token=provider-key-canary"
    malformed_url = "https://provider.example.test/v1#token=invalid-url-canary"

    if entry_point == "load":
        store.path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "providers": {
                        untrusted_provider: {"provider_type": "openai", "base_url": malformed_url}
                    },
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(UserConfigError, match="providers") as error:
            store.load()
    else:
        candidate = store.load()
        candidate.providers[untrusted_provider] = ProviderConfig(provider_type="fake")
        candidate.providers[untrusted_provider].base_url = malformed_url
        with pytest.raises(UserConfigError, match="providers") as error:
            if entry_point == "save":
                store.save(candidate)
            else:
                ProviderController(store, LLMProviderRegistry(), {})._commit_candidate(candidate)
        assert store.path.read_bytes() == original_bytes

    assert "provider-key-canary" not in str(error.value)
    assert "invalid-url-canary" not in str(error.value)
    assert "base_url" in str(error.value)


@pytest.mark.parametrize("field", ["top-level", "provider-field"])
def test_invalid_config_unknown_field_names_are_not_echoed(tmp_path, field: str) -> None:
    import json

    canary = "untrusted-schema-field-CANARY"
    config: dict[str, object] = {"schema_version": 1, "providers": {}}
    if field == "top-level":
        config[canary] = "invalid"
    else:
        config["providers"] = {"fixture-provider": {"provider_type": "fake", canary: "invalid"}}
    store = UserConfigStore(tmp_path / "config.json")
    store.path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(UserConfigError, match="invalid user configuration") as error:
        store.load()
    assert canary not in str(error.value)


@pytest.mark.parametrize("valid", ["wav", " WAV ", "Mp3", "flac", "aac", "opus", "pcm"])
def test_provider_response_format_matches_runtime_supported_formats(valid: str) -> None:
    provider = ProviderConfig(provider_type="openai-compatible-tts", response_format=valid)
    assert provider.response_format == valid.strip().lower()


@pytest.mark.parametrize("mutation_path", ["store", "provider-controller"])
def test_invalid_provider_response_format_rejected_before_persistence(
    tmp_path, mutation_path: str
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(
        UserConfig(
            providers={
                "speech": ProviderConfig(
                    provider_type="openai-compatible-tts", response_format="wav"
                )
            }
        )
    )
    original = store.path.read_bytes()
    candidate = store.load()
    canary = "format-canary-never-store"
    candidate.providers["speech"].response_format = canary
    with pytest.raises(UserConfigError, match="response_format") as error:
        if mutation_path == "store":
            store.save(candidate)
        else:
            ProviderController(store, LLMProviderRegistry(), {})._commit_candidate(candidate)
    assert canary not in str(error.value)
    assert store.path.read_bytes() == original


def test_provider_response_format_rejected_on_load_without_echo(tmp_path) -> None:
    import json

    store = UserConfigStore(tmp_path / "config.json")
    canary = "invalid-response-format-canary"
    store.path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": {
                    "speech": {
                        "provider_type": "openai-compatible-tts",
                        "response_format": canary,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(UserConfigError, match="response_format") as error:
        store.load()
    assert canary not in str(error.value)


@pytest.mark.parametrize("field", ("provider_type", "credential_env", "response_format"))
@pytest.mark.parametrize("control", ("\n", "\r", "\x1b", "\x00"))
def test_provider_controller_rejects_raw_controls_before_normalization(
    tmp_path, field: str, control: str
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={"research_policy": "off"}))
    original = store.path.read_bytes()
    controller = ProviderController(store, LLMProviderRegistry(), {})
    provider_type = "openai"
    arguments: dict[str, str] = {}
    if field == "provider_type":
        provider_type += control
    elif field == "credential_env":
        arguments["credential_env"] = "API_TOKEN" + control
    else:
        provider_type = "openai-compatible-tts"
        arguments["response_format"] = "wav" + control

    with pytest.raises(ValueError, match="single-line") as error:
        controller.save_provider("remote", provider_type, **arguments)
    submitted = provider_type if field == "provider_type" else arguments[field]
    assert submitted not in str(error.value)
    assert store.path.read_bytes() == original
    assert "remote" not in store.load().providers


def test_provider_controller_preserves_printable_whitespace_normalization(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    controller = ProviderController(store, LLMProviderRegistry(), {})
    controller.save_provider(
        "remote",
        "  openai  ",
        credential_env="  API_TOKEN  ",
        response_format=" WAV ",
    )
    reopened = store.load().providers["remote"]
    assert reopened.provider_type == "openai"
    assert reopened.credential_env == "API_TOKEN"
    assert reopened.response_format == "wav"
