"""Worker ownership when the runtime cannot start readiness threads."""

from __future__ import annotations

from threading import Thread, Timer
from typing import cast

import pytest
from textual.message import Message

import deeper_dive.guided_async_readiness as readiness
from deeper_dive.guided_workflow import WizardContext


class _App:
    def post_message(self, message: Message) -> bool:
        return True


@pytest.mark.parametrize("failure", ["timer", "worker"])
def test_thread_start_failure_releases_worker_reservation(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    class FailedTimer(Timer):
        def start(self) -> None:
            raise RuntimeError("thread capacity exhausted")

    class FailedWorker(Thread):
        def start(self) -> None:
            raise RuntimeError("thread capacity exhausted")

    if failure == "timer":
        monkeypatch.setattr(readiness, "Timer", FailedTimer)
    else:
        monkeypatch.setattr(readiness, "Thread", FailedWorker)

    callbacks: list[str] = []
    coordinator = readiness.FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        probe=lambda: cast(readiness.FirstRunRuntimeSnapshot, object()),
        fingerprint=lambda: "current",
    )
    try:
        assert not coordinator.request(_App(), lambda: callbacks.append("failed"))
        assert coordinator.view.state == "failed"
        assert coordinator.view.message == "Unable to start provider readiness check. Retry."
        assert callbacks == ["failed"]
        assert coordinator.active_worker_count == 0
        assert coordinator.timeout_timer_count == 0
    finally:
        coordinator.close()
