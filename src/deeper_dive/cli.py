"""Command-line entry point for Deeper Dive."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from enum import Enum
from pathlib import Path

from deeper_dive import __version__
from deeper_dive.application.service import DeeperDiveService, SourceImportSummary
from deeper_dive.domain.ids import parse_project_id
from deeper_dive.research_controller import PersistentResearchController
from deeper_dive.storage.repositories import SourceRecord
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

    source = commands.add_parser("source", help="manage project sources")
    source_commands = source.add_subparsers(dest="source_command", required=True)
    add = source_commands.add_parser("add", help="add files, directories, or explicit URLs")
    add.add_argument("project_id")
    add.add_argument("inputs", nargs="+")
    add.add_argument("--url", action="store_true", help="treat inputs as explicit HTTP/HTTPS URLs")
    list_sources = source_commands.add_parser("list", help="list project sources")
    list_sources.add_argument("project_id")
    show = source_commands.add_parser("show", help="show source metadata")
    show.add_argument("project_id")
    show.add_argument("source_id")
    for action in ("include", "exclude", "remove"):
        command = source_commands.add_parser(action, help=f"{action} a project source")
        command.add_argument("project_id")
        command.add_argument("source_id")

    research = commands.add_parser("research", help="inspect and run supplemental research")
    research_commands = research.add_subparsers(dest="research_command", required=True)
    analyze = research_commands.add_parser("analyze", help="analyze the corpus for research gaps")
    analyze.add_argument("project_id")
    analyze.add_argument("--focus", default="")
    gaps = research_commands.add_parser("gaps", help="list research gaps")
    gaps.add_argument("project_id")
    run_research = research_commands.add_parser("run", help="research selected gaps")
    run_research.add_argument("project_id")
    run_research.add_argument("gap_ids", nargs="*")
    run_research.add_argument("--all", action="store_true", dest="all_gaps")
    ignore = research_commands.add_parser("ignore", help="ignore a research gap")
    ignore.add_argument("project_id")
    ignore.add_argument("gap_id")
    outcomes = research_commands.add_parser(
        "outcomes", help="list supplemental research candidate outcomes"
    )
    outcomes.add_argument("project_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None:
        build_parser().print_help()
        return 0
    service = DeeperDiveService(WorkspaceManager(args.data_dir))
    try:
        if args.command == "project":
            return _project_command(service, args)
        if args.command == "source":
            return _source_command(service, args)
        if args.command == "research":
            return _research_command(service, args)
        return 2
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def _project_command(service: DeeperDiveService, args: argparse.Namespace) -> int:
    if args.project_command == "create":
        return _output(asdict(service.create_project(args.name)), args.json_output)
    if args.project_command == "list":
        return _output([asdict(project) for project in service.list_projects()], args.json_output)
    project = service.open_project(args.project_id)
    if project is None:
        print(f"project not found: {args.project_id}", file=sys.stderr)
        return 2
    return _output(asdict(project), args.json_output)


def _source_command(service: DeeperDiveService, args: argparse.Namespace) -> int:
    project_id = args.project_id
    if service.open_project(project_id) is None:
        print(f"project not found: {project_id}", file=sys.stderr)
        return 2
    if args.source_command == "add":
        if args.url:
            summary = service.add_url_sources(project_id, list(args.inputs))
        else:
            summary = service.add_file_sources(project_id, [Path(value) for value in args.inputs])
        return _output_import(summary, args.json_output)
    if args.source_command == "list":
        return _output_sources(service.list_sources(project_id), args.json_output)
    source = service.get_source(project_id, args.source_id)
    if source is None:
        print(f"source not found: {args.source_id}", file=sys.stderr)
        return 2
    if args.source_command == "show":
        return _output_source(source, args.json_output)
    if args.source_command in {"include", "exclude"}:
        included = args.source_command == "include"
        service.set_source_included(project_id, source.id, included)
        updated = service.get_source(project_id, source.id)
        assert updated is not None
        return _output_source(updated, args.json_output)
    service.delete_source(project_id, source.id)
    return _output({"id": source.id, "removed": True}, args.json_output)


def _research_command(service: DeeperDiveService, args: argparse.Namespace) -> int:
    project_id = args.project_id
    if service.open_project(project_id) is None:
        print(f"project not found: {project_id}", file=sys.stderr)
        return 2
    controller = PersistentResearchController(
        lambda value: service.workspaces.project_root(parse_project_id(value)) / "project.db"
    )
    if args.research_command == "analyze":
        gaps = controller.analyze(project_id, args.focus)
        return _output([asdict(gap) for gap in gaps], args.json_output)
    if args.research_command == "gaps":
        return _output([asdict(gap) for gap in controller.gaps(project_id)], args.json_output)
    if args.research_command == "ignore":
        controller.set_gap_status(project_id, args.gap_id, "ignored")
        return _output({"id": args.gap_id, "status": "ignored"}, args.json_output)
    if args.research_command == "outcomes":
        return _output([asdict(outcome) for outcome in controller.outcomes(project_id)], args.json_output)
    gap_ids = tuple(args.gap_ids)
    if args.all_gaps:
        gap_ids = tuple(gap.id for gap in controller.gaps(project_id) if gap.status != "ignored")
    if not gap_ids:
        raise ValueError("research run requires one or more gap IDs or --all")
    outcomes = controller.research(project_id, gap_ids)
    return _output([asdict(outcome) for outcome in outcomes], args.json_output)


def _output_import(summary: SourceImportSummary, json_output: bool) -> int:
    value = {
        "imported": [asdict(source) for source in summary.imported],
        "candidates": [asdict(candidate) for candidate in summary.plan.candidates],
    }
    if json_output:
        print(json.dumps(value, sort_keys=True))
    else:
        for candidate in summary.plan.candidates:
            print(f"{candidate.disposition}\t{candidate.locator}")
    return 0


def _output_sources(sources: list[SourceRecord], json_output: bool) -> int:
    if json_output:
        print(json.dumps([asdict(source) for source in sources], sort_keys=True))
    else:
        for source in sources:
            state = "included" if source.included else "excluded"
            print(f"{source.id}\t{state}\t{source.title}")
    return 0


def _output_source(source: SourceRecord, json_output: bool) -> int:
    if json_output:
        print(json.dumps(asdict(source), sort_keys=True))
    else:
        state = "included" if source.included else "excluded"
        print(f"{source.id}\t{state}\t{source.title}")
    return 0


def _json_default(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _output(value: object, json_output: bool) -> int:
    if json_output:
        print(json.dumps(value, sort_keys=True, default=_json_default))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                print(json.dumps(item, sort_keys=True, default=_json_default))
            else:
                print(str(item))
    elif isinstance(value, dict) and "name" in value:
        print(f"{value['id']}\t{value['name']}")
    else:
        print(json.dumps(value, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
