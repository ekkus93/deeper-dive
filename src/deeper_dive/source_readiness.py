"""One shared source-readiness contract for guided workflow and generation preflight."""

from __future__ import annotations

from deeper_dive.storage.repositories import SourceRecord


def source_index_ready(source: SourceRecord, chunk_count: int) -> bool:
    """A failed import is not usable evidence even if partial chunks were written."""

    return source.status not in {"error", "failed"} and chunk_count > 0


def source_readiness_label(source: SourceRecord, chunk_count: int) -> str:
    """Friendly, status-aware source row text; never expose internal source IDs."""

    if not source.included:
        return f"excluded ({chunk_count} chunks)"
    if source.status in {"error", "failed"}:
        return "import failed — retry source import"
    if chunk_count <= 0:
        return "needs indexing — no parsed chunks"
    if source.status == "warning":
        return f"ready with warnings ({chunk_count} indexed chunks)"
    return f"ready ({chunk_count} indexed chunks)"
