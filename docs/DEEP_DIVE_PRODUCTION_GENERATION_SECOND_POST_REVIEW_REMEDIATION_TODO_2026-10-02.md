# Deeper Dive Production Generation: Second Post-Review Remediation TODO

**Created:** 2026-10-02
**Status:** Complete
**Authority:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_SECOND_POST_REVIEW_REMEDIATION_SPEC_2026-10-02.md`
**Predecessor:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_POST_REVIEW_REMEDIATION_TODO_2026-09-27.md`

Checkboxes describe work to be done. Check an implementation item only after production wiring and focused regression evidence exist. Check qualification items only after the exact implementation head is observed in CI. Keep the previous completed checklist unchanged as historical evidence.

## Execution rules

- [x] Reload this TODO and companion spec from current `master` before implementation and after each merge or direct-master write.
- [x] Inspect current code, existing focused tests, and CI before duplicating work.
- [x] Record any discovered change in scope or policy in this spec and TODO before claiming completion.
- [x] Preserve readable persisted data and route CLI/TUI/background behavior through shared production services.

## SPR-100 — Plan revision and conversation lineage

- [x] Choose and document the behavior for editing a plan after generation has started: explicit rejection or new generation lineage.
- [x] Bind durable conversation state, turns, and run resume to the selected plan revision.
- [x] Apply the policy to whole-plan regeneration, segment regeneration, and segment editing.
- [x] Handle edits during pending, running, paused, failed, and completed runs deterministically.
- [x] Prevent old turns, claims, TTS, timeline, or audio from satisfying a revised plan while preserving old run/export history.
- [x] Preserve shared TTS cache files still referenced by other turns.
- [x] Add focused partial-run, completed-run, changed-segment-count, and old-run-resume regressions through public services.

## SPR-110 — Provider-originated TUI text

- [x] Sanitize successful LLM and TTS health messages before status display.
- [x] Sanitize discovered model identifiers and voice names/IDs before details display.
- [x] Sanitize provider-originated exceptions on those actions and check shared CLI/preflight surfaces.
- [x] Add synthetic-secret cases for authorization, Bearer, tokens, client secret, cookie, and credential URLs.
- [x] Add non-secret model/voice/health text preservation cases.

## SPR-120 — Returned TTS format parity

- [x] Compare provider-reported format with the requested response format before file, row, or checkpoint persistence.
- [x] Validate reported WAV content through the existing decoder before durable success where practical.
- [x] Ensure an unexpected MP3/raw response under a WAV request leaves no successful artifact or final audio.
- [x] Preserve existing provider, voice, model, cache, legacy artifact, and Kitten WAV behavior.
- [x] Add CLI/TUI preflight and synthesis regressions for configured MP3 and unexpected returned formats.

## SPR-130 — Role preflight/production parity

- [x] Make conversation completion checks and host/directing provider resolution follow the same role policy as preflight.
- [x] Confirm verification role checks match the work the verification stage executes.
- [x] Cover no plan, partial conversation, completed conversation, revised plan, and new run after completion.
- [x] Cover missing, unknown, unavailable, and unhealthy provider/model assignments where the role will execute.
- [x] Confirm CLI/TUI blockers agree and completed conversations do not duplicate turns.

## SPR-140 — Positive duration normalization

- [x] Reject or resolve infeasible segment counts before duration scaling.
- [x] Distribute rounding without producing a zero or negative segment duration.
- [x] Revalidate total and per-segment durations before persisting build, edit, or regeneration output.
- [x] Add scale-up, scale-down, rounding, many-tiny-segment, and infeasible-target regressions.

## SPR-150 — Strict persisted plan validity

- [x] Reject scalar, mapping, null, and mixed-type `evidence_ids` and `lead_host_ids` values.
- [x] Keep valid empty lists, project-scoped evidence, and episode-host membership behavior.
- [x] Define and enforce row/JSON consistency for title and duration used in generation.
- [x] Add invalid-shape, corrupt-JSON, cross-project, invalid-host, and auto-planning/blocker regressions.

## SPR-160 — Typing and style cleanup

- [x] Give the generation-start dependency a typed protocol or explicit application type.
- [x] Remove obsolete `type: ignore[attr-defined]` from the touched boundary.
- [x] Remove avoidable broad formatter and import-order suppressions in touched files; explain any remaining narrow exceptions.
- [x] Run Ruff format, Ruff lint, and mypy without unrelated style churn.

## SPR-170 — Exact-head qualification evidence

- [x] Document the historical 2026-09-27 final SHA/CI evidence gap accurately without rewriting its completed checklist.
- [x] Record implementation commit SHA(s), focused test names, and any necessary compatibility decision.
- [x] Observe exact-head quality and fresh-machine CI on the final implementation commit.
- [x] Record CI run ID, conclusion, quality result, installed-wheel result, and mandatory Kitten result.
- [x] Reload this TODO/spec from the qualified `master` head and confirm no unchecked items before declaring completion.

## SPR-180 — Pipeline stage semantics

- [x] Decide and document whether `sources`, `research`, and `export` produce artifacts during generation or are informational boundaries.
- [x] Implement real operations and artifact checks, or update progress/status language to match informational behavior.
- [x] Keep explicit export and multi-episode export isolation behavior intact.
- [x] Add a production-path status regression for the chosen semantics.

## Qualification matrix

- [x] Plan revision/resume acceptance, including partial and completed runs.
- [x] Provider UI redaction matrix with non-secret controls.
- [x] TTS requested/returned format and no-success-on-mismatch matrix.
- [x] Preflight versus production role matrix across CLI and TUI.
- [x] Duration and persisted-plan-shape matrices.
- [x] Pipeline status semantics and export isolation acceptance.
- [x] Persisted compatibility checks for projects, plans, runs, turns, timelines, TTS, and exports.
- [x] `uv lock --check`, Ruff format, Ruff lint, mypy, full pytest, package build, and CLI/import smoke.
- [x] Installed-wheel fresh-machine and selected real-Kitten qualification on the exact implementation head.

## Closeout evidence

Fill this section only after implementation and qualification. Record exact values, not placeholders marked as completed.

- Implementation SHA: `e5b62c8f98ec7c2eecd05daf6327fd681c8ae0d0` (direct `master` commit).
- Named focused tests: see the evidence mapping below.
- Qualified implementation `master` SHA: `e5b62c8f98ec7c2eecd05daf6327fd681c8ae0d0`. The subsequent documentation-only closeout is independently CI-qualified before completion is reported; its SHA/run are reported in the completion response to avoid a self-referential commit hash.
- Implementation exact-head CI: `37068864649`, **success**, https://github.com/ekkus93/deeper-dive/actions/runs/37068864649.
- Quality job `111043260808`: **success** (lock, format, lint, mypy, full pytest, build, CLI/import smoke).
- Fresh-machine job `111043260545`: **success** (clean wheel install, installed CLI/TUI launch, corpus/episode workflow).
- Mandatory real KittenTTS Micro CPU smoke: **success**, step 9 of fresh-machine job `111043260545`.
- Compatibility: legacy row-authoritative plan fields and missing ID lists remain readable; malformed explicit ID lists fail. Legacy TTS statuses/cache artifacts remain readable. Post-start plan mutation is explicitly rejected; create a new episode for changed content. No dependent history/cache files are removed. Informational sources/research/export boundaries are disclosed; explicit exports remain supported. No finding is intentionally deferred.

### Evidence mapping

| Finding | Production regression evidence |
| --- | --- |
| SPR-100 | `test_started_plan_is_immutable_and_preserves_history` (20 state/action combinations); `test_old_run_cannot_resume_revised_plan_content`; `test_rejected_revision_preserves_completed_export_and_shared_cache`; existing partial/resume conversation and shared-cache matrices. |
| SPR-110 | `test_provider_originated_health_discovery_and_errors_are_redacted`; `test_provider_cli_output_uses_canonical_recursive_redaction`; existing provider UI/CLI/preflight redaction and non-secret controls. |
| SPR-120 | `test_returned_format_mismatch_leaves_no_success` (MP3, raw PCM, disguised WAV, corrupt WAV); `test_production_tts_blocks_configured_openai_compatible_mp3`; WAV/cache/legacy/Kitten tests; `test_preflight_parity.py` CLI/TUI format blockers. |
| SPR-130 | `test_completed_conversation_omits_host_resolution_and_preserves_turns` (missing, invalid, valid host); existing `test_generation_start.py`, `test_preflight_model_roles.py`, and generation-start cross-surface matrices. |
| SPR-140 | `test_positive_duration_apportionment`; `test_infeasible_segment_count_is_rejected_before_persistence`; existing edit/regeneration scaling and persistence tests. |
| SPR-150 | `test_malformed_persisted_id_lists_are_not_empty_lists`; `test_row_json_generation_fields_must_agree`; `test_empty_id_lists_remain_valid`; existing corrupt-JSON, evidence/host scope, auto-planning, and blocker tests. |
| SPR-160 | Generation start uses explicit typed production/application dependencies. Touched broad formatter/import suppressions removed. Exact-head CI format, lint, and mypy steps pass. |
| SPR-170 | Implementation SHA/run/jobs above are observed exact-head evidence. Predecessor placeholder closeout is documented as an unproven historical final-SHA claim; its completed checklist remains unchanged. |
| SPR-180 | `test_production_status_explains_informational_boundaries`; generation monitor and explicit export/multi-episode isolation regression suites. |

The shared deterministic follow-up fixture exercises real provider factory, planning,
conversation, synthesis, composition, and export services. The production paths are
shared by CLI and TUI. Repository orientation and all remote commits/CI observations
used Ralph Bridge. No task branches or pull requests were created.
