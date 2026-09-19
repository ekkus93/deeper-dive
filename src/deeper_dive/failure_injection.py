"""Deterministic failure-injection helpers for resumable pipeline tests."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from deeper_dive.domain.clock import Clock, SystemClock, format_timestamp
from deeper_dive.pipeline import PipelineContext
from deeper_dive.storage.run_repositories import CompletedUnitRecord, GenerationRunRepository


class InjectedPipelineFailure(RuntimeError):
    """Synthetic failure raised by deterministic resumption tests."""


@dataclass(frozen=True, slots=True)
class FailurePoint:
    """One synthetic failure location inside a pipeline stage."""

    stage: str
    unit_id: str
    fail_after_checkpoint: bool = True
    message: str = "injected pipeline failure"


@dataclass(slots=True)
class FailureInjector:
    """Raise configured failures once, then allow reruns to make progress."""

    points: tuple[FailurePoint, ...]
    triggered: set[tuple[str, str, bool]] = field(default_factory=set)

    def maybe_fail(self, stage: str, unit_id: str, *, after_checkpoint: bool) -> None:
        key = (stage, unit_id, after_checkpoint)
        if key in self.triggered:
            return
        for point in self.points:
            if (
                point.stage == stage
                and point.unit_id == unit_id
                and point.fail_after_checkpoint == after_checkpoint
            ):
                self.triggered.add(key)
                raise InjectedPipelineFailure(f"{point.message}: {stage}/{unit_id}")


def run_checkpointed_units(
    context: PipelineContext,
    repository: GenerationRunRepository,
    unit_ids: Iterable[str],
    work: Callable[[str], None],
    *,
    injector: FailureInjector | None = None,
    clock: Clock | None = None,
) -> None:
    """Run idempotent units, preserving completed checkpoints across failures.

    The stage-level pipeline checkpoint is still owned by ``PipelineOrchestrator``.
    This helper adds finer-grained stage-internal checkpoints so deterministic
    tests can fail after parsing, planning, arbitrary turns, TTS items, or export
    substeps and prove reruns skip already committed units.
    """

    timestamp_clock = clock or SystemClock()
    completed = {
        unit.unit_id for unit in repository.list_completed_units(context.run_id, context.stage)
    }
    for unit_id in unit_ids:
        if unit_id in completed:
            continue
        if injector is not None:
            injector.maybe_fail(context.stage, unit_id, after_checkpoint=False)
        work(unit_id)
        repository.complete_unit(
            CompletedUnitRecord(
                context.run_id,
                context.stage,
                unit_id,
                format_timestamp(timestamp_clock.now()),
            )
        )
        completed.add(unit_id)
        if injector is not None:
            injector.maybe_fail(context.stage, unit_id, after_checkpoint=True)
