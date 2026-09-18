from __future__ import annotations

import deeper_dive.parsing as parsing


class FakeParser:
    parser_id = "fake"
    parser_version = "1"

    def supports(self, request: parsing.ParseRequest) -> bool:
        return request.text is not None

    def parse(self, request: parsing.ParseRequest) -> parsing.ParseResult:
        assert request.text is not None
        blocks = tuple(
            parsing.ParsedBlock(
                ordinal=index,
                text=line,
                location=f"line:{index + 1}",
                heading="Fixture" if index == 0 else None,
                metadata={"kind": "paragraph"},
            )
            for index, line in enumerate(request.text.splitlines())
        )
        return parsing.ParseResult(
            parser_id=self.parser_id,
            parser_version=self.parser_version,
            blocks=blocks,
            diagnostics=(
                parsing.ParseDiagnostic(
                    parsing.ParseSeverity.WARNING,
                    "fixture-warning",
                    "deterministic warning",
                ),
            ),
            metadata={"fixture": "true"},
        )


def _run(parser: parsing.SourceParser, text: str) -> parsing.ParseResult:
    request = parsing.ParseRequest(text=text, media_type="text/plain")
    assert parser.supports(request)
    result = parser.parse(request)
    parsing.validate_parse_result(parser, result)
    return result


def test_fake_parser_has_deterministic_structural_metadata_flow() -> None:
    first = _run(FakeParser(), "First\nSecond")
    second = _run(FakeParser(), "First\nSecond")

    assert first == second
    assert first.cache_identity == "fake:1"
    assert [block.location for block in first.blocks] == ["line:1", "line:2"]
    assert first.blocks[0].heading == "Fixture"
    assert first.blocks[1].metadata == {"kind": "paragraph"}
    assert first.diagnostics[0].severity is parsing.ParseSeverity.WARNING
    assert not first.has_errors


def test_parse_request_requires_exactly_one_input() -> None:
    for kwargs in ({}, {"path": __file__, "text": "both"}):
        try:
            parsing.ParseRequest(**kwargs)  # type: ignore[arg-type]
        except ValueError as exc:
            assert "exactly one" in str(exc)
        else:
            raise AssertionError("invalid parse request accepted")


def test_parse_result_rejects_noncontiguous_blocks() -> None:
    parser = FakeParser()
    result = parsing.ParseResult("fake", "1", (parsing.ParsedBlock(ordinal=2, text="bad"),))
    try:
        parsing.validate_parse_result(parser, result)
    except ValueError as exc:
        assert "contiguous" in str(exc)
    else:
        raise AssertionError("invalid parser output accepted")
