# First-run readiness: worker and transport audit (2026-10-10)

**Scope:** SPR-03 of `DEEP_DIVE_TUI_SECOND_POST_REVIEW_REMEDIATION_TODO_2026-10-09.md`. This is an implementation/operational audit, **not** a declaration that SPR-03 is complete.

## UI worker ownership

`src/deeper_dive/guided_async_readiness.py` owns `FirstRunReadinessCoordinator`, instantiated with a per-application worker limit of **2** by default. Requests do not queue: identical in-progress fingerprints coalesce into one probe and deduplicate identical completion callbacks. Distinct fingerprints may supersede the visible generation, but a result from a superseded generation cannot publish. Once the budget is exhausted, the coordinator reports a failed/retryable view without starting another worker. Repeated requests for that same rejected fingerprint now retain one stable failed generation until a worker slot becomes available.

`timeout_seconds` defaults to **8 seconds** for the UI view. This timeout is *not* a cancellation of arbitrary Python/provider code. A timed-out probe remains in the active-worker budget until it actually returns; a late result is ignored. `close()` cancels owned timers and clears callbacks; already-blocked daemon threads cannot be forcibly terminated. No promise of zero surviving threads is made on shutdown. The UI thread does not join blocked workers.

Tests: `tests/test_second_post_review_readiness_budget.py` covers 100 identical refreshes, callback-once coalescing, repeated timeouts with late-success exclusion, two blocked fingerprints plus 100 saturated retries, stable generation, and shutdown callback suppression. These tests use only deterministic fake probes and no network.

## Adapter-level readiness paths and transport limits

| Provider | Readiness calls | I/O boundary | Important qualification |
| --- | --- | --- | --- |
| OpenAI LLM | `health() -> models()` | `openai_llm.py` `GET /models`, `urlopen(timeout=config.timeout_seconds)`; default 60s; up to two retries with short backoff | The logical operation can exceed the UI's 8s timeout. |
| Ollama LLM | `health()`, `models()` | `ollama_llm.py` `GET /api/version`, `GET /api/tags`; `urlopen(timeout=...)` | Each call uses the configured per-request timeout. |
| llama-server LLM | `health()`, `models()` | `llama_server_llm.py` `GET /health`, `GET /v1/models`; `urlopen(timeout=...)` | Each call uses the configured per-request timeout. |
| ElevenLabs TTS | `health() -> voices()` | `elevenlabs_tts.py` `GET /voices`; `urlopen(timeout=...)` | Voice discovery is network I/O, so do not duplicate it during a single readiness check. |
| OpenAI TTS | `health()`, `voices()` | `openai_tts.py` configuration check and static voice catalog | No billable synthesis or network probe for readiness. |
| OpenAI-compatible TTS | `health()`, `voices()` | `openai_compatible_tts.py` configuration check and configured voice catalog | No network probe for readiness. |
| KittenTTS Micro | `health()`, `voices()` | `kitten_tts.py` local runtime availability and static voice catalog until runtime loaded | No model download or synthesis in readiness. |
| Fake LLM/TTS | `health()`, `models()/voices()` | In-memory deterministic implementations | Used for offline acceptance and stress tests. |

The `ProviderFactory` propagates persisted `ProviderConfig.timeout_seconds` to network adapters. The config contract currently accepts positive values up to **600 seconds** and defaults to **60 seconds**. `FirstRunController` additionally uses a short **0.35-second** timeout for its direct local-port probe. Provider health, model and voice discovery should not run on Textual's event loop.

**Limit:** `urllib.request.urlopen(timeout=...)` is a socket operation timeout, not an end-to-end deadline covering every DNS resolution, retry, redirect and incremental read. The UI timeout therefore cannot guarantee transport cancellation. The bounded worker budget is the safety backstop; it deliberately favors responsiveness and bounded resource use over starting unlimited replacement probes.

## Retry and operational guidance

If readiness reports that workers are still finishing timed-out checks, check provider connectivity and the configured provider timeout. Wait for the underlying request to complete before retrying. Repeated refreshes while both slots are occupied do not create new workers or a queue. Changing provider configuration changes the fingerprint but cannot bypass the worker budget. No provider credentials should appear in the visible status; errors pass through the shared sanitizer.

## Qualification and remaining SPR-03 work

- Exact-head CI for callback and shutdown regressions: `57fe0e992735c1674047211a5e72d539d4d9b16b`, run `38037509169` (quality and fresh-machine passed).
- Exact-head CI for stable-generation retry guard: `284128883fc8afe49c6290203b27bd0688944fb1`, run `38038291569` (quality and fresh-machine passed).
- Still required before checking SPR-03 complete: confirm per-application ownership/shutdown across every Textual entry point, transport-level test doubles that verify configured timeout propagation and retry bounds for every network adapter, callback/fingerprint race matrix, and installed-wheel acceptance with intentionally blocking providers.
