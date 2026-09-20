# Production composition

`deeper_dive.composition.ProductionComposition` is the single production dependency-composition boundary for Deeper Dive. Product surfaces must obtain shared services from this root rather than silently constructing deterministic substitutes.

## Object graph

The composition root owns the application-wide workspace and user-configuration boundary:

- `WorkspaceManager` -> `DeeperDiveService`
- workspace data directory -> `UserConfigStore`
- `UserConfigStore` -> `ProviderFactory` -> LLM/TTS registries plus effective network-scope metadata
- provider registries + config store -> `ProviderController`
- project workspace lookup -> `PersistentResearchController`
- shared preflight and generation-monitor controllers

The completed composition root must also own the production planning, pipeline orchestration, episode export, transcript repair/regeneration, TTS benchmark, and audio playback services. TUI controllers and CLI handlers are surface adapters over these shared services; they must not create independent production implementations.

## Provider boundary

Persisted provider records identify concrete adapters (`openai`, `ollama`, `llama-server`, `kitten`, `openai-tts`, `openai-compatible-tts`, `elevenlabs`, or an explicitly selected deterministic fake). Capability class (LLM versus TTS) is derived from the adapter identity. Credentials remain environment references and are never persisted in `UserConfig`.

Tests may substitute deterministic providers through `ProviderFactory` or service injection points. Production code must not fall back to a fake provider merely because configuration is absent.

## Surface ownership

The Textual application is constructed from `ProductionComposition`; screens receive controllers/services from that composition. CLI commands must use the same underlying planning, provider, pipeline, export, research, benchmark, repair, and playback services as their TUI counterparts. CLI parsing and rendering remain surface-specific.

## Configuration and lifecycle invariants

Effective provider/model assignments are resolved once through the shared configuration path and consumed consistently by planning, preflight, and generation. Episode overrides take precedence over project defaults, which take precedence over user/application defaults; built-in fallbacks are permitted only where explicitly documented.

Generation state is durable state produced by the pipeline. UI or CLI controls may request pause, cancel, or resume, but must not manufacture those states directly. Export, transcript repair, playback, and resume operations must resolve artifacts by the selected episode/run identity so work cannot cross episode boundaries.

## Construction rule

When adding a production capability, add it to `ProductionComposition` first and inject it into both product surfaces. A second ad-hoc construction path is a regression unless the object is strictly surface-local and stateless.
