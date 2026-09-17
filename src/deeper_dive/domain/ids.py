"""Stable, serializable identifiers for persisted domain objects."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

ProjectId = NewType("ProjectId", str)
SourceId = NewType("SourceId", str)
ChunkId = NewType("ChunkId", str)
HostId = NewType("HostId", str)
EpisodeId = NewType("EpisodeId", str)
TurnId = NewType("TurnId", str)
RunId = NewType("RunId", str)


def _new_id[T](constructor: Callable[[str], T]) -> T:
    return constructor(str(uuid4()))


def _parse_id[T](value: str, constructor: Callable[[str], T]) -> T:
    parsed = UUID(value)
    canonical = str(parsed)
    if value != canonical:
        raise ValueError(f"ID must use canonical UUID form: {canonical}")
    return constructor(canonical)


def new_project_id() -> ProjectId:
    return _new_id(ProjectId)


def new_source_id() -> SourceId:
    return _new_id(SourceId)


def new_chunk_id() -> ChunkId:
    return _new_id(ChunkId)


def new_host_id() -> HostId:
    return _new_id(HostId)


def new_episode_id() -> EpisodeId:
    return _new_id(EpisodeId)


def new_turn_id() -> TurnId:
    return _new_id(TurnId)


def new_run_id() -> RunId:
    return _new_id(RunId)


def parse_project_id(value: str) -> ProjectId:
    return _parse_id(value, ProjectId)


def parse_source_id(value: str) -> SourceId:
    return _parse_id(value, SourceId)


def parse_chunk_id(value: str) -> ChunkId:
    return _parse_id(value, ChunkId)


def parse_host_id(value: str) -> HostId:
    return _parse_id(value, HostId)


def parse_episode_id(value: str) -> EpisodeId:
    return _parse_id(value, EpisodeId)


def parse_turn_id(value: str) -> TurnId:
    return _parse_id(value, TurnId)


def parse_run_id(value: str) -> RunId:
    return _parse_id(value, RunId)
