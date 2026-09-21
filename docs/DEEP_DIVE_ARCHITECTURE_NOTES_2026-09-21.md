# Deeper Dive Architecture Notes

**Date:** 2026-09-21  
**Scope:** DDR-091 composition/API duplication review.

## Production composition boundary

`src/deeper_dive/composition.py` is the production composition root for the TUI and for shared production services. `ProductionComposition.build()` owns construction of the application service, durable configuration store, provider factory output, provider controller, research controller, preflight controller, generation monitor controller, TTS benchmark service, and playback controller.

The composition root intentionally exposes narrower service constructors for project-scoped capabilities:

- `database_for_project(project_id)` returns the production project database boundary.
- `planning_service(project_id, generator)` constructs the shared planning service with an explicit provider/generator boundary.
- `configured_planning_service(project_id, provider_id, model)` resolves a configured LLM provider through the production provider registry and adapts it to planning.
- `pipeline_service(project_id, handlers, progress=None)` constructs the durable `PipelineOrchestrator` with injected stage handlers.
- `exporter(project_id)` constructs the shared episode exporter rooted in the selected project workspace.
- `targeted_repair_service(...)` constructs transcript repair with explicit repair/recheck/summary provider boundaries.

## Shared TUI wiring

`src/deeper_dive/tui.py` constructs a `ProductionComposition` during app initialization and consumes its production controllers unless a test explicitly injects a controller double. That keeps TUI tests injectable while keeping the production app construction path explicit.

Generation Monitor is now production-wired through `ProductionComposition.build()`: its runner resolves the project for a durable run, constructs a `PipelineOrchestrator`, and executes the durable stage-boundary handlers. Richer stage-specific generation services can replace those handlers without changing the monitor surface.

## CLI duplication still to remove

`src/deeper_dive/cli.py` still constructs some services directly. The largest remaining duplications are:

- It creates `DeeperDiveService(WorkspaceManager(args.data_dir))` instead of consuming `ProductionComposition.build(data_dir=args.data_dir).service`.
- It constructs `PersistentResearchController` directly rather than using `ProductionComposition.research_controller`.
- It uses a private `_DeterministicPlanGenerator` as the CLI planning implementation instead of routing production planning through `ProductionComposition.configured_planning_service(...)` with deterministic providers injected only in tests or development fixtures.
- It creates `GenerationRunRepository`, `EpisodePlannerService`, and project `Database` boundaries directly for some episode commands rather than using composition-root service constructors.

These duplicate paths should be removed incrementally, with tests moved to explicit deterministic provider boundaries rather than production code relying on private fake or deterministic implementations.

## Test/development fake policy

Fake and deterministic implementations are acceptable when they are injected at provider or stage-handler boundaries. They should not be hidden inside production command handlers as the only implementation path. Production-facing surfaces should construct their dependencies through `ProductionComposition` and accept test fakes only through explicit injection points.

## Near-term DDR-091 follow-up

The next implementation slice should route CLI startup through `ProductionComposition.build(data_dir=args.data_dir)` while preserving current command behavior. After that, research, planning, pipeline, and export CLI commands can be migrated from direct constructors to composition-root service methods one command family at a time.
