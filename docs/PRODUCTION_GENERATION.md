# Production generation behavior

This guide describes the user-facing and developer-facing generation contract for Deeper Dive: provider-backed planning and generation, bounded multi-turn conversations, deterministic development providers, preflight/start parity, plan validity and evidence integrity, duplicate-run behavior, TTS/audio artifact semantics, transcript repair, sanitization, composition ownership, and explicit export behavior.

## Provider-backed production generation

Production generation is provider-backed. Episode planning, host-turn generation, optional directing, optional transcript verification, and TTS synthesis resolve provider/model assignments through durable user configuration and the provider registry. The production pipeline does not create hidden canned transcript turns or fake audio unless the user explicitly configured the deterministic fake providers.

A normal generation path is:

1. Configure LLM and TTS providers in user configuration or through the Providers TUI.
2. Assign model roles such as `episode_planning`, `host_generation`, `directing`, and `verification` to `provider:model` identities.
3. Assign each host a TTS provider and voice.
4. Create or edit an episode configuration.
5. Build a plan, or allow `episode generate` to auto-plan when no valid usable plan exists.
6. Run preflight and review blockers, warnings, provider routes, locality, FFmpeg status, and estimates.
7. Start generation from the CLI or TUI.
8. Review the transcript and generated audio artifacts.
9. Export transcript, manifest, metadata, and audio artifacts explicitly.

Generated turns retain provider/model identity evidence where the generation provider supplies it, and TTS artifacts retain provider, voice, model, cache key, status, and filesystem path metadata. Provider credentials are not stored in project databases or exports.

## Multi-turn and multi-segment conversation contract

Conversation generation consumes ordered durable plan segments and resumes durable `ConversationState` rather than treating the existence of any turn as stage completion. It generates successive turns until the director signals `COMPLETE_SEGMENT` or `COMPLETE_EPISODE`; `CONTINUE` keeps the current segment active. When directing is not assigned, the production service uses a bounded fallback rather than an unbounded loop.

Generation is bounded by per-segment and per-episode turn limits and by the episode duration/word budget. A provider that never emits completion cannot run forever, while an early valid completion signal is honored. Each durable turn records its evidence and provider/model identity together with conversation state/checkpoint progress so an interrupted run resumes from the first incomplete unit without duplicating completed turns.

Speakers remain restricted to hosts participating in the episode, and evidence remains restricted to the current episode's usable evidence scope.

## Transactional provider configuration and runtime ownership

Provider save/edit is transactional. A candidate `ProviderConfig` is validated and the complete candidate runtime is built before durable configuration is replaced. The live runtime is published only after persistence succeeds. Invalid adapters, missing required credential environment variables, invalid base URLs, or invalid voice/runtime configuration leave both the prior durable configuration and the prior live runtime intact.

Provider removal follows the same rule: the remaining candidate configuration/runtime must validate before removal is persisted. Removed providers are removed from the authoritative runtime registries rather than surviving in stale controller snapshots.

`ProductionComposition` owns the typed production application/runtime context. Controllers receive that composition explicitly; production code does not discover it through hidden `service._production_composition` attributes. Planning, directing, host generation, verification, TTS, repair, preflight, health, CLI, and TUI consumers therefore observe the same refreshed provider runtime in the same session.

## Deterministic CI and development providers

The `fake` LLM provider and `fake-tts` TTS provider are deterministic provider-boundary adapters for CI, local development, and acceptance fixtures. They are not hidden production shortcuts. They participate through the same durable configuration, provider factory, preflight, shared generation start service, pipeline, repositories, and export services used by production adapters.

Use fake providers when you need ordinary deterministic tests to verify generation semantics without paid credentials, GPU hardware, or live cloud services. Do not interpret fake-provider output as a product shortcut; production behavior is still configured-provider behavior.

## Preflight role and routing policy

The CLI `episode generate` command and the TUI Generate screen both use the shared generation start/preflight boundary. Required model roles are derived from the work the episode will actually execute: `episode_planning` is required when no valid usable plan exists, `host_generation` is required while conversation work remains, and configured `directing` and `verification` roles are validated when they will execute. The resolver is intentionally extensible to future production roles.

Preflight validates provider existence, model availability, voice availability, provider health, and local/remote network policy before expensive generation/run creation where applicable. Locality classification is shared across generation start, TUI preflight, and routing/security presentation. Explicit local or remote overrides take precedence over adapter defaults.

Generation is blocked before run creation when required inputs are missing or invalid, including missing sources, unindexed sources, missing hosts, missing host TTS assignment, invalid model-role assignments, unavailable/unhealthy providers or models, invalid TTS format policy, or missing FFmpeg. CLI and TUI surfaces report sanitized actionable blockers and do not create partial generation output when preflight blocks the run.

If execution fails after a durable run exists, the run is persisted as `failed` with stage, sanitized failure code/message, and timestamp rather than remaining stale in `pending` or `running`.

## Plan validity and evidence integrity

A plan is usable for generation only when it belongs to the episode, contains at least one valid segment, has coherent ordinals, non-empty titles, positive durations, valid participating lead hosts, valid JSON/state, an allowed status, and evidence IDs inside the episode's active evidence scope. Planning skips only a plan that passes this shared validity policy; generation-start role derivation uses the same policy.

Evidence validation is explicit. An active empty evidence scope rejects every evidence ID; it does not disable validation. Plan segment editing and regeneration reject nonexistent or cross-project evidence IDs and preserve valid in-scope evidence. Normal acceptance workflows build plans through `EpisodePlannerService` or the public planning entry point rather than seeding approved plan rows directly.

## Duplicate-run and control behavior

Generation starts are duplicate-safe for one episode. Existing active runs in `pending`, `running`, or `paused` states are reused rather than replaced. Terminal runs such as `completed`, `failed`, or `cancelled` allow a new attempt. Active runs with cancellation requested can be replaced by a new attempt after cancellation handling.

Pause, resume, cancel, status, Episode Library resume, playback, review, and export target the selected episode/run identity and do not silently switch to another episode just because it is the current TUI episode. Pipeline control is cooperative at durable safe stage boundaries.

## TTS provider, voice, format, and audio artifacts

Each host must have an explicit TTS provider and voice when audio generation is required. The TTS stage resolves the host assignment through the configured TTS provider registry, validates the voice against the provider catalog, and writes durable TTS artifacts.

The production composition contract is canonical 24 kHz mono signed-16-bit WAV. Unsupported configured output such as OpenAI-compatible MP3 is rejected during preflight before expensive synthesis rather than being allowed to fail later in WAV composition. KittenTTS remains WAV-only. Production normalization/resampling uses FFmpeg/libswresample through the public FFmpeg conversion API rather than naive sample manipulation or external calls to a private `_run()` helper.

The returned TTS identity is checked against the request: provider and voice must match, and an explicitly requested model must be reported/match according to the adapter contract. The returned audio format and persisted path extension must also agree. Identity/format mismatch cannot be persisted as successful synthesis.

The canonical successful TTS artifact status is `complete`. Legacy successful rows with status `completed` are read and normalized to `complete` by the artifact repository. Cache lookup and export treat normalized legacy success rows as valid only when the artifact file still exists and is non-empty.

TTS artifacts record the turn ID, artifact ID, cache key, status, path, provider ID, voice, optional model, and actual returned audio format. Every turn receives a persisted artifact-reference row. Identical synthesis inputs may share the same cache key, artifact ID, and physical file while retaining separate per-turn rows. Text, provider, voice, model, and synthesis settings participate in cache identity, so a repaired or reconfigured turn cannot silently reuse stale audio.

## Transcript repair, reverification, and cache cleanup

Targeted transcript repair is a production workflow, not a text-only patch. Repaired text is sent through real claim extraction/verification/recheck, conversation summary/context is refreshed where required, and unaffected turns remain unchanged. Repair-triggered audio regeneration goes through the public `ProductionComposition.regenerate_episode_audio()` operation and the shared provider runtime, rebuilding affected TTS, timeline, and episode audio without reaching into private pipeline stages.

Physical TTS cleanup is reference-aware. Replacing a turn's artifact may collect an obsolete file only after no remaining durable turn references it. Shared live cache files are preserved, active artifacts are preserved, and repeated repairs do not accumulate unbounded orphan files.

## Canonical sanitization and export guarantees

Durable and user-visible diagnostics use the canonical recursive sanitizer. It redacts credential-bearing authorization/API-key/token/access-token/refresh-token/secret/client-secret/password/cookie fields, Bearer values, credential-bearing URLs, nested collections/maps, assignment-like strings, and exception cause/context chains while preserving ordinary non-secret provenance and identity data.

Provider health/model/voice discovery failures are sanitized before CLI/TUI presentation or persistence. Provider configuration stores credential references such as environment-variable names rather than credential values. Failed provider saves, structured diagnostics, run failures, CLI/TUI status, and export metadata must not persist credential values.

`EpisodeExporter` applies the same canonical sanitizer recursively to metadata instead of maintaining a separate secret vocabulary.

## Export semantics and pipeline stage semantics

The generation pipeline `export` stage is a durable readiness checkpoint. It marks that generation has reached the point where explicit export is possible. It does not by itself write the exported transcript, manifest, metadata, or audio files.

Concrete export artifacts are created by explicit CLI export or Episode Library export through the shared export service. Export outputs include transcript, manifest, metadata, and audio when audio is available. Metadata records project, episode, and run identity so downstream tooling can distinguish generation completion from explicit exported files and keep multi-episode output isolated.

## Qualification policy

Mandatory deterministic tests use fake/local providers and require no paid credentials or cloud-provider calls. The current fresh-machine CI gate additionally installs the real KittenTTS runtime and runs the KittenTTS Micro CPU smoke. That gate is therefore intentionally **external-network dependent**: it downloads external runtime/model assets during qualification. Paid credentials and paid cloud calls remain excluded from mandatory CI.

Fresh-machine qualification builds the wheel from the checked-out remediation head, installs it into a clean environment, launches the installed CLI and TUI entry points, exercises the installed corpus/episode/planning/generation/export workflow, validates non-empty generated artifacts and sanitizer behavior, and then runs the real KittenTTS smoke.

See also `docs/GENERATION_PIPELINE_STAGE_SEMANTICS.md`, `docs/GENERATION_RUN_SELECTION_POLICY.md`, and `docs/PROVIDERS.md` for lower-level run, stage, and provider contracts.
