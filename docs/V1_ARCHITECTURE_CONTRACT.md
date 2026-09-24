# V1 architecture contract

This document records the final V1 integration boundaries used by the remediation qualification suite.

## Composition root

`ProductionComposition.build()` is the production object-graph entry point. It initializes workspace/configuration state, constructs providers through `ProviderFactory`, and exposes shared provider, research, preflight, generation, benchmark, playback, planning, export, and repair boundaries. Product surfaces should enter through this composition rather than construct surface-specific production substitutes.

## Provider factory

Persisted provider configuration records concrete adapter identity. `ProviderFactory` validates configuration and builds normalized LLM/TTS adapters and registries. Local/remote network-scope metadata remains available to preflight. Deterministic providers are injected at the provider boundary for tests; they are not alternate TUI/CLI implementations.

## Shared TUI and CLI service layer

Planning routes through `EpisodePlannerService`; preflight through `PreflightService`; generation/control through `PipelineOrchestrator` and durable generation-run repositories; episode export through the shared exporter path; research through shared research services/controllers; transcript repair through `TargetedRepairService`; provider inspection through the production provider controller/registries. TUI and CLI are presentation clients of these boundaries.

## Run and control lifecycle

A generation run is durable state, not a UI status label. Normal execution moves from pending into running and then a documented terminal/control state. Pause is cooperative and becomes durable only at a safe boundary. Resume requires a valid paused/checkpointed run and re-enters orchestration from durable completed work. Cancel records durable cancellation. Failures record sanitized failure information. Completed/cancelled/otherwise illegal transitions are rejected. Reconstructing the application/orchestrator must not destroy resumability.

## Artifact identity and export contract

Episode identity scopes transcript turns, TTS/audio artifacts, playback, review state, generation runs, and exports. Export produces a transcript, source/provenance manifest, metadata, and audio when present. Metadata carries project, episode, and run identity. Multi-episode qualification requires selecting episode A never to read, play, mutate, or export episode B artifacts. Duplicate/delete operations must preserve sibling isolation.

## TTS artifact status contract

The canonical successful TTS artifact status is `complete`, exposed in code as `TTS_ARTIFACT_STATUS_COMPLETE`. Writers must store the canonical value. Readers preserve persisted-data compatibility by accepting legacy successful `completed` rows and normalizing them to the canonical status at the repository boundary. Cache lookup, timeline visibility, episode export, installed-wheel smoke checks, and production-pipeline tests must assert the canonical status while continuing to support legacy successful rows.

## Sanitizer boundary

`deeper_dive.diagnostics` provides the canonical redaction/sanitization boundary. Untrusted provider/pipeline exception material is sanitized before durable failure persistence, structured diagnostic logging, diagnostic-bundle creation, or CLI/TUI presentation. Sanitization covers authorization headers, API-key/token/environment-style assignments, credential-bearing URLs, nested exception context, and debug/repr payloads while retaining actionable non-secret context.

## Deterministic CI provider strategy

Ordinary CI must require no paid credentials, live provider services, model downloads, GPUs, or live web access. Production composition is exercised with durable configuration while deterministic adapters are substituted only at provider/search/fetch boundaries. Acceptance fixtures should create real project/source/host/episode/plan/run/transcript/audio/export state and assert durable artifacts and terminal states. Live-provider or real-model checks remain bounded, explicit qualification smokes; the installed-wheel KittenTTS CPU smoke is one such gate.
