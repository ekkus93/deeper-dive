from __future__ import annotations

import pytest

from deeper_dive.invalidation import (
    CACHE_FORMAT_VERSION,
    Artifact,
    Change,
    cache_format_compatible,
    invalidated_artifacts,
)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (Change.SOURCE_CONTENT, set(Artifact)),
        (
            Change.SOURCE_INCLUSION,
            {Artifact.INDEX, Artifact.PLAN, Artifact.CONVERSATION, Artifact.TTS, Artifact.AUDIO},
        ),
        (
            Change.HOST_TEXT,
            {Artifact.PLAN, Artifact.CONVERSATION, Artifact.TTS, Artifact.AUDIO},
        ),
        (Change.HOST_VOICE, {Artifact.TTS, Artifact.AUDIO}),
        (
            Change.LLM_PROVIDER_MODEL,
            {Artifact.PLAN, Artifact.CONVERSATION, Artifact.TTS, Artifact.AUDIO},
        ),
        (Change.TTS_PROVIDER_MODEL, {Artifact.TTS, Artifact.AUDIO}),
        (Change.CACHE_FORMAT, set(Artifact)),
    ],
)
def test_invalidation_matrix_is_minimal(change: Change, expected: set[Artifact]) -> None:
    assert invalidated_artifacts(change) == expected


def test_multiple_changes_union_without_over_invalidating() -> None:
    assert invalidated_artifacts(Change.HOST_VOICE, Change.SOURCE_INCLUSION) == {
        Artifact.INDEX,
        Artifact.PLAN,
        Artifact.CONVERSATION,
        Artifact.TTS,
        Artifact.AUDIO,
    }
    assert Artifact.CHUNKS not in invalidated_artifacts(
        Change.HOST_VOICE, Change.SOURCE_INCLUSION
    )


def test_cache_format_version_prevents_silent_incompatible_reuse() -> None:
    assert cache_format_compatible(CACHE_FORMAT_VERSION)
    assert not cache_format_compatible(CACHE_FORMAT_VERSION - 1)
    assert not cache_format_compatible(CACHE_FORMAT_VERSION + 1)
