"""Non-blocking first-run runtime readiness for Textual surfaces."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock, Thread, Timer
from typing import Literal, Protocol

from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.first_run import FirstRunController, FirstRunSystemCheck
from deeper_dive.guided_readiness import FirstRunDerivedReadiness, first_run_readiness
from deeper_dive.guided_workflow import WizardContext

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


class ThreadDispatchApp(Protocol):
    def call_from_thread(self, callback: Callable[..., object], *args: object) -> object: ...


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
    ) -> None:
        self.context = context
        self._probe = probe or self._probe_runtime
        self._fingerprint_provider = fingerprint or self._configuration_fingerprint
        self.timeout_seconds = timeout_seconds
        self._lock = Lock()
        self._view = FirstRunReadinessView("idle", 0, None)

    @property
    def view(self) -> FirstRunReadinessView:
        with self._lock:
            return self._view

    @property
    def snapshot(self) -> FirstRunRuntimeSnapshot | None:
        return self.view.snapshot

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
    ) -> bool:
        fingerprint = self._fingerprint_provider()
        with self._lock:
            if self._view.state == "checking" and self._view.fingerprint == fingerprint:
                return False
            generation = self._view.generation + 1
            self._view = FirstRunReadinessView("checking", generation, fingerprint)

        timer = Timer(
            self.timeout_seconds,
            self._dispatch_timeout,
            args=(app, generation, fingerprint, callback),
        )
        timer.daemon = True
        timer.start()

        worker = Thread(
            target=self._run_probe,
            args=(app, generation, fingerprint, callback),
            name=f"deeper-dive-readiness-{generation}",
            daemon=True,
        )
        worker.start()
        return True

    def _run_probe(
        self,
        app: ThreadDispatchApp,
        generation: int,
        fingerprint: str,
        callback: Callable[[], object] | None,
    ) -> None:
        try:
            snapshot = self._probe()
            message = None
        except Exception as exc:  # isolated background provider boundary
            snapshot = None
            message = sanitize_exception_message(exc)
        self._dispatch(
            app,
            self._complete,
            generation,
            fingerprint,
            snapshot,
            message,
            callback,
        )

    def _dispatch_timeout(
        self,
        app: ThreadDispatchApp,
        generation: int,
        fingerprint: str,
        callback: Callable[[], object] | None,
    ) -> None:
        self._dispatch(app, self._timeout, generation, fingerprint, callback)

    @staticmethod
    def _dispatch(
        app: ThreadDispatchApp,
        callback: Callable[..., object],
        *args: object,
    ) -> None:
        try:
            app.call_from_thread(callback, *args)
        except RuntimeError:
            # The Textual app may have closed while a daemon probe was pending.
            return

    def _complete(
        self,
        generation: int,
        fingerprint: str,
        snapshot: FirstRunRuntimeSnapshot | None,
        message: str | None,
        callback: Callable[[], object] | None,
    ) -> None:
        with self._lock:
            if (
                self._view.generation != generation
                or self._view.state != "checking"
                or self._fingerprint_provider() != fingerprint
            ):
                return
            if snapshot is None:
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
        if callback is not None:
            callback()

    def _timeout(
        self,
        generation: int,
        fingerprint: str,
        callback: Callable[[], object] | None,
    ) -> None:
        with self._lock:
            if self._view.generation != generation or self._view.state != "checking":
                return
            self._view = FirstRunReadinessView(
                "failed",
                generation,
                fingerprint,
                message=(
                    "Provider readiness check timed out. "
                    "Review provider connectivity and retry."
                ),
            )
        if callback is not None:
            callback()

    def _probe_runtime(self) -> FirstRunRuntimeSnapshot:
        controller = self.context.composition.provider_controller
        return FirstRunRuntimeSnapshot(
            readiness=first_run_readiness(self.context),
            system_check=FirstRunController(controller).system_check(),
        )

    def _configuration_fingerprint(self) -> str:
        config = self.context.composition.provider_controller.config()
        return json.dumps(
            config.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
