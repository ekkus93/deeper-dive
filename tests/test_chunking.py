from __future__ import annotations

from deeper_dive.chunking import ChunkingConfig, chunk_parse_result
from deeper_dive.parsing import ParsedBlock, ParseResult


def test_chunking_is_deterministic_for_same_input_and_config() -> None:
    result = ParseResult(
        "fake",
        "1",
        (
            ParsedBlock(
                0,
                "abcdefghijklmnopqrstuvwxyz",
                location="page:1",
                heading="Intro",
                metadata={"kind": "page"},
            ),
        ),
    )
    config = ChunkingConfig(max_chars=10, overlap_chars=2)

    first = chunk_parse_result("source-1", "user", result, config=config)
    second = chunk_parse_result("source-1", "user", result, config=config)

    assert first == second
    assert [chunk.text for chunk in first] == ["abcdefghij", "ijklmnopqr", "qrstuvwxyz"]
    assert [chunk.ordinal for chunk in first] == [0, 1, 2]


def test_chunking_preserves_origin_location_heading_and_parser_metadata() -> None:
    result = ParseResult(
        "pdf-pypdf",
        "1",
        (
            ParsedBlock(
                0,
                "page text",
                location="page:7",
                heading="Section",
                metadata={"page": "7", "kind": "page"},
            ),
        ),
    )

    (chunk,) = chunk_parse_result("source-1", "supplemental", result)

    assert chunk.source_origin == "supplemental"
    assert chunk.location == "page:7"
    assert chunk.heading == "Section"
    assert chunk.metadata["page"] == "7"
    assert chunk.metadata["parser_id"] == "pdf-pypdf"
    assert chunk.metadata["parser_version"] == "1"
    assert chunk.metadata["chunker"].startswith("baseline-char-v1:")


def test_chunker_config_identity_changes_mapping() -> None:
    result = ParseResult("fake", "1", (ParsedBlock(0, "abcdef", location="line:1"),))

    first = chunk_parse_result(
        "source-1", "user", result, config=ChunkingConfig(max_chars=4, overlap_chars=1)
    )
    second = chunk_parse_result(
        "source-1", "user", result, config=ChunkingConfig(max_chars=4, overlap_chars=0)
    )

    assert [chunk.id for chunk in first] != [chunk.id for chunk in second]
    assert first[0].metadata["chunker"] != second[0].metadata["chunker"]


def test_chunker_rejects_invalid_overlap() -> None:
    try:
        ChunkingConfig(max_chars=10, overlap_chars=10)
    except ValueError as exc:
        assert "overlap_chars" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected invalid overlap to fail")


def test_empty_blocks_do_not_create_chunks() -> None:
    result = ParseResult("fake", "1", (ParsedBlock(0, "   "),))

    assert chunk_parse_result("source-1", "user", result) == ()
