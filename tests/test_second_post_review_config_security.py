"""Second post-review configuration durability and credential-boundary regression tests."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from deeper_dive.diagnostics import redact, sanitize_provider_error
from deeper_dive.user_config import (
    ProviderConfig,
    UserConfig,
    UserConfigConflictError,
    UserConfigError,
    UserConfigStore,
)


@pytest.mark.parametrize(
    "url",
    (
        "https://api.example.test/v1#token=fragment-canary",
        "https://api.example.test/v1#ToKeN%3Dfragment-canary",
        "https://api.example.test/v1#API%255FKEY%253Dfragment-canary",
        "http://[::1]:11434/v1#password=fragment-canary",
        "http://127.0.0.1:8080/#",
    ),
)
def test_provider_endpoints_reject_all_url_fragments_without_echo(url: str) -> None:
    with pytest.raises(ValueError, match="base_url") as error:
        ProviderConfig(provider_type="ollama", base_url=url)
    assert "fragment-canary" not in str(error.value)


def test_provider_endpoint_keeps_ipv6_and_nonsecret_query() -> None:
    config = ProviderConfig(
        provider_type="ollama",
        base_url="http://[::1]:11434/v1?region=local&safe=true",
    )
    assert config.base_url == "http://[::1]:11434/v1?region=local&safe=true"


@pytest.mark.parametrize(
    "fragment",
    (
        "token=fragment-canary",
        "TOKEN%3Dfragment-canary",
        "API%255FKEY%253Dfragment-canary",
        "password%253Dfragment-canary",
        "SeCrEt%3Dfragment-canary",
    ),
)
def test_diagnostics_hide_layered_credential_fragments(fragment: str) -> None:
    message = (
        f"failed https://example.test/v1#{fragment} and http://127.0.0.1:8080/#section on retry"
    )
    sanitized = str(redact(message))
    assert "fragment-canary" not in sanitized
    assert "https://example.test/v1#[REDACTED]" in sanitized
    assert "http://127.0.0.1:8080/#section" in sanitized
    event = sanitize_provider_error("local", RuntimeError(message))
    assert "fragment-canary" not in event.message


def test_mutated_provider_fragment_is_rejected_before_any_write(tmp_path: Path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    config = UserConfig(providers={"local": ProviderConfig(provider_type="ollama")})
    store.save(config)
    before = store.path.read_bytes()
    config.providers["local"].base_url = "https://example.test/#token=fragment-canary"

    with pytest.raises(UserConfigError, match="providers") as error:
        store.save(config)
    assert "fragment-canary" not in str(error.value)
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("research_policy", "unknown"),
        ("quick_deep_dive_research_policy", "invalid"),
        ("quick_deep_dive_duration_minutes", "-2"),
        ("quick_deep_dive_host_presets", "skeptic"),
        ("network_policy", "all-networks"),
        ("local_only", "maybe"),
        ("diagnostic_logging", "maximum"),
    ),
)
def test_semantically_invalid_defaults_do_not_change_durable_bytes(
    tmp_path: Path, key: str, value: str
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig())
    loaded = store.load()
    previous = store.path.read_bytes()
    loaded.defaults[key] = value
    with pytest.raises(UserConfigError):
        store.save(loaded)
    assert store.path.read_bytes() == previous


def test_disjoint_stale_writers_conflict_and_can_retry_explicitly(tmp_path: Path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig())
    first = store.load()
    second = store.load()
    first.defaults["local_only"] = "yes"
    second.defaults["network_policy"] = "allow-remote"

    store.save(first)
    before = store.path.read_bytes()
    with pytest.raises(UserConfigConflictError, match="reload and retry"):
        store.save(second)
    assert store.path.read_bytes() == before

    refreshed = store.load()
    refreshed.defaults["network_policy"] = "allow-remote"
    store.save(refreshed)
    assert store.load().defaults == {
        "local_only": "yes",
        "network_policy": "allow-remote",
    }


def test_two_simultaneous_initial_writers_have_exactly_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    barrier = Barrier(2)

    def write(mode: str) -> str:
        config = UserConfigStore(path).load()
        config.defaults["research_policy"] = mode
        barrier.wait()
        try:
            UserConfigStore(path).save(config)
        except UserConfigConflictError:
            return "conflict"
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(write, "off")
        second = pool.submit(write, "useful")
        outcomes = {first.result(), second.result()}
    assert outcomes == {"saved", "conflict"}
    assert UserConfigStore(path).load().defaults["research_policy"] in {"off", "useful"}


def test_atomic_replace_failure_keeps_old_bytes_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig())
    original = store.path.read_bytes()
    candidate = store.load()
    candidate.defaults["research_policy"] = "off"

    def fail_replace(source: object, target: object) -> None:
        raise OSError("injected rename failure")

    monkeypatch.setattr("deeper_dive.user_config.os.replace", fail_replace)
    with pytest.raises(OSError, match="injected rename failure"):
        store.save(candidate)
    assert store.path.read_bytes() == original
    assert list(tmp_path.glob(".config.json.*.tmp")) == []


def test_temp_chmod_failure_preserves_durable_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig())
    original = store.path.read_bytes()
    candidate = store.load()
    candidate.defaults["research_policy"] = "off"

    def fail_chmod(path: Path) -> None:
        raise OSError("injected chmod failure")

    monkeypatch.setattr(store, "_restrict_permissions", fail_chmod)
    with pytest.raises(OSError, match="injected chmod failure"):
        store.save(candidate)
    assert store.path.read_bytes() == original
    assert list(tmp_path.glob(".config.json.*.tmp")) == []


def test_temp_sync_failure_keeps_old_bytes_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig())
    original = store.path.read_bytes()
    candidate = store.load()
    candidate.defaults["research_policy"] = "useful"

    def fail_fsync(fd: int) -> None:
        raise OSError("injected temp fsync failure")

    monkeypatch.setattr("deeper_dive.user_config.os.fsync", fail_fsync)
    with pytest.raises(OSError, match="injected temp fsync failure"):
        store.save(candidate)
    assert store.path.read_bytes() == original
    assert list(tmp_path.glob(".config.json.*.tmp")) == []


def test_directory_sync_failure_reports_uncertain_durability_without_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig())
    candidate = store.load()
    candidate.defaults["research_policy"] = "aggressive"

    def fail_directory_sync() -> None:
        raise OSError("injected directory fsync failure")

    monkeypatch.setattr(store, "_sync_parent_directory", fail_directory_sync)
    with pytest.raises(OSError, match="injected directory fsync failure"):
        store.save(candidate)
    assert store.load().defaults["research_policy"] == "aggressive"
    assert list(tmp_path.glob(".config.json.*.tmp")) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlink and mode semantics")
def test_fixed_temp_symlink_canary_remains_untouched(tmp_path: Path) -> None:
    target = tmp_path / "symlink-canary.txt"
    target.write_text("do not modify this file", encoding="utf-8")
    legacy_temp = tmp_path / "config.json.tmp"
    legacy_temp.symlink_to(target)
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={"research_policy": "off"}))
    assert target.read_text(encoding="utf-8") == "do not modify this file"
    assert legacy_temp.is_symlink()
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.glob(".config.json.*.tmp")) == []
