# DDR-091 composition/API duplication review

**Date:** 2026-09-21

## Current production composition entry point

`ProductionComposition.build(...)` is the current production object-graph entry point for both TUI construction and several CLI/research/provider paths. It owns construction of the application service, provider controller, research controller, preflight controller, generation monitor controller, benchmark service, playback controller, transcript-repair service, and exporter service.

## Remaining duplication and narrowing

The review found these remaining duplication seams that should be remediated in code slices rather than closed by documentation alone:

- `EpisodeSetupScreen.action_build_plan` still reaches the retained production composition indirectly through `service._production_composition`. The desired boundary is an explicit app-owned `production_composition` reference so TUI screens do not rely on hidden service attributes.
- CLI `episode plan` still uses a command-local deterministic planner path. It should be routed through the shared production planning service, with deterministic behavior supplied through configured fake providers or explicit test/development injection.
- CLI `episode export` still assembles metadata JSON directly. It should use the shared `EpisodeExporter` path and assert real artifact contents.
- Generation command/control paths remain partially command-local and should continue moving toward the shared `PipelineOrchestrator` contract.

## Already-qualified supporting evidence

- Provider CLI and research CLI work now use production composition/controller paths where recently remediated.
- TUI preflight/generation setup uses production controllers supplied by `ProductionComposition`.
- DDR-003 introduced production-composed model-role resolution through `ProductionComposition.effective_model_role_assignments(...)`.
- DDR-090 removed the broad Ruff test-file exclusion list and kept merged-master CI green.

## Follow-up implementation targets

1. Expose `ProductionComposition` explicitly on `DeeperDiveApp` and route Episode Setup planning through that app-level boundary.
2. Replace CLI `episode plan` deterministic construction with the shared production planning service while keeping deterministic fake providers injected/configured for CI.
3. Replace metadata-only CLI export with the shared exporter service.
4. Keep fake implementations behind provider/service injection points, not command-local production branches.

This note is evidence for the DDR-091 architecture-notes subtask only; it does not close the implementation subitems above.
