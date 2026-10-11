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

`ProviderFactory` propagates `ProviderConfig.timeout_seconds` to normal HTTP-capable generation adapters. The persisted field defaults to **60 seconds** and permits values greater than zero and up to **600 seconds**. **First-run readiness** instead calls `ProviderController.readiness_probe_controller(request_timeout_seconds=min(ui_timeout/4, 1.0))` to build **isolated** adapters. The probe factory caps each configured transport timeout to that shorter budget, while leaving the live generation registry and persisted configuration untouched. OpenAI discovery uses zero retries in readiness adapters (normal generation retains its separate retry policy); Ollama, llama-server and ElevenLabs discovery use the short per-operation timeout. These remain per-request socket budgets, **not strict end-to-end wall-clock deadlines**; serial adapter work and uninterruptible provider calls are still possible.

`FirstRunController.system_check()` also probes `/api/tags` and `/health` using `urlopen(..., timeout=0.35)`. That is a socket timeout per probe, not an end-to-end cancellation mechanism.

## Coordinator budget, limitations, and pending acceptance

`FirstRunReadinessCoordinator` defaults to `timeout_seconds=8.0` for the visible readiness result, and `max_workers=2` per coordinator with no pending queue. It coalesces identical fingerprints, rejects new work when all slots remain occupied, and prevents late/superseded publication. The timeout timer does **not** interrupt a blocked provider socket call; the daemon worker stays within the bounded worker budget until the underlying call exits. Shutdown cancels timers and callbacks, but cannot forcibly terminate non-cooperative Python threads.

**Accepted partial transport evidence:** `tests/test_second_post_review_readiness_transport.py` injects deterministic fake requests through production adapter boundaries: Ollama/llama-server health and model calls use the bounded timeout, OpenAI discovery makes one bounded attempt on a synthetic timeout, ElevenLabs calls voice discovery only once, and repeated probe construction neither mutates the published generation registry nor persists any timeout change. These source/test paths were included in the full passing exact-head [CI #2639](https://github.com/ekkus93/deeper-dive/actions/runs/38152619285) at `d215cf2cb0132790a9f5bc3fc0e92cc61a94fa2d` (quality/fresh-machine passed). A true wall-clock cancellation guarantee for uncooperative providers is **not** claimed.

**Open requirement:** Exercise the shortened transport boundary in a full installed-wheel Textual first-run acceptance flow, verify app navigation remains responsive with deliberately never-returning fake probes, audit all default/adaptor-specific deadlines, and document/shutdown behavior on supported platforms. Do not mark the rest of SPR-03 complete from this inventory.

**Source references:** `src/deeper_dive/guided_async_readiness.py`, `guided_readiness.py`, `first_run.py`, `provider_factory.py`, `user_config.py`, `llm.py`, `tts.py`, `openai_llm.py`, `ollama_llm.py`, `llama_server_llm.py`, `openai_tts.py`, `openai_compatible_tts.py`, `elevenlabs_tts.py`, and `kitten_tts.py`.
