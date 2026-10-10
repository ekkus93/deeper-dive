# SPR-03 — First-run readiness transport and retry inventory

**Source audited:** `master` `adc123441d7ad646c16dc6396764fcf6a9a87e8e` (2026-10-10).
**Scope:** Every production `health()`, `models()`, and `voices()` operation reachable through first-run readiness, not generation or speech synthesis.

## Production call graph

`FirstRunReadinessCoordinator._probe_runtime` runs `first_run_readiness(context)` and `FirstRunController.system_check()` in its bounded background worker. `first_run_readiness` iterates configured LLMs and checks health/model discovery through `_llm_runtime_ready`, then validates the selected TTS provider and voice through `_tts_runtime_ready`. OpenAI LLM avoids duplicate discovery by calling `models()` without `health()`; ElevenLabs TTS calls `voices()` without `health()` for the same reason. `FirstRunController.status()` is local, while `system_check()` separately probes configured/default Ollama and llama-server endpoints.

## Provider I/O inventory

| Production adapter | Health/discovery path in first run | Transport and retries |
| --- | --- | --- |
| `FakeLLMProvider` | `health()`, `models()` | Local deterministic, no socket |
| `OpenAILLMProvider` | `models()` once per readiness refresh (health also delegates to models when explicitly invoked) | `GET /models` via `urlopen(..., timeout=self._timeout)`; default `max_retries=2` allows up to three attempts on rate limit/timeout, with short backoff |
| `OllamaLLMProvider` | `health()` then `models()` | `GET /api/version` and `GET /api/tags`; each `urlopen` receives configured timeout; no adapter retry loop for these calls |
| `LlamaServerLLMProvider` | `health()` then `models()` | Health and model endpoint GETs; each `urlopen` receives configured timeout; no adapter retry loop for these calls |
| `FakeTTSProvider` | `health()`, `voices()` | Local deterministic, no socket |
| `KittenTTSMicroProvider` | `health()`, `voices()` | Local runtime availability check and metadata; model loading/synthesis are not triggered |
| `OpenAITTSProvider` | `health()`, `voices()` | Local configuration/voice metadata only; `synthesize()` has separate network timeout/retry behavior, outside readiness |
| `OpenAICompatibleTTSProvider` | `health()`, `voices()` | Local configuration/voice metadata only; `synthesize()` has separate network timeout behavior |
| `ElevenLabsTTSProvider` | `voices()` once per readiness refresh (health also delegates to voices when explicitly invoked) | `GET /voices` via `urlopen(..., timeout=self._timeout)`; no adapter retry loop for this discovery |

`ProviderFactory` propagates `ProviderConfig.timeout_seconds` to the HTTP-capable adapters. The persisted field defaults to **60 seconds** and permits values greater than zero and up to **600 seconds**. These are per-request socket timeouts, **not strict end-to-end wall-clock deadlines**; the provider may perform sequential operations and OpenAI discovery may retry.

`FirstRunController.system_check()` also probes `/api/tags` and `/health` using `urlopen(..., timeout=0.35)`. That is a socket timeout per probe, not an end-to-end cancellation mechanism.

## Coordinator budget, limitations, and pending acceptance

`FirstRunReadinessCoordinator` defaults to `timeout_seconds=8.0` for the visible readiness result, and `max_workers=2` per coordinator with no pending queue. It coalesces identical fingerprints, rejects new work when all slots remain occupied, and prevents late/superseded publication. The timeout timer does **not** interrupt a blocked provider socket call; the daemon worker stays within the bounded worker budget until the underlying call exits. Shutdown cancels timers and callbacks, but cannot forcibly terminate non-cooperative Python threads.

**Open requirement:** Enforce or document appropriately shortened readiness-specific transport budgets so a configured 60–600-second socket timeout and OpenAI retry loop do not leave both readiness workers occupied long after the eight-second UI timeout. Prove deadline/retry behavior via fake transport and installed-wheel Textual acceptance; do not mark the rest of SPR-03 complete from this inventory.

**Source references:** `src/deeper_dive/guided_async_readiness.py`, `guided_readiness.py`, `first_run.py`, `provider_factory.py`, `user_config.py`, `llm.py`, `tts.py`, `openai_llm.py`, `ollama_llm.py`, `llama_server_llm.py`, `openai_tts.py`, `openai_compatible_tts.py`, `elevenlabs_tts.py`, and `kitten_tts.py`.
