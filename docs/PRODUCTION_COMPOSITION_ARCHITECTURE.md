# Production composition architecture

`ProductionComposition` is the production dependency root shared by the TUI and CLI. Surface code should obtain planning, preflight, generation, export, provider, research, playback, benchmark, and transcript-repair capabilities through this composition path rather than constructing parallel implementations.

## Shared-service rule

TUI and CLI entry points are adapters over the same application services. Episode planning uses `EpisodePlannerService`; generation uses `PipelineOrchestrator`; export uses the shared episode/export services; provider construction goes through `ProviderFactory` and the production registries. New surface-specific implementations should be avoided when an existing production service expresses the operation.

## Test doubles

Deterministic/fake implementations belong at explicit provider or service injection boundaries. Production surface code must not select deterministic planners, LLMs, TTS engines, or other fake behavior implicitly. Tests may substitute deterministic adapters while retaining the production composition and durable repositories so integration tests exercise the same object graph as the application.

## Artifact identity

Episode/run identity is carried through durable generation, transcript, audio, playback, and export paths. Consumers must resolve artifacts for the selected episode/run rather than scanning for an arbitrary file. This invariant is what allows multi-episode projects to remain isolated.

## Maintenance guidance

When adding a CLI or TUI action, first expose or reuse the operation on the shared service layer, then make each surface a thin adapter. This keeps provider routing, persistence, sanitization, lifecycle semantics, and qualification behavior consistent across interfaces.
