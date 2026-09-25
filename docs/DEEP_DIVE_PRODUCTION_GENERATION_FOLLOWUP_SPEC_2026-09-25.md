# Deeper Dive Production Generation Follow-up Remediation Spec

**Created:** 2026-09-25  
**Status:** Draft for implementation  
**Applies to:** follow-up remediation after `docs/DEEP_DIVE_PRODUCTION_GENERATION_CORRECTNESS_TODO_2026-09-24.md`  
**Primary objective:** close production-quality gaps discovered after the production-generation correctness remediation was formally completed on `master`.

---

## 1. Background

The production generation correctness remediation moved Deeper Dive away from hidden deterministic shortcuts and toward explicit provider-backed generation. The merged implementation added configured LLM/TTS provider boundaries, shared CLI/TUI generation-start semantics, duplicate-safe run selection, provider UI coverage, durable artifact identity, explicit export semantics, and fresh-machine qualification.

A follow-up review identified several issues that do not invalidate the completed remediation but should be fixed before treating the production generation path as robust for real same-session TUI use, real provider audio, and evidence-grounded generated transcripts.

This spec is the authority for the follow-up remediation. The corresponding checklist is `docs/DEEP_DIVE_PRODUCTION_GENERATION_FOLLOWUP_TODO_2026-09-25.md`.

---

## 2. Scope

The remediation covers five production clusters:

1. **Provider runtime coherence:** provider configuration changes saved through the TUI must be visible to preflight and generation immediately, without requiring an app restart.
2. **Planning role correctness:** pipeline auto-planning must route through the configured `episode_planning` model role and must fail durably when planning cannot be completed.
3. **Generated evidence/provenance:** provider-backed conversation generation must receive usable source/plan evidence identifiers and exported transcripts must prove non-empty provenance when source evidence exists.
4. **Real audio composition:** episode audio composition must produce valid audio output rather than concatenating provider artifact container bytes.
5. **TTS response-format and artifact identity:** configured TTS response formats must be honored, and per-turn artifact/cache semantics must be clarified and tested.

Out of scope unless required to satisfy the acceptance criteria:

- New live paid-provider tests in normal CI.
- A full audio editor or rich mixing UI.
- Changes to unrelated research, project, source-import, or host-management behavior.
- Reopening the completed `DEEP_DIVE_PRODUCTION_GENERATION_CORRECTNESS_TODO_2026-09-24.md`.

---

## 3. Design requirements

### 3.1 Provider runtime coherence

Current risk: `ProviderController.reload()` rebuilds controller-local registries after provider saves, but `ProductionComposition.providers` can retain the startup `ProviderBuildResult`. Production generation paths use `composition.providers.llm_registry` and `composition.providers.tts_registry`, so freshly saved providers can be visible to the TUI/preflight while generation still sees stale runtime providers.

Required behavior:

- There must be one coherent runtime provider state for preflight, planning, generation, TTS, and provider health checks.
- Saving, editing, or removing a provider through the TUI/controller must update every production path used in the same process.
- Same-session workflow must work: open app, create/save provider config, assign defaults/hosts, run preflight, generate, and export without restarting.
- Preflight and generation must agree on provider existence, model availability, voice availability, network scope, and health status.
- Provider runtime refresh must not persist credentials or expose credential values in status, diagnostics, logs, CLI output, TUI text, metadata, or exported artifacts.

Implementation guidance:

- Prefer a composition-level provider refresh method or provider-runtime accessor that updates/rebuilds `ProviderBuildResult`, `ProviderController`, and `PreflightService` together.
- Avoid copying provider registries into multiple long-lived objects unless the refresh boundary updates all of them atomically.
- Tests should prove that provider changes made through `ProviderController.save_provider()` are consumed by `GenerationStartService`, `_planning_stage`, `_conversation_stage`, `_tts_stage`, and `EpisodeLibraryExportService` without rebuilding the app.

### 3.2 Planning role correctness

Current risk: pipeline `_planning_stage()` selects the first registered LLM provider and first model instead of resolving `ModelRole.EPISODE_PLANNING`. It also catches `ValueError` from plan construction and returns, allowing the stage to be marked complete even when planning failed.

Required behavior:

- Pipeline auto-planning must resolve `episode_planning` through the same user > project > episode precedence used by CLI `episode plan`.
- Pipeline auto-planning must construct the provider through the same production provider registry used elsewhere.
- If no plan exists and `episode_planning` is required, missing/invalid provider/model assignments must fail before output is produced.
- Invalid provider output, invalid structured plan shape, provider exceptions, unavailable models, or storage failures must fail the durable run with sanitized actionable diagnostics; they must not silently create a no-op completed planning stage.
- If a valid plan already exists, planning may be skipped idempotently.
- CLI `episode plan`, CLI `episode generate`, TUI Generate, and background monitor generation must agree on planning provider selection and failure semantics.

Implementation guidance:

- Route `_planning_stage()` through `effective_model_role_assignments_for_episode()` and `ModelRole.EPISODE_PLANNING`.
- Reuse `configured_planning_service()` only after resolving the configured provider/model assignment.
- Remove broad silent `ValueError` swallowing from production planning.
- Add regressions with two LLM providers where the sorted-first provider would produce the wrong marker and the configured `episode_planning` provider must be used.

### 3.3 Generated evidence and provenance

Current risk: the export path preserves seeded/durable provenance, but provider-backed production generation does not appear to supply real available evidence IDs to the director/host-turn provider in the normal generation path. As a result, generated turns can be provider-backed but still citation-empty even when indexed source chunks exist.

Required behavior:

- When included, indexed source material exists, generation must make relevant evidence IDs available to directing and host-turn generation through durable production paths.
- Evidence availability should come from an approved durable source, such as the episode plan's segment evidence IDs, retrieval over indexed source chunks, or another documented production evidence-selection service.
- Host-turn provider prompts must constrain citations to supplied evidence IDs and reject evidence outside the director/evidence scope.
- Persisted turns must retain evidence IDs selected by the provider when valid.
- Exported transcripts must include turn citations, claim/source-passage provenance when available, and resolved source passage metadata/text for cited chunks.
- If no relevant evidence exists, generation may produce an uncited turn only when the preflight/reporting behavior makes the absence explicit or the plan/source state permits it.
- Multi-episode isolation must be preserved: evidence IDs for one episode must not resolve against another project/episode's source corpus.

Implementation guidance:

- Prefer reusing existing retrieval and episode-plan services instead of inventing a surface-specific evidence shortcut.
- Add a reusable acceptance fixture that creates source chunks, a plan with evidence IDs, provider-backed directing/host generation, and exportable provenance.
- Add negative tests for provider-returned evidence IDs outside the supplied scope.

### 3.4 Real audio composition

Current risk: `_composition_stage()` writes final episode audio by byte-concatenating per-turn artifact files into a `.wav`. This passes marker-based fake audio tests but is not valid for real WAV/MP3/containerized provider output.

Required behavior:

- The composition stage must produce a valid episode audio artifact for supported provider artifact formats.
- For WAV input artifacts, the output `.wav` must be readable by Python `wave.open()` and contain a single coherent WAV header and combined PCM frames.
- For MP3 or other supported compressed/container formats, composition must either route through FFmpeg or reject unsupported composition with a sanitized actionable error before claiming completion.
- Composition must preserve episode-specific audio identity and timeline identity.
- Composition must fail if required TTS artifacts are missing, empty, unreadable, unsupported, or mismatched to the expected provider/voice/cache identity.
- Normal CI must remain free of live paid-provider requirements.

Implementation guidance:

- Prefer reusing existing `CanonicalAudio`, audio normalization, or FFmpeg composition abstractions.
- Avoid concatenating bytes from container files.
- Add tests with two minimal valid WAV turn artifacts and assert the final episode WAV can be opened, has expected channels/sample width/sample rate, and has nonzero combined frames.
- Add tests for unsupported artifact format or missing FFmpeg where appropriate.

### 3.5 TTS response-format and artifact identity

Current risk: provider configuration includes TTS `response_format`, but production `TTSTurn` does not carry provider config settings, so `TTSRequest.response_format` defaults to `wav` and can override an OpenAI-compatible provider configured for `mp3`. Also, cache reuse currently returns an artifact for the current turn without necessarily saving a per-turn artifact row, which makes the turn/cache identity contract ambiguous.

Required behavior:

- Provider-configured TTS response formats must be honored during production synthesis.
- OpenAI-compatible TTS configured for `mp3` must receive/request `mp3` during production generation, and artifact paths/extensions must match the actual returned format.
- Providers that only support WAV, such as KittenTTS Micro, must reject unsupported response formats before claiming successful generation.
- The TTS artifact/cache schema contract must be explicitly documented and enforced:
  - either every turn gets a persisted row that references the reused artifact/cache identity, or
  - `tts_artifacts` is documented and tested as a cache table and downstream code must never assume one row per turn.
- Export/composition must continue to locate the correct artifact for every turn after cache reuse.
- Transcript repair invalidation must continue to regenerate changed-turn audio and must not reuse stale cache entries after text/provider/voice/settings changes.

Implementation guidance:

- Add response-format and other synthesis settings to `TTSTurn.settings` from durable provider config or provider defaults.
- Include response format/settings in the cache key.
- Add tests for OpenAI-compatible TTS `mp3`, Kitten WAV-only rejection, cache reuse with duplicate text/voice, and repair invalidation.

---

## 4. Acceptance criteria

The remediation is complete only when all of the following are true:

- Every task and subtask in `docs/DEEP_DIVE_PRODUCTION_GENERATION_FOLLOWUP_TODO_2026-09-25.md` is implemented, tested, reconciled, and checked.
- Same-session TUI provider save/reload/preflight/generate/export passes without restarting the app or rebuilding the composition.
- Pipeline auto-planning uses the configured `episode_planning` provider/model and fails durably on invalid provider output.
- Provider-backed generated transcripts include non-empty citations/source-passage provenance when indexed evidence is available and the configured fake provider selects valid evidence.
- Generated turns reject provider-returned evidence IDs outside the supplied evidence scope.
- Final episode audio composition writes a valid output artifact for supported WAV inputs and has explicit supported/unsupported behavior for compressed/container formats.
- Configured TTS response formats are honored during production generation.
- TTS cache/artifact identity semantics are documented and covered by regression tests.
- Full CI quality gates pass on the exact remediation head.
- Fresh-machine installed-wheel validation passes on the exact remediation head.
- The remediation PR is merged to `master`.
- The TODO is reloaded from merged `master`.
- Merged-master CI passes.

---

## 5. Required evidence

The final TODO reconciliation must record:

- The implementation commits/PRs for each remediation cluster.
- Exact-head CI run IDs and conclusions.
- Merged-master CI run IDs and conclusions.
- Names of the tests covering each bug class.
- Any intentionally deferred behavior with rationale and a follow-up file if required.

Do not mark the remediation complete based only on documentation or green tests that do not exercise the production path described above.
