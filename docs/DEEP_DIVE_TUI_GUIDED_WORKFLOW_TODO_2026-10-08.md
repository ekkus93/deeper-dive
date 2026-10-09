# Deeper Dive TUI Guided Workflow TODO

**Created:** 2026-10-08
**Status:** In progress
**Authority:** docs/DEEP_DIVE_TUI_GUIDED_WORKFLOW_SPEC_2026-10-08.md
**Predecessor:** docs/DEEP_DIVE_PRODUCTION_GENERATION_SECOND_POST_REVIEW_REMEDIATION_TODO_2026-10-02.md

This is the authoritative checklist for the guided Textual workflow remediation. A checkbox is complete only when the behavior is wired through production services, has focused regression evidence, is on master, and has the required exact-head qualification. Do not check items merely because a screen or helper exists.

## Execution rules

- [ ] Reload this TODO and companion spec from current master at the start of every Ralph run and after every successful direct-master write or merge.
- [ ] Inspect current master, relevant Ralph branches/open PRs, and CI before implementing duplicate work.
- [ ] Work directly on master when Ralph Bridge policy permits; do not create a branch/PR per screen or checkbox.
- [ ] Prefer coherent vertical slices that share wizard state, production services, tests, or navigation.
- [ ] Keep the current production-generation TODOs unchanged as historical evidence.
- [ ] Route guided workflows through existing production services instead of adding wizard-only business logic.
- [ ] Keep deterministic fake providers behind normal durable provider config/factory/runtime boundaries.
- [ ] Preserve CLI and existing persisted project compatibility.
- [ ] Keep all new provider/runtime/status text behind canonical sanitization.
- [ ] Treat the approved TUI mockup as UX intent and this spec/TODO as the normative implementation contract.

## GW-100 — Baseline and guided-workflow architecture

- [x] Inventory current DeeperDiveApp navigation, screen ownership, controller/service boundaries, and first-run readiness behavior.
- [x] Record the current flat global/project navigation and implementation-heavy Episode Setup behavior with focused baseline tests before replacing UX.
- [x] Define a typed shared WizardState/WizardContext boundary that references production IDs/state instead of copying business entities.
- [x] Define first-run completion as derived readiness, not a one-time boolean.
- [x] Define New Deep Dive step completion from durable project/source/host/episode/plan/preflight state.
- [x] Define the minimal permitted UI-only draft state and versioning/recovery policy.
- [x] Add shared navigation/transition helpers used by both wizards.
- [x] Ensure ProductionComposition remains the production application context used by guided flows.

## GW-110 — Shared Textual wizard shell

- [x] Implement one reusable wizard shell for first-run and New Deep Dive.
- [x] Render wizard title and Step N of M.
- [x] Render completed/current/upcoming progress state with text plus symbols, not color alone.
- [x] Implement consistent Back, Continue, Save and Exit, Help, and status areas.
- [x] Implement deterministic Tab and Shift+Tab focus order.
- [x] Implement arrow-key/radio/select navigation where appropriate.
- [x] Implement Enter activation and Space toggle semantics where appropriate.
- [x] Implement Escape modal cancellation and safe Save/Exit behavior.
- [x] Keep primary actions visible while main content scrolls.
- [x] Add busy-state protection against unsafe duplicate actions.
- [x] Add pilot tests for keyboard-only navigation and focus order.
- [x] Add recommended-size and 80x24 compact-layout tests.
- [x] Add explicit terminal-too-small behavior below the supported minimum.

## GW-120 — First-run Welcome and System Check

- [x] Route a clean/unready installation into the First-run Setup Wizard.
- [x] Skip automatic setup entry for a returning user whose derived readiness is valid.
- [x] Welcome screen offers Quick Setup and Advanced Setup with concise explanations.
- [x] Welcome screen allows Skip Setup without falsely marking setup complete.
- [x] System Check reports Python/runtime sanity.
- [x] System Check reports FFmpeg readiness.
- [x] System Check reports KittenTTS availability as required/optional according to selected speech path.
- [x] System Check detects configured/reachable Ollama where supported.
- [x] System Check detects configured/reachable llama-server where supported.
- [x] Missing optional components do not block unrelated valid provider choices.
- [x] Details/remediation actions expose useful diagnostics without raw tracebacks.
- [x] Add deterministic first-run routing and system-check tests.

## GW-130 — First-run AI provider configuration

- [x] Present user-oriented AI provider choices: Ollama, llama-server, OpenAI, OpenAI-compatible, Manual.
- [x] Mark detected local providers clearly.
- [x] Quick Setup may recommend a healthy local provider but never overrides an explicit choice.
- [x] Configure Provider screen shows only fields relevant to the selected adapter.
- [x] Ollama flow discovers models and supports a model picker.
- [x] llama-server flow validates endpoint/model behavior through existing provider boundaries.
- [x] OpenAI flow persists credential references rather than raw credential values.
- [x] OpenAI-compatible flow supports base URL, credential reference, model, and network-scope behavior through existing config.
- [x] Test Connection uses the same provider factory/runtime used by production.
- [x] Failed provider save/build preserves prior durable config and live runtime.
- [x] Provider-originated health/discovery/errors are canonically sanitized.
- [x] Add positive and negative transactional provider tests through the wizard.

## GW-140 — First-run model test and role assignment

- [x] Add a synthetic minimal language-model inference test through the configured production provider.
- [x] Show running, success, elapsed-time, and sanitized failure states.
- [x] Show a short sanitized response preview on success.
- [x] Quick Setup proposes recommended compatible assignments for episode planning, host generation/conversation, directing, and verification.
- [x] Persist recommended role assignments through the existing durable role-assignment boundary.
- [x] Advanced Setup can edit roles without leaving the wizard workflow.
- [x] Do not report model readiness from configuration presence alone.
- [x] Add model-test failure/retry coverage.
- [x] Add restart coverage proving role assignments reload.

## GW-150 — First-run speech, voices, defaults, and Ready

- [x] Present speech choices: KittenTTS local, OpenAI TTS, ElevenLabs, No speech yet, Advanced/Custom.
- [x] Explain local/cloud and credential implications before save.
- [x] Configure selected speech through normal provider config/factory/runtime boundaries.
- [x] Discover/select friendly voice names without requiring raw voice IDs.
- [x] Preview the focused voice through the production TTS boundary where practical.
- [x] Support Host 1 and Host 2 default voice choices.
- [x] Collect default episode-duration preset.
- [x] Collect default research level.
- [x] Preserve explicit local-only/network-scope policy.
- [x] No speech yet may complete setup but must not masquerade as audio-ready.
- [x] Ready screen recomputes provider, role, TTS, FFmpeg, and default readiness on mount.
- [x] Ready screen exposes Create My First Deep Dive and Go to Dashboard.
- [x] Restart after successful setup lands on Home.
- [x] Invalidating a previously ready provider surfaces Setup needs attention.
- [x] Add deterministic fake-LLM/fake-TTS end-to-end first-run acceptance.

## GW-160 — Simplified Home and navigation

- [x] Replace the default flat subsystem-first navigation with user-goal-first navigation.
- [x] Primary navigation exposes Home, New Deep Dive, Projects, and Library.
- [x] Advanced section exposes Sources, Research, Hosts, Providers, Settings, and Help.
- [x] Preserve access to existing advanced screens.
- [x] Home provides a dominant New Deep Dive action.
- [x] Home shows derived setup/readiness status.
- [x] Home shows recent projects from durable summaries.
- [x] Home shows recent episodes where durable data supports it.
- [x] Home offers Resume Deep Dive when an incomplete wizard can be reconstructed.
- [x] Existing project open/rename/delete operations remain available.
- [x] Add keyboard-only navigation regression for Home/Primary/Advanced sections.

## GW-170 — New Deep Dive: Project and Sources

- [x] New Deep Dive opens the shared seven-step guided workflow.
- [x] Project Setup collects project name.
- [x] Project Setup collects topic/main curiosity prompt.
- [x] Project Setup collects user-facing audience preset.
- [x] Project creation uses DeeperDiveService and normal workspace persistence.
- [x] Save and Exit after project creation leaves a discoverable resumable project.
- [x] Sources step exposes Files, Paste Text, URL, and Folder where supported.
- [x] Source imports use existing source/corpus application services.
- [x] Source rows show friendly identity, inclusion, indexing/readiness, and concise failure state.
- [x] Source add/remove/include/exclude actions preserve existing provenance and security behavior.
- [x] Continue semantics reflect actual source/index readiness.
- [x] No acceptance test directly seeds source repository rows for the normal path.
- [x] Add import/index failure, retry, restart, and resume regressions.

## GW-180 — New Deep Dive: Research and Hosts

- [x] Research step offers Use only my sources.
- [x] Research step offers Fill important gaps as the recommended middle choice.
- [x] Research step offers Research extensively.
- [x] Choices map to existing research policy/controller behavior.
- [x] External-network implications are disclosed before networked research.
- [x] Advanced research options preserve current expert controls.
- [x] Hosts step renders friendly host rows/cards with behavior summary and voice.
- [x] Hosts step supports one or more selected hosts.
- [x] Host ordering is explicit and deterministic.
- [x] Voice preview is available from the host selection workflow where speech is configured.
- [x] Custom host creation/editing uses existing host services.
- [x] Episode host selection never requires comma-separated raw host IDs in the normal wizard.
- [x] Add research-policy mapping and host-order persistence tests.

## GW-190 — New Deep Dive: Episode Settings and Review/Plan

- [x] Episode Settings collects episode title.
- [x] Episode Settings collects main question/focus.
- [x] Episode Settings offers duration presets plus Custom.
- [x] Episode Settings collects audience.
- [x] Technical depth, must-cover topics, avoid topics, and similar expert fields are available under Advanced options.
- [x] Persist episode state through EpisodeConfigurationService.
- [x] Validate episode fields before forward navigation.
- [x] Review & Plan builds through EpisodePlannerService.
- [x] Render ordered segment title, duration, and purpose/focus.
- [x] Provide Edit Plan and Regenerate actions through supported production planner operations.
- [x] Respect the existing post-start plan immutability/revision policy.
- [x] Continue requires the shared valid-plan policy to pass.
- [x] Provider/planner errors are sanitized and actionable.
- [x] Add positive plan, negative planner output, invalid persisted plan, and post-start mutation regressions.

## GW-200 — Ready to Generate and actionable preflight

- [x] Ready to Generate invokes the same shared preflight used by production CLI/TUI generation.
- [x] Render readiness for sources.
- [x] Render readiness for research policy.
- [x] Render readiness for hosts.
- [x] Render valid-plan status.
- [x] Render model-role/provider/model health.
- [x] Render speech/voice readiness.
- [x] Render FFmpeg readiness.
- [x] Render local-only/network-scope compatibility.
- [x] Every blocker has an actionable route back to the relevant wizard step or advanced screen where practical.
- [x] Continue/Generate remains disabled while blocking preflight issues exist.
- [x] Generate starts through GenerationStartService/shared ProductionComposition.
- [x] No wizard-specific run-creation or orchestration path exists.
- [x] Add CLI/TUI preflight-parity regression after wizard integration.

## GW-210 — Generation Progress and failure recovery

- [x] Create a guided Generation Progress screen backed by durable run state.
- [x] Show current stage and completed stages.
- [x] Preserve current informational-stage semantics; do not claim nonexistent artifacts.
- [x] Show honest progress only where production can compute it.
- [x] Show elapsed time and sanitized latest status.
- [x] Support pause where durable pipeline state permits it.
- [x] Support resume where durable pipeline state permits it.
- [x] Support cancel with confirmation.
- [x] Reload progress correctly after screen recreation/restart.
- [x] Durable failure view shows stage, stable failure code when present, and sanitized message.
- [x] Provide Retry/Resume only for supported failure states.
- [x] Provide route back to configuration for setup/preflight repair.
- [x] Add duplicate-action, pause/resume/cancel, resume-after-failure, and restart regressions.

## GW-220 — Episode Ready and Library handoff

- [x] Successful generation transitions to Episode Ready.
- [x] Episode Ready shows title, duration when available, and selected hosts.
- [x] Episode Ready resolves playback for the selected episode/run only.
- [x] Open in Review routes to existing transcript review.
- [x] Export Episode uses existing export services.
- [x] View in Library selects the generated episode.
- [x] Simplified Library prioritizes episodes with project/time/status context.
- [x] Library supports Play, Open, and Export.
- [x] Preserve multi-episode isolation for playback/review/export.
- [x] Add two-episode guided-workflow isolation acceptance.

## GW-230 — Quick Deep Dive integration

- [x] Expose Quick Deep Dive as a recommended shortcut from Home and/or New Deep Dive.
- [x] Quick mode still creates/uses normal durable project state.
- [x] Quick mode requires or collects source material through normal source services.
- [x] Apply documented recommended research, host, and episode defaults.
- [x] Build plan through EpisodePlannerService.
- [x] Run shared preflight.
- [x] Start through GenerationStartService and PipelineOrchestrator.
- [x] Produce normal durable turns, TTS, timeline/audio, review state, and exports.
- [x] Keep QuickDeepDiveService as a convenience boundary rather than a second engine.
- [x] Add Quick-versus-guided production-equivalence acceptance for shared artifacts/state.

## GW-240 — Save/resume and durable wizard-state recovery

- [x] Define and implement the minimal versioned wizard draft record only if production state cannot represent a needed UI draft.
- [x] Do not duplicate provider config, source data, host definitions, episode config, plan, run, or export data into wizard draft state.
- [x] Save and Exit preserves partial first-run progress.
- [x] Save and Exit preserves partial New Deep Dive progress.
- [x] Resume computes the earliest incomplete prerequisite from production state.
- [x] Resume preserves a later valid location when prerequisites remain valid.
- [x] Invalid/corrupt/old draft state fails safe to the earliest derivable valid step.
- [x] Previously completed steps move back to Needs attention when their production prerequisite becomes invalid.
- [x] Add restart tests at every major wizard boundary.

## GW-250 — Validation, security, accessibility, and compact-terminal UX

- [x] Preserve typed input after validation failure.
- [x] Use inline validation for local field errors.
- [x] Use screen-level blockers for workflow errors.
- [ ] Put technical detail behind an explicit details/help action.
- [ ] Never show raw tracebacks in the normal wizard path.
- [ ] Apply canonical recursive sanitization to all provider/runtime/user-visible errors.
- [ ] Preserve credential-reference and non-persistence rules.
- [ ] Disclose cloud/network behavior before networked actions.
- [x] Use synthetic minimal prompts for setup tests rather than private user source material.
- [x] Visible focus meets keyboard-only requirements.
- [x] Completion/current/error state is not color-only.
- [x] Primary action placement and Back semantics remain consistent.
- [ ] No normal screen requires a raw internal ID as the primary user input.
- [ ] Destructive actions require confirmation.
- [x] 100x30 recommended layout passes.
- [x] 80x24 compact layout passes without primary horizontal scrolling.
- [x] Below-minimum viewport shows a clear resize message while preserving state.
- [ ] Add accessibility/focus/layout regression matrix.

## GW-260 — Shared acceptance fixture and end-to-end guided workflow

- [x] Extend/reuse the deterministic production acceptance fixture rather than create one-off repository seeding.
- [x] First-run acceptance configures a deterministic LLM through normal provider boundaries.
- [x] First-run acceptance configures deterministic TTS/voices through normal provider boundaries.
- [x] First-run acceptance persists recommended roles and reaches derived Ready.
- [x] New Deep Dive acceptance creates project through DeeperDiveService.
- [x] Acceptance adds/indexes source through production source APIs.
- [x] Acceptance selects research policy through production mapping.
- [x] Acceptance selects hosts through host services.
- [x] Acceptance persists episode through EpisodeConfigurationService.
- [x] Acceptance builds a plan through EpisodePlannerService.
- [x] Acceptance passes shared preflight.
- [x] Acceptance starts through GenerationStartService.
- [x] Acceptance generates multiple durable turns through PipelineOrchestrator.
- [x] Acceptance synthesizes TTS/timeline/audio through production services.
- [x] Acceptance reaches Episode Ready and exports through shared export services.
- [x] Acceptance reopens the episode from Library.
- [x] Prove no direct normal-path seeding of plan, run, turn, TTS, timeline, or export repository rows.

## GW-270 — Compatibility and regression protection

- [x] Existing provider configuration still loads.
- [x] Existing projects and sources still open.
- [ ] Existing hosts still open.
- [ ] Existing episode configs/plans/runs/turns/provider identities still open.
- [x] Existing timelines/audio/exports still open.
- [ ] Existing Transcript Review and targeted repair remain usable.
- [x] Existing advanced Sources/Research/Hosts/Providers/Settings screens remain usable.
- [ ] Existing CLI acceptance remains green.
- [ ] Existing production-generation remediation suites remain green.
- [ ] No migration is introduced unless required by a documented compatibility case.
- [ ] If a migration is required, prove idempotence, failure safety, and rollback/read compatibility.

## GW-280 — Documentation

- [x] Document first-run setup.
- [x] Document Quick versus Advanced setup.
- [x] Document local versus cloud provider choices.
- [x] Document New Deep Dive guided workflow.
- [x] Document Quick Deep Dive shortcut semantics.
- [x] Document advanced navigation.
- [x] Document keyboard controls.
- [x] Document terminal-size requirements.
- [x] Document Save/Exit/resume behavior.
- [x] Document common setup/preflight blockers and recovery.
- [x] Document that wizard flows reuse the same production services as CLI and advanced TUI.
- [ ] Update screenshots/ASCII examples only after final Textual layout stabilizes.

## GW-290 — Qualification and closeout

- [ ] Focused first-run wizard tests pass.
- [ ] Focused New Deep Dive wizard tests pass.
- [ ] Keyboard/focus/accessibility matrix passes.
- [ ] Compact-terminal matrix passes.
- [ ] Save/resume/restart matrix passes.
- [ ] Security/redaction matrix passes.
- [ ] Provider routing/preflight parity passes.
- [ ] Pause/resume/cancel/resume-after-failure matrix passes.
- [ ] Multi-episode isolation passes.
- [ ] Quick-versus-guided production-equivalence acceptance passes.
- [ ] Persisted compatibility matrix passes.
- [ ] uv lock --check passes.
- [ ] Ruff format check passes.
- [ ] Ruff lint passes.
- [ ] mypy passes.
- [ ] Full pytest passes.
- [ ] Package build passes.
- [ ] CLI/import smoke passes.
- [ ] Installed-wheel fresh-machine guided-workflow acceptance passes.
- [ ] Mandatory real KittenTTS qualification passes under the existing external-network policy.
- [ ] Record implementation commit SHA(s).
- [ ] Record named focused tests by cluster.
- [ ] Record exact final master SHA.
- [ ] Record exact-head CI run ID and conclusion.
- [ ] Reload this TODO and companion spec from the qualified final master head.
- [ ] Confirm zero unchecked tasks before declaring the guided-workflow remediation complete.

## Qualification evidence

Populate only as work is completed. Do not pre-check or use placeholders as completion evidence.

- Implementation SHAs:
  - 3169e296eb5d91276d4445a0902fa1a7d0b70fb6, de02c3ca5ca89b2c8ab1579998f23bb7c2481ddf, 211fcf57fe77180cc25cfa1d5c247342fa076a4a, 72b886638a22963366c8fff7211daeaa37a3bc38 — reused `completed_episode_acceptance` production fixture in `tests/test_guided_persisted_compatibility.py::test_guided_tui_reopens_completed_legacy_artifacts_and_advanced_routes`; fresh-service persisted provider/source/project, timeline/audio/export, selected episode review/export and advanced-screen compatibility; exact-head master CI 37907649199 passed at 324f08c72612f8641145b8d909a4bb00bd5150c8 (quality and fresh-machine).
  - c1b48250404349b2f6dc461cdfec345cda43f039 — GW-250 focus, inline validation, screen blockers, sanitized runtime failure and terminal layout tests; exact-head CI 37904031350 passed (quality and fresh-machine).

  - a5dfdd6cfdc8f00bd151bd612c5556c74e329adf, 58a662116a4a32f9a70ee781e47f7191ef5852b3 — Guided Episode Ready reuses Library playback; two-episode action-selection regression; exact-head CI 37869998015 passed.
  - 7f750cb35d7522022882bbdea4f2c8f4b0e96999 — Home Quick Deep Dive now invokes shared preflight and GenerationStartService via the normal Generate action, then uses the production monitor/pipeline; existing Quick pipeline acceptance covers persisted turns, TTS, timeline, audio, review and export; exact-head CI 37870163029 passed.
  - 8c5dc5339cddb94ccf28befcf629eefc984c4b38 — two-episode transcript review and real export isolation; exact-head CI 37870457593 passed.
  - 206cc0d47a641b0084bc32662a27c7ebaffb5ae7 — one guided wizard and one Quick episode through the shared planning/start/pipeline/export production services with separately durable turns, audio, timelines, and exported identities; exact-head CI 37870945858 passed.
  - 1315cef6a5ff2f065633aa3da8de5ccea7280516 — guided production completion handoff to Episode Ready, UI export, and reopen selected episode from Library; exact-head CI 37871316770 passed.
  - d03450b8498fa9615c778bc37d8f082880bf8a68 — all seven New Deep Dive step bookmarks recovered with fresh production composition; existing eight-step first-run checkpoint matrix also qualified; exact-head CI 37871439509 passed.
  - e9f7ef916d720ec2b42c2e8fdfde8fa61e0774b6 — prevent first-run provider-config compose crash on resume; exact-head CI 37868452882 passed.
  - f5e065672ea2ff37c2803e552b73297a7a8e024b, 77ff90903ce1ab13c7fc03897356c30a460381e2 — invalidated provider returns prior setup steps to Needs attention; exact-head CI 37868870026 passed.
  - 004198882412bccb0789a89b91e7b2514539194a, 1666f072a9434917d0fc077113401bb496319b98, d9010ee5f471563680c46b7200c4f40b22f0364a — shared source readiness for wizard and generation preflight, status-aware rows, negative/positive indexing gates; exact-head CI 37859564426 passed.

  - 179adb1ee0e7616fa0da5afd7c8eea93e1bcc679, 8873119ca22d5b4f7100f265874e558b69f6f4c5 — guided host order/edit/restart regression; exact-head CI 37857593854 passed.
  - c9e78253cd80c3a141138ef2f7b10f24567aaac4, f4c662b4610a2dc4631a91e27f822d5126918455 — single-host, voice-preview, and custom-host regression; exact-head CI 37858305157 passed.
  - e854f3ca29c3c9214591b2de2c6c41196ce1bdfd, c32084b77f881631a9d503c7b1a148cc1fa8ca31 — advanced Research navigation and project lifecycle regression; exact-head CI 37856266276 passed.
  - 817ecc66fe05a9f7b0584a8fcc1c9c80446be701, 32df225207ae158cabfbf8c90392899d869b81d6 — source-gated Home Quick entry through existing Episode setup, planner and preflight; exact-head CI 37856994233 passed.
  - ac9d7801911a6f646ca7abd994d3d38c921bdf83 — recovery derives earliest valid wizard prerequisite from production.
  - 5a7226766fcbe57db5310496af27ec6796a82a3c — Home keyboard and source failure/retry/restart acceptance.
  - bf61544c27435e76bdf7876a6e16b1fb46927254 — guided user guide and README entry.
  - 066a96b3b5f509b9bd1953857e6a74c42857632f — canonical monitor diagnostics sanitization and literal display; exact-head CI 37844246239 passed.
  - 22ecdfcb795ce9e44998c6870a57818d94494901 — guided monitor/ready-screen regression repair; exact-head CI 37835540919 passed.
  - 0ce02ffcf596268b4060ff1d8902d0cd4a1b3af7 — failed-run guided monitor repair route; exact-head CI 37836046970 passed.
  - 160bbdc607dfb68163731210e956207a3c186aeb — selected episode Library playback; exact-head CI 37836853268 passed.
  - 8fa7bf02998525137d222ebd55405a3044cce58e, 19189a36cff518d8aeef53b2dd37f64e949fac81, ced678e2b20da528153d082da18011d4a620ef19, 0b43631f9ab79a231aaf522b0f51b0e292fecde6 — supported failed-stage retry gating and durable pause/resume/cancel/duplicate-action regressions; exact-head CI 37864545949 passed.
- Focused first-run tests:
  - tests/test_guided_first_run.py::test_first_run_fake_llm_model_roles_and_deferred_speech_survive_restart
  - tests/test_guided_first_run.py::test_first_run_fake_tts_voice_preview_and_ready_restart
  - tests/test_guided_draft.py::test_ready_first_run_restores_each_wizard_checkpoint
- Focused New Deep Dive tests:
  - tests/test_guided_episode_wizard.py::test_guided_and_quick_runs_produce_isolated_durable_artifacts
  - tests/test_guided_source_wizard.py::test_source_readiness_uses_status_and_durable_chunks
  - tests/test_guided_source_wizard.py::test_guided_source_continue_reflects_index_readiness
  - tests/test_guided_episode_wizard.py::test_guided_hosts_reorder_edit_and_restart_from_production_state
  - tests/test_guided_app.py::test_goal_first_home_preserves_project_open_rename_delete
  - tests/test_guided_source_wizard.py::test_guided_research_choices_persist_through_production_controller
  - tests/test_guided_source_wizard.py::test_guided_advanced_research_preserves_project_context
  - tests/test_guided_app.py::test_goal_first_quick_requires_sources_then_uses_production_plan
  - tests/test_guided_source_wizard.py::test_guided_source_import_failure_retains_form_then_resumes_after_restart
  - tests/test_guided_episode_wizard.py::test_guided_episode_plan_preflight_and_generation_start
  - tests/test_guided_episode_wizard.py::test_guided_generate_opens_production_monitor_and_confirmed_cancel
  - tests/test_guided_episode_wizard.py::test_guided_completed_run_shows_episode_ready_and_routes_to_library
  - tests/test_guided_generation_monitor.py::test_guided_monitor_failed_sources_run_routes_to_sources
  - tests/test_episode_library_playback.py::test_episode_library_play_uses_selected_episode_audio_only
- Keyboard/focus/layout tests:
  - tests/test_guided_app.py::test_goal_first_home_keyboard_primary_and_advanced_actions
- Recovery/resume tests:
  - tests/test_guided_episode_wizard.py::test_new_deep_dive_restarts_at_each_guided_wizard_boundary
  - tests/test_guided_first_run.py::test_first_run_save_exit_resumes_durable_partial_provider_setup
  - tests/test_guided_draft.py::test_ready_setup_invalidated_provider_marks_prerequisite_needs_attention
  - tests/test_guided_draft.py::test_draft_recovers_to_earliest_missing_production_prerequisite
  - tests/test_guided_draft.py::test_draft_preserves_valid_later_location_when_prerequisites_are_ready
  - tests/test_guided_app.py::test_saved_new_deep_dive_resumes_from_durable_project_after_restart
  - tests/test_guided_generation_monitor.py::test_guided_monitor_reloads_checkpoint_after_restart
  - tests/test_guided_generation_monitor.py::test_guided_monitor_retries_only_supported_failed_stages
  - tests/test_guided_generation_monitor.py::test_guided_monitor_pause_resume_cancel_controls_are_durable
- Security/redaction tests:
  - tests/test_generation_monitor.py::test_monitor_diagnostics_and_status_redact_persisted_credential_canaries
- Quick Deep Dive parity tests:
  - tests/test_guided_app.py::test_guided_home_quick_starts_shared_generation_when_ready
  - tests/test_quick_deep_dive.py::test_quick_deep_dive_preflight_executes_pipeline_and_exports_artifacts
  - tests/test_guided_episode_wizard.py::test_guided_and_quick_runs_produce_isolated_durable_artifacts
- Multi-episode isolation tests:
  - tests/test_episode_library_playback.py::test_episode_library_play_uses_selected_episode_audio_only
  - tests/test_episode_library_playback.py::test_guided_ready_actions_keep_two_episodes_isolated
  - tests/test_episode_library_export.py::test_review_and_real_exports_stay_isolated_across_two_episodes
  - tests/test_guided_episode_wizard.py::test_guided_and_quick_runs_produce_isolated_durable_artifacts
- Compatibility tests:
- Final master SHA:
- Final exact-head CI run:
- Quality job:
  - 37844246239 quality: passed (lock check, Ruff, mypy, pytest, package, CLI smoke; exact-head 066a96b3b5f509b9bd1953857e6a74c42857632f).
- Fresh-machine installed-wheel result:
  - 37844246239 fresh-machine: passed (installed wheel/entry points/corpus workflow).
- Mandatory KittenTTS result:
  - 37844246239 fresh-machine: real KittenTTS Micro CPU smoke passed.
- Compatibility/migration decision:
