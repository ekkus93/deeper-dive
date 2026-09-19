"""Deterministic cache invalidation policy for generated project artifacts.

The policy is deliberately independent from storage. Callers compare the inputs
that produced an artifact and invalidate only the downstream stages returned by
:func:`invalidated_artifacts`.
"""

from __future__ import annotations

from enum import StrEnum

CACHE_FORMAT_VERSION = 1


class Change(StrEnum):
    SOURCE_CONTENT = "source_content"
    SOURCE_INCLUSION = "source_inclusion"
    HOST_TEXT = "host_text"
    HOST_VOICE = "host_voice"
    LLM_PROVIDER_MODEL = "llm_provider_model"
    TTS_PROVIDER_MODEL = "tts_provider_model"
    CACHE_FORMAT = "cache_format"


class Artifact(StrEnum):
    CHUNKS = "chunks"
    INDEX = "index"
    PLAN = "plan"
    CONVERSATION = "conversation"
    TTS = "tts"
    AUDIO = "audio"


_ALL = frozenset(Artifact)

_INVALIDATION: dict[Change, frozenset[Artifact]] = {
    Change.SOURCE_CONTENT: _ALL,
    Change.SOURCE_INCLUSION: frozenset(
        {Artifact.INDEX, Artifact.PLAN, Artifact.CONVERSATION, Artifact.TTS, Artifact.AUDIO}
    ),
    Change.HOST_TEXT: frozenset(
        {Artifact.PLAN, Artifact.CONVERSATION, Artifact.TTS, Artifact.AUDIO}
    ),
    Change.HOST_VOICE: frozenset({Artifact.TTS, Artifact.AUDIO}),
    Change.LLM_PROVIDER_MODEL: frozenset(
        {Artifact.PLAN, Artifact.CONVERSATION, Artifact.TTS, Artifact.AUDIO}
    ),
    Change.TTS_PROVIDER_MODEL: frozenset({Artifact.TTS, Artifact.AUDIO}),
    Change.CACHE_FORMAT: _ALL,
}


def invalidated_artifacts(*changes: Change) -> frozenset[Artifact]:
    """Return the minimal union of artifacts invalidated by ``changes``."""

    invalidated: set[Artifact] = set()
    for change in changes:
        invalidated.update(_INVALIDATION[change])
    return frozenset(invalidated)


def cache_format_compatible(stored_version: int) -> bool:
    """Reject artifacts produced by an incompatible application cache format."""

    return stored_version == CACHE_FORMAT_VERSION
