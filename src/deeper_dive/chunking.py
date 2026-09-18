"""Deterministic source chunking with provenance preservation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from deeper_dive.parsing import ParseResult, ParsedBlock


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    """Baseline chunking configuration suitable for stable local indexing."""

    max_chars: int = 1600
    overlap_chars: int = 160
    version: str = "baseline-char-v1"

    def __post_init__(self) -> None:
        if self.max_chars < 1:
            raise ValueError("max_chars must be positive")
        if self.overlap_chars < 0:
            raise ValueError("overlap_chars must be non-negative")
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")

    @property
    def identity(self) -> str:
        return f"{self.version}:max={self.max_chars}:overlap={self.overlap_chars}"


@dataclass(frozen=True, slots=True)
class Chunk:
    """One deterministic chunk that retains source/block provenance."""

    id: str
    ordinal: int
    text: str
    content_hash: str
    source_origin: str
    location: str | None
    heading: str | None
    metadata: dict[str, str]


def chunk_parse_result(
    source_id: str,
    source_origin: str,
    parse_result: ParseResult,
    *,
    config: ChunkingConfig | None = None,
) -> tuple[Chunk, ...]:
    """Chunk parsed blocks while preserving origin, location, heading, and parser metadata."""

    selected_config = ChunkingConfig() if config is None else config
    chunks: list[Chunk] = []
    for block in parse_result.blocks:
        for piece_index, piece in enumerate(_split_text(block.text, selected_config)):
            content_hash = hashlib.sha256(piece.encode("utf-8")).hexdigest()
            chunk_id = _chunk_id(source_id, block, piece_index, selected_config, piece)
            chunks.append(
                Chunk(
                    id=chunk_id,
                    ordinal=len(chunks),
                    text=piece,
                    content_hash=content_hash,
                    source_origin=source_origin,
                    location=block.location,
                    heading=block.heading,
                    metadata={
                        **block.metadata,
                        "parser_id": parse_result.parser_id,
                        "parser_version": parse_result.parser_version,
                        "chunker": selected_config.identity,
                        "block_ordinal": str(block.ordinal),
                        "piece_ordinal": str(piece_index),
                    },
                )
            )
    return tuple(chunks)


def _split_text(text: str, config: ChunkingConfig) -> tuple[str, ...]:
    stripped = text.strip()
    if not stripped:
        return ()
    if len(stripped) <= config.max_chars:
        return (stripped,)
    pieces: list[str] = []
    start = 0
    while start < len(stripped):
        end = min(start + config.max_chars, len(stripped))
        piece = stripped[start:end].strip()
        if piece:
            pieces.append(piece)
        if end == len(stripped):
            break
        start = end - config.overlap_chars
    return tuple(pieces)


def _chunk_id(
    source_id: str,
    block: ParsedBlock,
    piece_index: int,
    config: ChunkingConfig,
    text: str,
) -> str:
    payload = "\x1f".join(
        (
            source_id,
            str(block.ordinal),
            str(piece_index),
            block.location or "",
            block.heading or "",
            config.identity,
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
