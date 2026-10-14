"""TPR-15: the readiness fingerprint never waits on the config advisory lock."""

from __future__ import annotations

from pathlib import Path
from queue import Queue
from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace
from typing import cast

from textual.message import Message

from deeper_dive.guided_async_readiness import (
    FirstRunReadinessCoordinator,
    FirstRunRuntimeSnapshot,
)
from deeper_dive.guided_workflow import WizardContext
from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import UserConfigStore


class _App:
    def __init__(self) -> None:
        self.messages: Queue[Message] = Queue()

    def post_message(self, message: Message) -> bool:
        self.messages.put(message)
        return True


def test_request_returns_promptly_while_another_thread_holds_the_config_lock(
    tmp_path: Path,
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(store.load())
    controller = ProviderController(store, LLMProviderRegistry(), {})
    context = cast(
        WizardContext,
        SimpleNamespace(composition=SimpleNamespace(provider_controller=controller)),
    )
    release = Event()
    holding = Event()

    def hold_lock() -> None:
        with store._locked():
            holding.set()
            release.wait(10)

    holder = Thread(target=hold_lock, daemon=True)
    holder.start()
    assert holding.wait(3)
    coordinator = FirstRunReadinessCoordinator(
        context,
        probe=lambda: cast(FirstRunRuntimeSnapshot, object()),
        timeout_seconds=5,
    )
    try:
        started = monotonic()
        coordinator.request(_App())
        assert monotonic() - started < 1.0
        assert coordinator.view.fingerprint is not None
    finally:
        release.set()
        holder.join(3)
        coordinator.close()
