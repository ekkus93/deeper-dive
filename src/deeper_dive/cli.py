"""Command-line entry point for Deeper Dive."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from deeper_dive import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser without causing external side effects."""
    parser = argparse.ArgumentParser(
        prog="deeper-dive",
        description="Explore source material and generate evidence-grounded deep dives.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Deeper Dive command-line interface."""
    build_parser().parse_args(argv)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
