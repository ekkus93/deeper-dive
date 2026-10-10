"""Controller-level concurrent configuration writes through the production store."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController
from deeper_dive.user_config import UserConfig, UserConfigConflictError, UserConfigStore


class _SynchronizedStore(UserConfigStore):
    """Synchronize commits after each controller has loaded its baseline."""

    def __init__(self, path: Path, barrier: Barrier) -> None:
        super().__init__(path)
        self.barrier = barrier

    def save(self, config: UserConfig) -> None:
        self.barrier.wait(timeout=10)
        super().save(config)


@pytest.mark.parametrize("same_key", (False, True))
def test_independent_settings_controllers_do_not_silently_clobber(
    tmp_path: Path, same_key: bool
) -> None:
    path = tmp_path / "config.json"
    UserConfigStore(path).save(UserConfig())
    barrier = Barrier(2)
    first = SettingsController(
        ProviderController(_SynchronizedStore(path, barrier), LLMProviderRegistry(), {})
    )
    second = SettingsController(
        ProviderController(_SynchronizedStore(path, barrier), LLMProviderRegistry(), {})
    )
    second_key = "research_policy" if same_key else "network_policy"
    second_value = "useful" if same_key else "local-only"

    def write(controller: SettingsController, key: str, value: str) -> str:
        try:
            controller.set_default(key, value)
        except UserConfigConflictError:
            return "conflict"
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_write = pool.submit(write, first, "research_policy", "off")
        second_write = pool.submit(write, second, second_key, second_value)
        first_result, second_result = first_write.result(), second_write.result()

    assert sorted((first_result, second_result)) == ["conflict", "saved"]
    persisted = UserConfigStore(path).load()
    if same_key:
        assert persisted.defaults["research_policy"] in {"off", "useful"}
    elif first_result == "saved":
        assert persisted.defaults == {"research_policy": "off"}
    else:
        assert persisted.defaults == {"network_policy": "local-only"}

    # An explicit retry must reload the other writer's state, not replay
    # a stale whole-config snapshot that drops unrelated settings.
    if first_result == "conflict":
        SettingsController(
            ProviderController(UserConfigStore(path), LLMProviderRegistry(), {})
        ).set_default("research_policy", "off")
    else:
        SettingsController(
            ProviderController(UserConfigStore(path), LLMProviderRegistry(), {})
        ).set_default(second_key, second_value)

    expected = {"research_policy": second_value if same_key and first_result == "saved" else "off"}
    if not same_key:
        expected["network_policy"] = "local-only"
    assert UserConfigStore(path).load().defaults == expected


def test_provider_and_settings_controller_race_is_detected_and_recoverable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.json"
    UserConfigStore(path).save(UserConfig())
    barrier = Barrier(2)
    provider = ProviderController(
        _SynchronizedStore(path, barrier), LLMProviderRegistry(), {}
    )
    settings = SettingsController(
        ProviderController(_SynchronizedStore(path, barrier), LLMProviderRegistry(), {})
    )

    def save_provider() -> str:
        try:
            provider.save_provider("fake-llm", "fake", default_model="fake-model")
        except UserConfigConflictError:
            return "conflict"
        return "saved"

    def save_settings() -> str:
        try:
            settings.set_default("local_only", "true")
        except UserConfigConflictError:
            return "conflict"
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        provider_future = pool.submit(save_provider)
        settings_future = pool.submit(save_settings)
        provider_result = provider_future.result()
        settings_result = settings_future.result()

    assert sorted((provider_result, settings_result)) == ["conflict", "saved"]
    intermediate = UserConfigStore(path).load()
    assert ("fake-llm" in intermediate.providers) != (
        "local_only" in intermediate.defaults
    )
    if provider_result == "conflict":
        ProviderController(
            UserConfigStore(path), LLMProviderRegistry(), {}
        ).save_provider("fake-llm", "fake", default_model="fake-model")
    else:
        SettingsController(
            ProviderController(UserConfigStore(path), LLMProviderRegistry(), {})
        ).set_default("local_only", "true")
    final = UserConfigStore(path).load()
    assert final.providers["fake-llm"].provider_type == "fake"
    assert final.defaults["local_only"] == "true"
