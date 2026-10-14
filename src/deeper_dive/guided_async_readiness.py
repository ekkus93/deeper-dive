"""Non-blocking first-run runtime readiness for Textual surfaces."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from threading import Lock, Thread, Timer
from typing import Literal, Protocol

from textual.message import Message

from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.first_run import FirstRunController, FirstRunSystemCheck
from deeper_dive.guided_readiness import FirstRunDerivedReadiness, first_run_readiness
from deeper_dive.guided_workflow import WizardContext

_LOGGER = logging.getLogger(__name__)


def _notify(callbacks: Iterable[Callable[[], object]]) -> None:
    """Invoke each subscriber in isolation; one failure must not starve the rest."""

    for callback in callbacks:
        try:
            callback()
        except Exception as exc:  # subscriber boundary: UI callbacks are foreign code
            _LOGGER.warning("readiness subscriber failed: %s", sanitize_exception_message(exc))


_FIRST_RUN_STEPS = (
    "welcome",
    "system-check",
    "ai-provider",
    "provider-config",
    "model-test",
    "speech",
    "voice-defaults",
    "ready",
)


class FirstRunReadinessDispatch(Message):
    """Thread-safe request for one coordinator callback on Textual's UI loop."""

    def __init__(self, callback: Callable[..., object], args: tuple[object, ...]) -> None:
        super().__init__()
        self.callback = callback
        self.args = args

    def run(self) -> None:
        self.callback(*self.args)


class ThreadDispatchApp(Protocol):
    def post_message(self, message: Message) -> bool: ...


@dataclass(frozen=True, slots=True)
class FirstRunRuntimeSnapshot:
    readiness: FirstRunDerivedReadiness
    system_check: FirstRunSystemCheck


@dataclass(frozen=True, slots=True)
class FirstRunReadinessView:
    state: Literal["idle", "checking", "ready", "failed"]
    generation: int
    fingerprint: str | None
    snapshot: FirstRunRuntimeSnapshot | None = None
    message: str | None = None


class ReadinessRequestOutcome(Enum):
    """What ``FirstRunReadinessCoordinator.request`` did; truthy only when a probe started."""

    STARTED = "started"
    COALESCED = "coalesced"
    SATURATED = "saturated"
    CLOSED = "closed"
    CONFIG_UNREADABLE = "config-unreadable"
    START_FAILED = "start-failed"

    def __bool__(self) -> bool:
        return self is ReadinessRequestOutcome.STARTED


class FirstRunReadinessCoordinator:
    """Run provider/system probes away from Textual's UI thread.

    Refreshes are generation tagged. Duplicate requests for the same configuration
    are coalesced while pending, and a result for an older configuration is ignored.
    """

    def __init__(
        self,
        context: WizardContext,
        *,
        probe: Callable[[], FirstRunRuntimeSnapshot] | None = None,
        fingerprint: Callable[[], str] | None = None,
        timeout_seconds: float = 8.0,
        max_workers: int = 2,
    ) -> None:
        self.context = context
        self._probe = probe or self._probe_runtime
        self._fingerprint_provider = fingerprint or self._configuration_fingerprint
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        if not isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self.timeout_seconds = timeout_seconds
        self.max_workers = max_workers
        self._lock = Lock()
        self._view = FirstRunReadinessView("idle", 0, None)
        self._callbacks: list[Callable[[], object]] = []
        self._active_workers: set[int] = set()
        self._timers: dict[int, Timer] = {}
        self._closed = False

    @property
    def view(self) -> FirstRunReadinessView:
        with self._lock:
            return self._view

    @property
    def snapshot(self) -> FirstRunRuntimeSnapshot | None:
        return self.view.snapshot

    @property
    def active_worker_count(self) -> int:
        with self._lock:
            return len(self._active_workers)

    @property
    def timeout_timer_count(self) -> int:
        with self._lock:
            return len(self._timers)

    def close(self) -> None:
        """Stop accepting refreshes and cancel owned timeout timers.

        Python cannot safely kill an arbitrary blocked provider thread, so workers
        already inside provider code remain daemonized but are bounded by the
        configured worker budget and cannot publish after close.
        """

        with self._lock:
            if self._closed:
                return
            self._closed = True
            timers = tuple(self._timers.values())
            self._timers.clear()
            self._callbacks.clear()
            generation = self._view.generation + 1
            self._view = FirstRunReadinessView(
                "failed",
                generation,
                self._view.fingerprint,
                message="Provider readiness checking stopped.",
            )
        for timer in timers:
            timer.cancel()

    def completion(self, step_key: str) -> bool:
        """Completion probe that never performs runtime I/O on the UI thread."""
        snapshot = self.snapshot
        if snapshot is None:
            # Preserve a saved/current location while the background snapshot is
            # pending, but do not allow the current runtime-dependent step to
            # advance until fresh readiness is available.
            if step_key in {"welcome", "system-check", "ai-provider"}:
                return True
            try:
                return _FIRST_RUN_STEPS.index(step_key) < _FIRST_RUN_STEPS.index(
                    self.context.state.current_step
                )
            except ValueError:
                return False
        readiness = snapshot.readiness
        if step_key in {"welcome", "system-check", "ai-provider"}:
            return True
        if step_key == "provider-config":
            return readiness.llm_provider_ready
        if step_key == "model-test":
            return readiness.model_roles_ready
        if step_key == "speech":
            return readiness.speech_choice_made
        if step_key == "voice-defaults":
            return readiness.defaults_ready and (readiness.speech_deferred or readiness.audio_ready)
        if step_key == "ready":
            return readiness.setup_ready
        raise KeyError(step_key)

    def request(
        self,
        app: ThreadDispatchApp,
        callback: Callable[[], object] | None = None,
        *,
        user_initiated: bool = False,
    ) -> ReadinessRequestOutcome:
        """Start (or coalesce) a readiness probe; the outcome is truthy only when one started.

        Automatic refreshes are quiet when a failed check cannot be retried because
        every worker is still blocked. An explicit user Retry (``user_initiated``)
        instead publishes a visible "workers are still finishing" status and wakes
        subscribers, so the button never appears to do nothing. Policy: no queued or
        automatic retry; the user retries again once a slot frees.
        """
        # Once the screen/app has closed, do not read mutable or disk-backed
        # configuration merely to reject another readiness request.
        with self._lock:
            if self._closed:
                return ReadinessRequestOutcome.CLOSED
        try:
            fingerprint = self._fingerprint_provider()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._fingerprint_failed(exc, callback)
            return ReadinessRequestOutcome.CONFIG_UNREADABLE
        rejected = False
        rejected_callbacks: tuple[Callable[[], object], ...] = ()
        stale_timers: tuple[Timer, ...] = ()
        with self._lock:
            if self._closed:
                return ReadinessRequestOutcome.CLOSED
            if self._view.state == "checking" and self._view.fingerprint == fingerprint:
                if callback is not None and callback not in self._callbacks:
                    self._callbacks.append(callback)
                return ReadinessRequestOutcome.COALESCED
            if (
                not user_initiated
                and self._view.state == "failed"
                and self._view.fingerprint == fingerprint
                and len(self._active_workers) >= self.max_workers
            ):
                return ReadinessRequestOutcome.SATURATED
            generation = self._view.generation + 1
            # Superseded generations cannot publish; cancel their deadlines so
            # rapid refreshes cannot accumulate abandoned timeout timers.
            stale_timers = tuple(self._timers.values())
            self._timers.clear()
            if len(self._active_workers) >= self.max_workers:
                self._view = FirstRunReadinessView(
                    "failed",
                    generation,
                    fingerprint,
                    message=(
                        "Provider readiness workers are still finishing timed-out checks. "
                        "Retry after the provider timeout expires."
                    ),
                )
                # Superseding a coalesced pending generation must wake all
                # subscribers exactly once, even when no worker slot is free.
                rejected = True
                callbacks = list(self._callbacks)
                if callback is not None and callback not in callbacks:
                    callbacks.append(callback)
                rejected_callbacks = tuple(callbacks)
                self._callbacks.clear()
            else:
                self._view = FirstRunReadinessView("checking", generation, fingerprint)
                # A superseded pending generation's subscribers move to the new
                # generation, so each is notified exactly once when it settles.
                if callback is not None and callback not in self._callbacks:
                    self._callbacks.append(callback)
                self._active_workers.add(generation)
        for stale_timer in stale_timers:
            stale_timer.cancel()
        if rejected:
            _notify(rejected_callbacks)
            return ReadinessRequestOutcome.SATURATED
        # Timer installation below owns the reserved worker slot. A separate
        # unlocked view check could abandon a superseded slot without a worker.
        timer = Timer(
            self.timeout_seconds,
            self._dispatch_timeout,
            args=(app, generation, fingerprint),
        )
        timer.daemon = True
        with self._lock:
            if (
                self._closed
                or self._view.state != "checking"
                or self._view.generation != generation
            ):
                self._active_workers.discard(generation)
                return ReadinessRequestOutcome.CLOSED
            self._timers[generation] = timer
        try:
            timer.start()
        except (OSError, RuntimeError):
            self._start_failed(generation, timer)
            return ReadinessRequestOutcome.START_FAILED

        worker = Thread(
            target=self._run_probe,
            args=(app, generation, fingerprint),
            name=f"deeper-dive-readiness-{generation}",
            daemon=True,
        )
        try:
            worker.start()
        except (OSError, RuntimeError):
            self._start_failed(generation, timer)
            return ReadinessRequestOutcome.START_FAILED
        return ReadinessRequestOutcome.STARTED

    def _fingerprint_failed(
        self,
        error: Exception,
        callback: Callable[[], object] | None,
    ) -> None:
        """Surface a malformed/unreadable config without starting another worker."""
        with self._lock:
            if self._closed:
                return
            timers = tuple(self._timers.values())
            self._timers.clear()
            # A failed refresh supersedes any in-flight generation. Its
            # subscribers must be notified once, not silently abandoned.
            callbacks = list(self._callbacks)
            if callback is not None and callback not in callbacks:
                callbacks.append(callback)
            self._callbacks.clear()
            self._view = FirstRunReadinessView(
                "failed",
                self._view.generation + 1,
                None,
                message=(
                    "Provider configuration could not be read. "
                    + sanitize_exception_message(error)
                    + " Correct the configuration and retry."
                ),
            )
        for timer in timers:
            timer.cancel()
        _notify(callbacks)

    def _start_failed(self, generation: int, timer: Timer) -> None:
        """Release a reserved slot if the OS cannot start a timer or worker."""
        timer.cancel()
        with self._lock:
            self._timers.pop(generation, None)
            self._active_workers.discard(generation)
            if self._closed or self._view.generation != generation:
                return
            self._view = FirstRunReadinessView(
                "failed",
                generation,
                self._view.fingerprint,
                message="Unable to start provider readiness check. Retry.",
            )
            callbacks = tuple(self._callbacks)
            self._callbacks.clear()
        _notify(callbacks)

    def _run_probe(
        self,
        app: ThreadDispatchApp,
        generation: int,
        fingerprint: str,
    ) -> None:
        try:
            try:
                snapshot = self._probe()
                message = None
            except Exception as exc:  # isolated background provider boundary
                snapshot = None
                message = sanitize_exception_message(exc)
            if not self._dispatch(
                app,
                self._complete,
                generation,
                fingerprint,
                snapshot,
                message,
            ):
                self.close()
        finally:
            with self._lock:
                self._active_workers.discard(generation)

    def _dispatch_timeout(
        self,
        app: ThreadDispatchApp,
        generation: int,
        fingerprint: str,
    ) -> None:
        if not self._dispatch(app, self._timeout, generation, fingerprint):
            self.close()

    @staticmethod
    def _dispatch(
        app: ThreadDispatchApp,
        callback: Callable[..., object],
        *args: object,
    ) -> bool:
        # A rejected message means Textual's pump is no longer accepting work.
        # The caller closes the coordinator so deadlines/callbacks cannot leak.
        try:
            return app.post_message(FirstRunReadinessDispatch(callback, args))
        except RuntimeError:
            # Textual may raise when its message pump has already closed.
            return False

    def _complete(
        self,
        generation: int,
        fingerprint: str,
        snapshot: FirstRunRuntimeSnapshot | None,
        message: str | None,
    ) -> None:
        # A late provider result is inert after shutdown: avoid another
        # disk-backed configuration read on an already-closed coordinator.
        # Check without holding the lock while invoking the fingerprint; the
        # subsequent locked generation check still rejects concurrent close.
        with self._lock:
            if self._closed:
                return
        # Configuration may have changed or become invalid while the worker
        # probed. Never call disk-backed fingerprint functions under our lock
        # or leave a "checking" view behind after cancelling its deadline.
        try:
            current_fingerprint = self._fingerprint_provider()
            fingerprint_error = None
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            current_fingerprint = None
            fingerprint_error = sanitize_exception_message(exc)
        with self._lock:
            timer = self._timers.pop(generation, None)
            if timer is not None:
                timer.cancel()
            if (
                self._closed
                or self._view.generation != generation
                or self._view.state != "checking"
            ):
                return
            if fingerprint_error is not None:
                self._view = FirstRunReadinessView(
                    "failed",
                    generation,
                    fingerprint,
                    message=(
                        "Provider configuration could not be read. "
                        + fingerprint_error
                        + " Correct the configuration and retry."
                    ),
                )
            elif current_fingerprint != fingerprint:
                self._view = FirstRunReadinessView(
                    "failed",
                    generation,
                    fingerprint,
                    message="Provider configuration changed during readiness check. Retry.",
                )
            elif snapshot is None:
                self._view = FirstRunReadinessView(
                    "failed",
                    generation,
                    fingerprint,
                    message=message or "Provider readiness check failed.",
                )
            else:
                self._view = FirstRunReadinessView(
                    "ready",
                    generation,
                    fingerprint,
                    snapshot=snapshot,
                )
            callbacks = tuple(self._callbacks)
            self._callbacks.clear()
        _notify(callbacks)

    def _timeout(
        self,
        generation: int,
        fingerprint: str,
    ) -> None:
        message = "Provider readiness check timed out."
        message += " Review provider connectivity and retry."
        with self._lock:
            self._timers.pop(generation, None)
            if (
                self._closed
                or self._view.generation != generation
                or self._view.state != "checking"
            ):
                return
            self._view = FirstRunReadinessView(
                "failed",
                generation,
                fingerprint,
                message=message,
            )
            callbacks = tuple(self._callbacks)
            self._callbacks.clear()
        _notify(callbacks)

    def _probe_runtime(self) -> FirstRunRuntimeSnapshot:
        # The visible UI timeout cannot interrupt blocked provider threads.
        # Give each real HTTP readiness request a separate short socket budget,
        # keeping long generation/synthesis timeouts entirely unchanged.
        controller = self.context.composition.provider_controller.readiness_probe_controller(
            request_timeout_seconds=min(self.timeout_seconds / 4, 1.0),
            total_timeout_seconds=self.timeout_seconds,
        )
        return FirstRunRuntimeSnapshot(
            readiness=first_run_readiness(self.context, runtime_controller=controller),
            system_check=FirstRunController(controller).system_check(),
        )

    def _configuration_fingerprint(self) -> str:
        # Runs on the UI thread: never wait on the config advisory lock.
        config = self.context.composition.provider_controller.config_snapshot()
        return json.dumps(
            config.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
