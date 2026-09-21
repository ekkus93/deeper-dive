# DDR-091 current composition wiring status

**Date:** 2026-09-21  
**Scope:** Current state of `docs/DEEP_DIVE_V1_INTEGRATION_REMEDIATION_TODO_2026-09-19.md` DDR-091.

## Completed wiring slices

- Research CLI commands now consume the `research_controller` provided by `ProductionComposition` instead of constructing a separate `PersistentResearchController` path.
- Provider CLI inspection now routes through production-composed provider configuration and registries instead of constructing hard-coded fake providers in `deeper_dive.command`.
- The configured fake LLM adapter built by `ProviderFactory` now returns a deterministic episode-plan-shaped response. This keeps CI-safe planning fakes behind explicit persisted provider configuration rather than a command-local planner.
- Developer architecture notes identify `ProductionComposition.build` as the current production object graph entry point for TUI and CLI surfaces.
- TUI Episode Setup planning now reuses the app's existing production composition boundary instead of constructing a second `ProductionComposition` while building a plan.

## Remaining DDR-091 work

- `episode plan` still needs to move from `_DeterministicPlanGenerator` to configured planning through `ProductionComposition.configured_planning_service`.
- `episode generate`, `pause`, `cancel`, and `resume` still need real orchestration semantics instead of command-local run-state mutation.
- `episode export` still needs to use the shared exporter path instead of command-local metadata JSON assembly.
- The older `docs/ARCHITECTURE.md` DDR-091 paragraph should be refreshed once these remaining paths are either migrated or deliberately retained with narrow documentation.

## Qualification rule

Do not close DDR-091 until the remaining paths above are implemented or explicitly narrowed, exact-head CI passes for the final reconciliation change, and the result is merged to `master`.
