# Production generation behavior

This guide describes the user-facing generation contract for Deeper Dive: provider-backed generation, deterministic development providers, preflight/start parity, duplicate-run behavior, TTS audio artifact semantics, and explicit export behavior.

## Provider-backed production generation

Production generation is provider-backed. Episode planning, host-turn generation, optional directing, optional transcript verification, and TTS synthesis resolve provider/model assignments through durable user configuration and the provider registry. The production pipeline should not create hidden canned transcript turns or fake audio unless the user explicitly configured the deterministic fake providers.

A normal generation path is:

1. Configure LLM and TTS providers in user configuration or through the Providers TUI.
2. Assign model roles such as `episode_planning`, `host_generation`, `directing`, and `verification` to `provider:model` identities.
3. Assign each host a TTS provider and voice.
4. Create or edit an episode configuration.
5. Build a plan.
6. Run preflight and review blockers, warnings, provider routes, locality, FFmpeg status, and estimates.
7. Start generation from the CLI or TUI.
8. Review the transcript and generated audio artifacts.
9. Export transcript, manifest, metadata, and audio artifacts explicitly.

Generated turns retain provider/model identity evidence where the generation provider supplies it, and TTS artifacts retain provider, voice, model, cache key, status, and filesystem path metadata. Provider credentials are not stored in project databases or exports.

## Deterministic CI and development providers

The `fake` LLM provider and `fake-tts` TTS provider are deterministic provider-boundary adapters for CI, local development, and acceptance fixtures. They are not hidden production shortcuts. They participate through the same durable configuration, provider factory, preflight, shared generation start service, pipeline, repositories, and export services used by production adapters.

Use fake providers when you need ordinary CI to verify generation semantics without network access, paid credentials, model downloads, GPUs, or live external services. Do not interpret fake-provider output as a product shortcut; production behavior is still configured-provider behavior.

## CLI and TUI preflight/start parity

The CLI `episode generate` command and the TUI Generate screen both use the shared generation start service where production composition is available. That shared boundary runs preflight-equivalent readiness checks before creating a run.

Generation is blocked before run creation when required inputs are missing or invalid, including missing sources, unindexed sources, missing hosts, missing host TTS assignment, missing or invalid model-role assignments, unavailable provider/model identities, or missing FFmpeg.

CLI and TUI surfaces should report sanitized, actionable blockers. They should not create partial generation output when preflight blocks the run.

## Duplicate-run behavior

Generation starts are duplicate-safe for one episode. Existing active runs in `pending`, `running`, or `paused` states are reused rather than replaced. Terminal runs such as `completed`, `failed`, or `cancelled` allow a new attempt. Active runs with cancellation requested can be replaced by a new attempt after cancellation handling.

Pause, resume, cancel, status, Episode Library resume, and Episode Library export target the selected episode/run identity and should not silently switch to another episode just because it is the current TUI episode.

## TTS provider, voice, and audio artifacts

Each host must have an explicit TTS provider and voice when audio generation is required. The TTS stage resolves the host assignment through the configured TTS provider registry, validates the voice against the provider catalog, and writes durable TTS artifacts.

The canonical successful TTS artifact status is `complete`. Legacy successful rows with status `completed` are read and normalized to `complete` by the artifact repository. Cache lookup and export should treat normalized legacy success rows as valid only when the artifact file still exists and is non-empty.

TTS artifacts record the turn ID, artifact ID, cache key, status, path, provider ID, voice, and optional model. Export uses those artifacts and the episode audio produced by the composition stage rather than re-synthesizing by default.

## Export semantics and pipeline stage semantics

The generation pipeline `export` stage is a durable readiness checkpoint. It marks that generation has reached the point where explicit export is possible. It does not by itself write the exported transcript, manifest, metadata, or audio files.

Concrete export artifacts are created by explicit CLI export or Episode Library export through the export service. Export outputs include transcript, manifest, metadata, and audio when audio is available. Metadata records the project, episode, and run identity so downstream tooling can distinguish generation completion from explicit exported files.

See also `docs/GENERATION_PIPELINE_STAGE_SEMANTICS.md` and `docs/GENERATION_RUN_SELECTION_POLICY.md` for the lower-level run and stage contracts.
