"""Command-line entry point for Deeper Dive."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, replace
from enum import Enum
from pathlib import Path
from typing import Any

from deeper_dive import __version__, model_roles
from deeper_dive.application.service import DeeperDiveService, SourceImportSummary
from deeper_dive.composition import ProductionComposition
from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.episode_planner import EpisodePlannerService
from deeper_dive.hosts import HostProfile, create_host_from_preset, preset_names
from deeper_dive.research_controller import PersistentResearchController
from deeper_dive.research_gaps import ResearchGap, ResearchGapPlanner
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.repositories import SourceRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deeper-dive",
        description="Explore source material and generate evidence-grounded deep dives.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    commands = parser.add_subparsers(dest="command")
    _add_project_parser(commands)
    _add_source_parser(commands)
    _add_research_parser(commands)
    _add_host_parser(commands)
    _add_episode_parser(commands)
    return parser


def _add_project_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    project = commands.add_parser("project", help="manage projects")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    create = project_commands.add_parser("create", help="create a project")
    create.add_argument("name")
    project_commands.add_parser("list", help="list projects")
    info = project_commands.add_parser("info", help="show project metadata")
    info.add_argument("project_id")


def _add_source_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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


def _add_research_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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


def _add_host_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    host = commands.add_parser("host", help="manage project hosts")
    host_commands = host.add_subparsers(dest="host_command", required=True)
    host_commands.add_parser("presets", help="list host presets")
    host_list = host_commands.add_parser("list", help="list project hosts")
    host_list.add_argument("project_id")
    host_create = host_commands.add_parser("create", help="create host from preset")
    host_create.add_argument("project_id")
    host_create.add_argument("preset")
    host_create.add_argument("--name")
    host_edit = host_commands.add_parser("edit", help="edit primary host fields")
    host_edit.add_argument("project_id")
    host_edit.add_argument("host_id")
    host_edit.add_argument("--name")
    host_edit.add_argument("--role")
    host_edit.add_argument("--expertise")
    host_edit.add_argument("--instructions")
    host_voice = host_commands.add_parser("voice", help="assign host TTS provider and voice")
    host_voice.add_argument("project_id")
    host_voice.add_argument("host_id")
    host_voice.add_argument("--provider", required=True)
    host_voice.add_argument("--voice", required=True)


def _add_episode_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    episode = commands.add_parser("episode", help="manage project episodes")
    episode_commands = episode.add_subparsers(dest="episode_command", required=True)
    episode_list = episode_commands.add_parser("list", help="list episodes")
    episode_list.add_argument("project_id")
    create = episode_commands.add_parser("create", help="create/configure an episode")
    create.add_argument("project_id")
    _add_episode_config_args(create, require_title=True)
    configure = episode_commands.add_parser("configure", help="edit an episode configuration")
    configure.add_argument("project_id")
    configure.add_argument("episode_id")
    _add_episode_config_args(configure, require_title=False)
    show = episode_commands.add_parser("show", help="show episode configuration")
    show.add_argument("project_id")
    show.add_argument("episode_id")
    plan = episode_commands.add_parser("plan", help="create or replace a production plan")
    plan.add_argument("project_id")
    plan.add_argument("episode_id")
    show_plan = episode_commands.add_parser("show-plan", help="show the current plan")
    show_plan.add_argument("project_id")
    show_plan.add_argument("episode_id")
    generate = episode_commands.add_parser("generate", help="create a durable generation run")
    generate.add_argument("project_id")
    generate.add_argument("episode_id")
    for action in ("pause", "cancel", "resume", "status", "export"):
        command = episode_commands.add_parser(action, help=f"{action} episode generation")
        command.add_argument("project_id")
        command.add_argument("episode_id")
        if action == "export":
            command.add_argument("--output-dir", type=Path)


def _add_episode_config_args(parser: argparse.ArgumentParser, *, require_title: bool) -> None:
    parser.add_argument("--title", required=require_title)
    parser.add_argument("--focus")
    parser.add_argument("--audience")
    parser.add_argument("--depth", dest="technical_depth")
    parser.add_argument("--duration", type=int, dest="target_duration_seconds")
    parser.add_argument("--style")
    parser.add_argument("--hosts", help="comma-separated host IDs; defaults to all project hosts")
    parser.add_argument("--must-cover", dest="must_cover", help="comma-separated required topics")
    parser.add_argument("--avoid", dest="avoid_topics", help="comma-separated avoided topics")
    parser.add_argument("--research-policy", default=None)
    parser.add_argument("--citation-behavior", default=None)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    composition = ProductionComposition.build(data_dir=args.data_dir)
    service = composition.service
    try:
        if args.command == "project":
            return _project_command(service, args)
        if args.command == "source":
            return _source_command(service, args)
        if args.command == "research":
            return _research_command(composition, args)
        if args.command == "host":
            return _host_command(service, args)
        if args.command == "episode":
            return _episode_command(composition, args)
        return 2
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        print(sanitize_exception_message(exc), file=sys.stderr)
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
        summary = (
            service.add_url_sources(project_id, list(args.inputs))
            if args.url
            else service.add_file_sources(project_id, [Path(value) for value in args.inputs])
        )
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
        service.set_source_included(project_id, source.id, args.source_command == "include")
        updated = service.get_source(project_id, source.id)
        assert updated is not None
        return _output_source(updated, args.json_output)
    service.delete_source(project_id, source.id)
    return _output({"id": source.id, "removed": True}, args.json_output)


def _research_command(composition: ProductionComposition, args: argparse.Namespace) -> int:
    service = composition.service
    controller = composition.research_controller
    project_id = args.project_id
    if service.open_project(project_id) is None:
        print(f"project not found: {project_id}", file=sys.stderr)
        return 2
    if args.research_command == "analyze":
        return _output(
            [asdict(gap) for gap in _research_analyze(composition, project_id, args.focus)],
            args.json_output,
        )
    if args.research_command == "gaps":
        return _output([asdict(gap) for gap in controller.gaps(project_id)], args.json_output)
    if args.research_command == "ignore":
        controller.set_gap_status(project_id, args.gap_id, "ignored")
        return _output({"id": args.gap_id, "status": "ignored"}, args.json_output)
    if args.research_command == "outcomes":
        return _output(
            [asdict(outcome) for outcome in controller.outcomes(project_id)], args.json_output
        )
    gap_ids = tuple(args.gap_ids)
    if args.all_gaps:
        gap_ids = tuple(gap.id for gap in controller.gaps(project_id) if gap.status != "ignored")
    if not gap_ids:
        raise ValueError("research run requires one or more gap IDs or --all")
    return _output(
        [asdict(outcome) for outcome in controller.research(project_id, gap_ids)], args.json_output
    )


def _research_analyze(
    composition: ProductionComposition,
    project_id: str,
    focus: str,
) -> tuple[ResearchGap, ...]:
    assignments, errors = composition.effective_model_role_assignments(project_id)
    if errors:
        raise ValueError("; ".join(errors))
    assignment = assignments.resolve(model_roles.ModelRole.CORPUS_ANALYSIS)
    if assignment is None:
        raise ValueError("no provider/model assignment for corpus_analysis")
    provider = composition.provider_controller.llm_registry.get(assignment.provider)
    controller = composition.research_controller
    controller.save_policy(project_id, controller.policy(project_id), focus)
    planner = ResearchGapPlanner(composition.database_for_project(project_id), provider)
    return planner.analyze(project_id, model=assignment.model)


def _host_command(service: DeeperDiveService, args: argparse.Namespace) -> int:
    if args.host_command == "presets":
        return _output([{"name": name} for name in preset_names()], args.json_output)
    project_id = args.project_id
    if service.open_project(project_id) is None:
        print(f"project not found: {project_id}", file=sys.stderr)
        return 2
    repository = service.hosts(project_id)
    if args.host_command == "list":
        return _output(
            [
                HostProfile.from_record(record).as_dict()
                for record in repository.list_hosts(project_id)
            ],
            args.json_output,
        )
    if args.host_command == "create":
        host = create_host_from_preset(args.preset, project_id)
        if args.name:
            host.display_name = args.name
            host.validate()
        repository.create_host(host.to_record())
        return _output(host.as_dict(), args.json_output)
    record = repository.get_host(args.host_id)
    if record is None or record.project_id != project_id:
        raise KeyError(args.host_id)
    if args.host_command == "voice":
        updated = replace(record, tts_provider=args.provider, tts_voice=args.voice)
    else:
        updated = replace(
            record,
            display_name=args.name if args.name is not None else record.display_name,
            role=args.role if args.role is not None else record.role,
            expertise=args.expertise if args.expertise is not None else record.expertise,
            instructions=args.instructions
            if args.instructions is not None
            else record.instructions,
        )
        HostProfile.from_record(updated).validate()
    repository.update_host(updated)
    return _output(HostProfile.from_record(updated).as_dict(), args.json_output)


def _episode_command(composition: ProductionComposition, args: argparse.Namespace) -> int:
    service = composition.service
    project_id = args.project_id
    if service.open_project(project_id) is None:
        print(f"project not found: {project_id}", file=sys.stderr)
        return 2
    database = composition.database_for_project(project_id)
    repository = service.hosts(project_id)
    config_service = EpisodeConfigurationService(database)
    if args.episode_command == "list":
        return _output(
            [asdict(episode) for episode in repository.list_episodes(project_id)], args.json_output
        )
    if args.episode_command == "create":
        config = _episode_config_from_args(service, project_id, args)
        return _output(asdict(config_service.create(project_id, config)), args.json_output)

    episode = _episode_record(repository.get_episode(args.episode_id), project_id, args.episode_id)
    if args.episode_command == "configure":
        existing = config_service.load_configuration(episode.id)
        config = _episode_config_from_args(service, project_id, args, existing=existing)
        return _output(asdict(config_service.edit(episode.id, config)), args.json_output)
    if args.episode_command == "show":
        return _output(_episode_payload(config_service, repository, episode), args.json_output)
    if args.episode_command == "plan":
        planner = _planner(composition, project_id, episode.id)
        return _output(asdict(planner.build_plan(episode.id)), args.json_output)
    if args.episode_command == "show-plan":
        planner = _plan_reader(composition, project_id)
        return _output(asdict(planner.load_plan(episode.id)), args.json_output)
    if args.episode_command == "generate":
        run = composition.create_generation_run(project_id, episode.id)
        result = composition.run_generation(project_id, run.id)
        return _output(asdict(result.run), args.json_output)
    if args.episode_command in {"pause", "cancel", "resume", "status"}:
        return _episode_run_command(composition, episode, args)
    if args.episode_command == "export":
        return _output(
            _export_episode(composition, project_id, episode, args.output_dir),
            args.json_output,
        )
    return 2


def _episode_run_command(
    composition: ProductionComposition,
    episode: EpisodeRecord,
    args: argparse.Namespace,
) -> int:
    runs = composition.generation_run_repository(episode.project_id)
    run = runs.latest_for_episode(episode.id)
    if args.episode_command == "status":
        return _output(_status_payload(episode, run), args.json_output)
    if run is None:
        raise KeyError(f"no generation run for episode: {episode.id}")
    pipeline = composition.generation_pipeline(episode.project_id)
    if args.episode_command == "pause":
        pipeline.request_pause(run.id)
        updated = runs.get(run.id)
    elif args.episode_command == "cancel":
        pipeline.request_cancel(run.id)
        updated = runs.get(run.id)
    else:
        updated = pipeline.resume(run.id)
    assert updated is not None
    return _output(asdict(updated), args.json_output)


def _episode_config_from_args(
    service: DeeperDiveService,
    project_id: str,
    args: argparse.Namespace,
    *,
    existing: EpisodeConfiguration | None = None,
) -> EpisodeConfiguration:
    hosts = _csv(getattr(args, "hosts", None))
    if not hosts and existing is None:
        hosts = tuple(host.id for host in service.hosts(project_id).list_hosts(project_id))
    research_overrides = dict(existing.research_overrides) if existing is not None else {}
    if args.research_policy is not None:
        research_overrides["policy"] = args.research_policy
    if args.citation_behavior is not None:
        research_overrides["citation_behavior"] = args.citation_behavior
    return EpisodeConfiguration(
        title=_arg_or_existing(args.title, existing.title if existing else None, "title"),
        focus=_arg_or_existing(args.focus, existing.focus if existing else "", "focus"),
        audience=_arg_or_existing(
            args.audience, existing.audience if existing else "general", "audience"
        ),
        technical_depth=_arg_or_existing(
            args.technical_depth,
            existing.technical_depth if existing else "balanced",
            "technical_depth",
        ),
        target_duration_seconds=int(
            _arg_or_existing(
                args.target_duration_seconds,
                existing.target_duration_seconds if existing else 1800,
                "target_duration_seconds",
            )
        ),
        style=_arg_or_existing(args.style, existing.style if existing else "discussion", "style"),
        host_ids=hosts or (existing.host_ids if existing is not None else ()),
        must_cover=_csv(args.must_cover) or (existing.must_cover if existing is not None else ()),
        avoid_topics=_csv(args.avoid_topics)
        or (existing.avoid_topics if existing is not None else ()),
        research_overrides=research_overrides,
        source_overrides=dict(existing.source_overrides) if existing is not None else {},
        model_overrides=dict(existing.model_overrides) if existing is not None else {},
    )


def _arg_or_existing(value: Any, fallback: Any, field_name: str) -> Any:
    if value is not None:
        return value
    if fallback is not None:
        return fallback
    raise ValueError(f"episode {field_name} is required")


def _csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _planner(
    composition: ProductionComposition,
    project_id: str,
    episode_id: str,
) -> EpisodePlannerService:
    assignments, errors = composition.effective_model_role_assignments_for_episode(
        project_id, episode_id
    )
    if errors:
        raise ValueError("; ".join(errors))
    assignment = assignments.resolve(model_roles.ModelRole.EPISODE_PLANNING)
    if assignment is None:
        raise ValueError("no provider/model assignment for episode_planning")
    return composition.configured_planning_service(
        project_id,
        assignment.provider,
        assignment.model,
    )


def _plan_reader(composition: ProductionComposition, project_id: str) -> EpisodePlannerService:
    return composition.planning_service(project_id, _UnavailablePlanGenerator())


class _UnavailablePlanGenerator:
    def generate_plan(self, request: dict[str, Any]) -> dict[str, Any]:
        _ = request
        raise RuntimeError("episode plan generation is not configured")


def _episode_record(
    record: EpisodeRecord | None, project_id: str, episode_id: str
) -> EpisodeRecord:
    if record is None or record.project_id != project_id:
        raise KeyError(f"episode not found: {episode_id}")
    return record


def _episode_payload(
    config_service: EpisodeConfigurationService,
    repository: Any,
    episode: EpisodeRecord,
) -> dict[str, object]:
    return {
        "episode": asdict(episode),
        "configuration": asdict(config_service.load_configuration(episode.id)),
        "host_ids": repository.list_episode_host_ids(episode.id),
    }


def _status_payload(
    episode: EpisodeRecord,
    run: GenerationRunRecord | None,
) -> dict[str, object]:
    return {"episode": asdict(episode), "run": None if run is None else asdict(run)}


def _export_episode(
    composition: ProductionComposition,
    project_id: str,
    episode: EpisodeRecord,
    output_dir: Path | None,
) -> dict[str, object]:
    run = composition.generation_run_repository(project_id).latest_for_episode(episode.id)
    export = EpisodeLibraryExportService(composition.service.workspaces).export(
        project_id,
        episode,
        run,
        output_dir=output_dir,
    )
    return {
        "episode_id": episode.id,
        "transcript": str(export.transcript),
        "manifest": str(export.manifest),
        "metadata": str(export.metadata),
        "audio": None if export.audio is None else str(export.audio),
        "paths": [str(path) for path in export.paths],
        "path": str(export.metadata),
    }


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
            print(f"{source.id}\t{'included' if source.included else 'excluded'}\t{source.title}")
    return 0


def _output_source(source: SourceRecord, json_output: bool) -> int:
    if json_output:
        print(json.dumps(asdict(source), sort_keys=True))
    else:
        print(f"{source.id}\t{'included' if source.included else 'excluded'}\t{source.title}")
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
            print(
                json.dumps(item, sort_keys=True, default=_json_default)
                if isinstance(item, dict)
                else str(item)
            )
    elif isinstance(value, dict) and "name" in value:
        print(f"{value.get('id', '')}\t{value['name']}")
    else:
        print(json.dumps(value, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
