# Provider runtime consumer inventory

**Date:** 2026-09-27  
**Follow-up checklist:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_FOLLOWUP_TODO_2026-09-25.md` R1 / PCG-FU-001

This inventory identifies the production runtime consumers that must share refreshed provider registries after same-session provider saves, removals, or reloads.

## Runtime refresh boundary

`ProductionComposition.refresh_providers()` is the canonical refresh boundary. `ProviderController.reload()` rebuilds providers through `ProviderFactory.build()` and calls the composition refresh callback. The callback replaces `ProductionComposition.providers` and rebinds dependent runtime services so the process does not continue with stale registries.

## Consumers

| Consumer | Runtime dependency | Required invariant |
| --- | --- | --- |
| `ProviderController` | Controller-local LLM registry and TTS provider map | Saves/removes/reloads rebuild controller registries and invoke the composition refresh callback. |
| `ProductionComposition.providers` | Shared `ProviderBuildResult` | The composition snapshot is replaced on reload rather than retaining startup registries. |
| `PreflightService` | LLM and TTS registries | Preflight uses the same refreshed registries that generation will use. |
| Planning stage | Refreshed LLM registry through configured `episode_planning` assignment | Auto-planning resolves the configured provider/model from the refreshed production registry and fails durably on missing or invalid assignments. |
| Conversation generation | Refreshed LLM registry through `host_generation` and optional `directing` assignments | Generated host turns and directing decisions use the same configured provider set validated by preflight. |
| TTS generation | Refreshed TTS registry and selected host provider/voice | Synthesis resolves every host turn through the refreshed TTS providers and records provider/voice/model/format identity. |
| Provider health | `ProviderController.health()` routed through refreshed adapters | Same-session health checks report the current adapter state, not startup state. |
| Export and audio composition | Durable artifacts produced by refreshed generation/TTS stages | Export/composition must not create a separate provider registry; it consumes the durable turn, provenance, timeline, and TTS artifact identity written by the refreshed generation path. |

## Explicit non-consumers

Export and audio composition are not provider factories. They do not resolve LLM or TTS providers at export time. Their provider-related correctness comes from durable artifact identity: transcript turns, cited evidence IDs, TTS artifact rows, timeline entries, and composed audio written by the production generation path.

## Regression anchors

- `tests/test_followup_provider_runtime.py::test_same_session_provider_save_refreshes_preflight_generation_and_export` covers same-session `ProviderController.save_provider()` followed by provider health, preflight, generation, and Episode Library export without rebuilding the composition.
- `tests/test_followup_provider_runtime.py::test_same_session_provider_remove_blocks_preflight_and_generation` covers LLM removal propagating to preflight and stale generation failure.
- `tests/test_followup_provider_runtime.py::test_same_session_tts_remove_updates_preflight_registry` covers TTS removal propagating to preflight.
- `tests/test_followup_provider_runtime.py::test_provider_save_persists_credential_env_name_not_secret` covers credential environment-name persistence without secret-value persistence.
