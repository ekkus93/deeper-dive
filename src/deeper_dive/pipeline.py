"""Durable ordered generation pipeline orchestration."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from deeper_dive.application.events import ProgressEvent, ProgressSink
from deeper_dive.domain.clock import Clock, SystemClock, format_timestamp
from deeper_dive.storage.run_repositories import (
    CompletedUnitRecord,
    GenerationRunRecord,
    GenerationRunRepository,
)


class StageHandler(Protocol):
    """One idempotent pipeline stage."""

    def __call__(self, context: PipelineContext) -> None: ...


@dataclass(frozen=True, slots=True)
class PipelineContext:
    run_id: str
    episode_id: str
    stage: str


@dataclass(frozen=True, slots=True)
class PipelineResult:
    run: GenerationRunRecord
    executed_stages: tuple[str, ...]
    skipped_stages: tuple[str, ...]


DEFAULT_STAGES = (
    "sources",
    "research",
    "planning",
    "conversation",
    "verification",
    "tts",
    "composition",
    "export",
)


class PipelineOrchestrator:
    """Execute an ordered pipeline with durable stage checkpoints."""

    def __init__(
        self,
        repository: GenerationRunRepository,
        handlers: Mapping[str, StageHandler],
        *,
        stages: Sequence[str] = DEFAULT_STAGES,
        clock: Clock | None = None,
        progress: ProgressSink | None = None,
        max_stage_retries: int = 2,
        max_concurrency: int = 1,
    ) -> None:
        if max_stage_retries < 0:
            raise ValueError("max_stage_retries must be non-negative")
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if not stages or len(set(stages)) != len(stages):
            raise ValueError("stages must be non-empty and unique")
        missing = [stage for stage in stages if stage not in handlers]
        if missing:
            raise ValueError(f"missing stage handlers: {', '.join(missing)}")
        self.repository = repository
        self.handlers = handlers
        self.stages = tuple(stages)
        self.clock = clock or SystemClock()
        self.progress = progress
        self.max_stage_retries = max_stage_retries
        # Reserved for stages that internally support bounded parallel work. Keeping the
        # orchestration itself serial preserves deterministic durable stage ordering.
        self.max_concurrency = max_concurrency

    def request_pause(self, run_id: str) -> None:
        """Request cooperative pause at the next safe stage boundary."""
        self.repository.request_pause(run_id, self._now())

    def request_cancel(self, run_id: str) -> None:
        """Request cooperative cancel at the next safe stage boundary."""
        self.repository.request_cancel(run_id, self._now())

    def resume(self, run_id: str) -> GenerationRunRecord:
        """Clear a durable pause request so a later process can continue the run."""
        record = self.repository.get(run_id)
        if record is None:
            raise KeyError(f"unknown generation run: {run_id}")
        if record.cancel_requested or record.state == "cancelled":
            raise ValueError("cancelled runs cannot be resumed")
        resumed = replace(
            record,
            state="pending",
            pause_requested=False,
            failure_code=None,
            failure_message=None,
            modified_at=self._now(),
        )
        self.repository.update(resumed)
        self._emit(record.stage, "resumed")
        return resumed

    def run(
        self,
        run_id: str,
        *,
        force_from: str | None = None,
        artifact_valid: Callable[[str], bool] | None = None,
    ) -> PipelineResult:
        record = self.repository.get(run_id)
        if record is None:
            raise KeyError(f"unknown generation run: {run_id}")
        if force_from is not None and force_from not in self.stages:
            raise ValueError(f"unknown force_from stage: {force_from}")
        forced_index = self.stages.index(force_from) if force_from is not None else len(self.stages)
        executed: list[str] = []
        skipped: list[str] = []

        control_result = self._apply_requested_control(record, tuple(executed), tuple(skipped))
        if control_result is not None:
            return control_result

        for index, stage in enumerate(self.stages):
            record = self._refresh(run_id)
            control_result = self._apply_requested_control(record, tuple(executed), tuple(skipped))
            if control_result is not None:
                return control_result

            completed = bool(self.repository.list_completed_units(run_id, stage))
            valid = artifact_valid(stage) if artifact_valid is not None else completed
            if index < forced_index and completed and valid:
                skipped.append(stage)
                self._emit(stage, "skipped", "valid durable artifact already exists")
                continue

            record = self._update(record, stage=stage, state="running")
            self._emit(stage, "running")
            context = PipelineContext(run_id=run_id, episode_id=record.episode_id, stage=stage)
            attempts = 0
            while True:
                try:
                    self.handlers[stage](context)
                    break
                except Exception as exc:
                    attempts += 1
                    if attempts > self.max_stage_retries:
                        failed = GenerationRunRepository.with_failure(
                            record,
                            code="stage_failed",
                            sanitized_message=str(exc),
                            modified_at=self._now(),
                        )
                        self.repository.update(failed)
                        self._emit(stage, "failed", str(exc))
                        raise
                    self._emit(stage, "retrying", f"retry {attempts}/{self.max_stage_retries}")

            self.repository.complete_unit(CompletedUnitRecord(run_id, stage, "stage", self._now()))
            executed.append(stage)
            self._emit(stage, "completed")

            record = self._refresh(run_id)
            control_result = self._apply_requested_control(record, tuple(executed), tuple(skipped))
            if control_result is not None:
                return control_result

        record = self._update(record, stage=self.stages[-1], state="completed")
        self._emit("pipeline", "completed", completed=len(self.stages), total=len(self.stages))
        return PipelineResult(record, tuple(executed), tuple(skipped))

    def _refresh(self, run_id: str) -> GenerationRunRecord:
        record = self.repository.get(run_id)
        if record is None:
            raise KeyError(f"unknown generation run: {run_id}")
        return record

    def _apply_requested_control(
        self,
        record: GenerationRunRecord,
        executed: tuple[str, ...],
        skipped: tuple[str, ...],
    ) -> PipelineResult | None:
        if record.cancel_requested:
            cancelled = self._update(record, stage=record.stage, state="cancelled")
            self._emit(record.stage, "cancelled", "cancel requested at safe boundary")
            return PipelineResult(cancelled, executed, skipped)
        if record.pause_requested:
            paused = self._update(record, stage=record.stage, state="paused")
            self._emit(record.stage, "paused", "pause requested at safe boundary")
            return PipelineResult(paused, executed, skipped)
        return None

    def _update(
        self, record: GenerationRunRecord, *, stage: str, state: str
    ) -> GenerationRunRecord:
        updated = GenerationRunRecord(
            id=record.id,
            episode_id=record.episode_id,
            stage=stage,
            state=state,
            created_at=record.created_at,
            modified_at=self._now(),
            retry_count=record.retry_count,
            failure_code=None,
            failure_message=None,
            pause_requested=record.pause_requested,
            cancel_requested=record.cancel_requested,
        )
        self.repository.update(updated)
        return updated

    def _now(self) -> str:
        return format_timestamp(self.clock.now())

    def _emit(
        self,
        operation: str,
        state: str,
        message: str = "",
        *,
        completed: int | None = None,
        total: int | None = None,
    ) -> None:
        if self.progress is not None:
            self.progress(ProgressEvent(operation, state, message, completed, total))
