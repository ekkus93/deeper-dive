"""Command-line entry point for Deeper Dive."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from deeper_dive import __version__
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.storage.workspace import WorkspaceManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deeper-dive",
        description="Explore source material and generate evidence-grounded deep dives.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    commands = parser.add_subparsers(dest="command")
    project = commands.add_parser("project", help="manage projects")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    create = project_commands.add_parser("create", help="create a project")
    create.add_argument("name")
    project_commands.add_parser("list", help="list projects")
    info = project_commands.add_parser("info", help="show project metadata")
    info.add_argument("project_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None:
        build_parser().print_help()
        return 0
    service = DeeperDiveService(WorkspaceManager(args.data_dir))
    try:
        if args.project_command == "create":
            return _output(asdict(service.create_project(args.name)), args.json_output)
        if args.project_command == "list":
            return _output(
                [asdict(project) for project in service.list_projects()], args.json_output
            )
        project = service.open_project(args.project_id)
        if project is None:
            print(f"project not found: {args.project_id}", file=sys.stderr)
            return 2
        return _output(asdict(project), args.json_output)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def _output(value: object, json_output: bool) -> int:
    if json_output:
        print(json.dumps(value, sort_keys=True))
    elif isinstance(value, list):
        for item in value:
            print(f"{item['id']}\t{item['name']}")
    else:
        item = value
        print(f"{item['id']}\t{item['name']}")  # type: ignore[index]
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
