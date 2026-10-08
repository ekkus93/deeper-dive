# Deeper Dive TUI Guided Workflow TODO

**Created:** 2026-10-08
**Status:** Not started
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

- [ ] Inventory current DeeperDiveApp navigation, screen ownership, controller/service boundaries, and first-run readiness behavior.
- [ ] Record the current flat global/project navigation and implementation-heavy Episode Setup behavior with focused baseline tests before replacing UX.
- [ ] Define a typed shared WizardState/WizardContext boundary that references production IDs/state instead of copying business entities.
- [ ] Define first-run completion as derived readiness, not a one-time boolean.
- [ ] Define New Deep Dive step completion from durable project/source/host/episode/plan/preflight state.
- [ ] Define the minimal permitted UI-only draft state and versioning/recovery policy.
- [ ] Add shared navigation/transition helpers used by both wizards.
- [ ] Ensure ProductionComposition remains the production application context used by guided flows.

## GW-110 — Shared Textual wizard shell

- [ ] Implement one reusable wizard shell for first-run and New Deep Dive.
- [ ] Render wizard title and Step N of M.
- [ ] Render completed/current/upcoming progress state with text plus symbols, not color alone.
- [ ] Implement consistent Back, Continue, Save and Exit, Help, and status areas.
- [ ] Implement deterministic Tab and Shift+Tab focus order.
- [ ] Implement arrow-key/radio/select navigation where appropriate.
- [ ] Implement Enter activation and Space toggle semantics where appropriate.
- [ ] Implement Escape modal cancellation and safe Save/Exit behavior.
- [ ] Keep primary actions visible while main content scrolls.
- [ ] Add busy-state protection against unsafe duplicate actions.
- [ ] Add pilot tests for keyboard-only navigation and focus order.
- [ ] Add recommended-size and 80x24 compact-layout tests.
- [ ] Add explicit terminal-too-small behavior below the supported minimum.

## GW-120 — First-run Welcome and System Check

- [ ] Route a clean/unready installation into the First-run Setup Wizard.
- [ ] Skip automatic setup entry for a returning user whose derived readiness is valid.
- [ ] Welcome screen offers Quick Setup and Advanced Setup with concise explanations.
- [ ] Welcome screen allows Skip Setup without falsely marking setup complete.
- [ ] System Check reports Python/runtime sanity.
- [ ] System Check reports FFmpeg readiness.
- [ ] System Check reports KittenTTS availability as required/optional according to selected speech path.
- [ ] System Check detects configured/reachable Ollama where supported.
- [ ] System Check detects configured/reachable llama-server where supported.
- [ ] Missing optional components do not block unrelated valid provider choices.
- [ ] Details/remediation actions expose useful diagnostics without raw tracebacks.
- [ ] Add deterministic first-run routing and system-check tests.

## GW-130 — First-run AI provider configuration

- [ ] Present user-oriented AI provider choices: Ollama, llama-server, OpenAI, OpenAI-compatible, Manual.
- [ ] Mark detected local providers clearly.
- [ ] Quick Setup may recommend a healthy local provider but never overrides an explicit choice.
- [ ] Configure Provider screen shows only fields relevant to the selected adapter.
- [ ] Ollama flow discovers models and supports a model picker.
- [ ] llama-server flow validates endpoint/model behavior through existing provider boundaries.
- [ ] OpenAI flow persists credential references rather than raw credential values.
- [ ] OpenAI-compatible flow supports base URL, credential reference, model, and network-scope behavior through existing config.
- [ ] Test Connection uses the same provider factory/runtime used by production.
- [ ] Failed provider save/build preserves prior durable config and live runtime.
- [ ] Provider-originated health/discovery/errors are canonically sanitized.
- [ ] Add positive and negative transactional provider tests through the wizard.

## GW-140 — First-run model test and role assignment

- [ ] Add a synthetic minimal language-model inference test through the configured production provider.
- [ ] Show running, success, elapsed-time, and sanitized failure states.
- [ ] Show a short sanitized response preview on success.
- [ ] Quick Setup proposes recommended compatible assignments for episode planning, host generation/conversation, directing, and verification.
- [ ] Persist recommended role assignments through the existing durable role-assignment boundary.
- [ ] Advanced Setup can edit roles without leaving the wizard workflow.
- [ ] Do not report model readiness from configuration presence alone.
- [ ] Add model-test failure/retry coverage.
- [ ] Add restart coverage proving role assignments reload.

## GW-150 — First-run speech, voices, defaults, and Ready

- [ ] Present speech choices: KittenTTS local, OpenAI TTS, ElevenLabs, No speech yet, Advanced/Custom.
- [ ] Explain local/cloud and credential implications before save.
- [ ] Configure selected speech through normal provider config/factory/runtime boundaries.
- [ ] Discover/select friendly voice names without requiring raw voice IDs.
- [ ] Preview the focused voice through the production TTS boundary where practical.
- [ ] Support Host 1 and Host 2 default voice choices.
- [ ] Collect default episode-duration preset.
- [ ] Collect default research level.
- [ ] Preserve explicit local-only/network-scope policy.
- [ ] No speech yet may complete setup but must not masquerade as audio-ready.
- [ ] Ready screen recomputes provider, role, TTS, FFmpeg, and default readiness on mount.
- [ ] Ready screen exposes Create My First Deep Dive and Go to Dashboard.
- [ ] Restart after successful setup lands on Home.
- [ ] Invalidating a previously ready provider surfaces Setup needs attention.
- [ ] Add deterministic fake-LLM/fake-TTS end-to-end first-run acceptance.

## GW-160 — Simplified Home and navigation

- [ ] Replace the default flat subsystem-first navigation with user-goal-first navigation.
- [ ] Primary navigation exposes Home, New Deep Dive, Projects, and Library.
- [ ] Advanced section exposes Sources, Research, Hosts, Providers, Settings, and Help.
- [ ] Preserve access to existing advanced screens.
- [ ] Home provides a dominant New Deep Dive action.
- [ ] Home shows derived setup/readiness status.
- [ ] Home shows recent projects from durable summaries.
- [ ] Home shows recent episodes where durable data supports it.
- [ ] Home offers Resume Deep Dive when an incomplete wizard can be reconstructed.
- [ ] Existing project open/rename/delete operations remain available.
- [ ] Add keyboard-only navigation regression for Home/Primary/Advanced sections.

## GW-170 — New Deep Dive: Project and Sources

- [ ] New Deep Dive opens the shared seven-step guided workflow.
- [ ] Project Setup collects project name.
- [ ] Project Setup collects topic/main curiosity prompt.
- [ ] Project Setup collects user-facing audience preset.
- [ ] Project creation uses DeeperDiveService and normal workspace persistence.
- [ ] Save and Exit after project creation leaves a discoverable resumable project.
- [ ] Sources step exposes Files, Paste Text, URL, and Folder where supported.
- [ ] Source imports use existing source/corpus application services.
- [ ] Source rows show friendly identity, inclusion, indexing/readiness, and concise failure state.
- [ ] Source add/remove/include/exclude actions preserve existing provenance and security behavior.
- [ ] Continue semantics reflect actual source/index readiness.
- [ ] No acceptance test directly seeds source repository rows for the normal path.
- [ ] Add import/index failure, retry, restart, and resume regressions.

## GW-180 — New Deep Dive: Research and Hosts

- [ ] Research step offers Use only my sources.
- [ ] Research step offers Fill important gaps as the recommended middle choice.
- [ ] Research step offers Research extensively.
- [ ] Choices map to existing research policy/controller behavior.
- [ ] External-network implications are disclosed before networked research.
- [ ] Advanced research options preserve current expert controls.
- [ ] Hosts step renders friendly host rows/cards with behavior summary and voice.
- [ ] Hosts step supports one or more selected hosts.
- [ ] Host ordering is explicit and deterministic.
- [ ] Voice preview is available from the host selection workflow where speech is configured.
- [ ] Custom host creation/editing uses existing host services.
- [ ] Episode host selection never requires comma-separated raw host IDs in the normal wizard.
- [ ] Add research-policy mapping and host-order persistence tests.

## GW-190 — New Deep Dive: Episode Settings and Review/Plan

- [ ] Episode Settings collects episode title.
- [ ] Episode Settings collects main question/focus.
- [ ] Episode Settings offers duration presets plus Custom.
- [ ] Episode Settings collects audience.
- [ ] Technical depth, must-cover topics, avoid topics, and similar expert fields are available under Advanced options.
- [ ] Persist episode state through EpisodeConfigurationService.
- [ ] Validate episode fields before forward navigation.
- [ ] Review & Plan builds through EpisodePlannerService.
- [ ] Render ordered segment title, duration, and purpose/focus.
- [ ] Provide Edit Plan and Regenerate actions through supported production planner operations.
- [ ] Respect the existing post-start plan immutability/revision policy.
- [ ] Continue requires the shared valid-plan policy to pass.
- [ ] Provider/planner errors are sanitized and actionable.
- [ ] Add positive plan, negative planner output, invalid persisted plan, and post-start mutation regressions.

## GW-200 — Ready to Generate and actionable preflight

- [ ] Ready to Generate invokes the same shared preflight used by production CLI/TUI generation.
- [ ] Render readiness for sources.
- [ ] Render readiness for research policy.
- [ ] Render readiness for hosts.
- [ ] Render valid-plan status.
- [ ] Render model-role/provider/model health.
- [ ] Render speech/voice readiness.
- [ ] Render FFmpeg readiness.
- [ ] Render local-only/network-scope compatibility.
- [ ] Every blocker has an actionable route back to the relevant wizard step or advanced screen where practical.
- [ ] Continue/Generate remains disabled while blocking preflight issues exist.
- [ ] Generate starts through GenerationStartService/shared ProductionComposition.
- [ ] No wizard-specific run-creation or orchestration path exists.
- [ ] Add CLI/TUI preflight-parity regression after wizard integration.

## GW-210 — Generation Progress and failure recovery

- [ ] Create a guided Generation Progress screen backed by durable run state.
- [ ] Show current stage and completed stages.
- [ ] Preserve current informational-stage semantics; do not claim nonexistent artifacts.
- [ ] Show honest progress only where production can compute it.
- [ ] Show elapsed time and sanitized latest status.
- [ ] Support pause where durable pipeline state permits it.
- [ ] Support resume where durable pipeline state permits it.
- [ ] Support cancel with confirmation.
- [ ] Reload progress correctly after screen recreation/restart.
- [ ] Durable failure view shows stage, stable failure code when present, and sanitized message.
- [ ] Provide Retry/Resume only for supported failure states.
- [ ] Provide route back to configuration for setup/preflight repair.
- [ ] Add duplicate-action, pause/resume/cancel, resume-after-failure, and restart regressions.

## GW-220 — Episode Ready and Library handoff

- [ ] Successful generation transitions to Episode Ready.
- [ ] Episode Ready shows title, duration when available, and selected hosts.
- [ ] Episode Ready resolves playback for the selected episode/run only.
- [ ] Open in Review routes to existing transcript review.
- [ ] Export Episode uses existing export services.
- [ ] View in Library selects the generated episode.
- [ ] Simplified Library prioritizes episodes with project/time/status context.
- [ ] Library supports Play, Open, and Export.
- [ ] Preserve multi-episode isolation for playback/review/export.
- [ ] Add two-episode guided-workflow isolation acceptance.

## GW-230 — Quick Deep Dive integration

- [ ] Expose Quick Deep Dive as a recommended shortcut from Home and/or New Deep Dive.
- [ ] Quick mode still creates/uses normal durable project state.
- [ ] Quick mode requires or collects source material through normal source services.
- [ ] Apply documented recommended research, host, and episode defaults.
- [ ] Build plan through EpisodePlannerService.
- [ ] Run shared preflight.
- [ ] Start through GenerationStartService and PipelineOrchestrator.
- [ ] Produce normal durable turns, TTS, timeline/audio, review state, and exports.
- [ ] Keep QuickDeepDiveService as a convenience boundary rather than a second engine.
- [ ] Add Quick-versus-guided production-equivalence acceptance for shared artifacts/state.

## GW-240 — Save/resume and durable wizard-state recovery

- [ ] Define and implement the minimal versioned wizard draft record only if production state cannot represent a needed UI draft.
- [ ] Do not duplicate provider config, source data, host definitions, episode config, plan, run, or export data into wizard draft state.
- [ ] Save and Exit preserves partial first-run progress.
- [ ] Save and Exit preserves partial New Deep Dive progress.
- [ ] Resume computes the earliest incomplete prerequisite from production state.
- [ ] Resume preserves a later valid location when prerequisites remain valid.
- [ ] Invalid/corrupt/old draft state fails safe to the earliest derivable valid step.
- [ ] Previously completed steps move back to Needs attention when their production prerequisite becomes invalid.
- [ ] Add restart tests at every major wizard boundary.

## GW-250 — Validation, security, accessibility, and compact-terminal UX

- [ ] Preserve typed input after validation failure.
- [ ] Use inline validation for local field errors.
- [ ] Use screen-level blockers for workflow errors.
- [ ] Put technical detail behind an explicit details/help action.
- [ ] Never show raw tracebacks in the normal wizard path.
- [ ] Apply canonical recursive sanitization to all provider/runtime/user-visible errors.
- [ ] Preserve credential-reference and non-persistence rules.
- [ ] Disclose cloud/network behavior before networked actions.
- [ ] Use synthetic minimal prompts for setup tests rather than private user source material.
- [ ] Visible focus meets keyboard-only requirements.
- [ ] Completion/current/error state is not color-only.
- [ ] Primary action placement and Back semantics remain consistent.
- [ ] No normal screen requires a raw internal ID as the primary user input.
- [ ] Destructive actions require confirmation.
- [ ] 100x30 recommended layout passes.
- [ ] 80x24 compact layout passes without primary horizontal scrolling.
- [ ] Below-minimum viewport shows a clear resize message while preserving state.
- [ ] Add accessibility/focus/layout regression matrix.

## GW-260 — Shared acceptance fixture and end-to-end guided workflow

- [ ] Extend/reuse the deterministic production acceptance fixture rather than create one-off repository seeding.
- [ ] First-run acceptance configures a deterministic LLM through normal provider boundaries.
- [ ] First-run acceptance configures deterministic TTS/voices through normal provider boundaries.
- [ ] First-run acceptance persists recommended roles and reaches derived Ready.
- [ ] New Deep Dive acceptance creates project through DeeperDiveService.
- [ ] Acceptance adds/indexes source through production source APIs.
- [ ] Acceptance selects research policy through production mapping.
- [ ] Acceptance selects hosts through host services.
- [ ] Acceptance persists episode through EpisodeConfigurationService.
- [ ] Acceptance builds a plan through EpisodePlannerService.
- [ ] Acceptance passes shared preflight.
- [ ] Acceptance starts through GenerationStartService.
- [ ] Acceptance generates multiple durable turns through PipelineOrchestrator.
- [ ] Acceptance synthesizes TTS/timeline/audio through production services.
- [ ] Acceptance reaches Episode Ready and exports through shared export services.
- [ ] Acceptance reopens the episode from Library.
- [ ] Prove no direct normal-path seeding of plan, run, turn, TTS, timeline, or export repository rows.

## GW-270 — Compatibility and regression protection

- [ ] Existing provider configuration still loads.
- [ ] Existing projects and sources still open.
- [ ] Existing hosts still open.
- [ ] Existing episode configs/plans/runs/turns/provider identities still open.
- [ ] Existing timelines/audio/exports still open.
- [ ] Existing Transcript Review and targeted repair remain usable.
- [ ] Existing advanced Sources/Research/Hosts/Providers/Settings screens remain usable.
- [ ] Existing CLI acceptance remains green.
- [ ] Existing production-generation remediation suites remain green.
- [ ] No migration is introduced unless required by a documented compatibility case.
- [ ] If a migration is required, prove idempotence, failure safety, and rollback/read compatibility.

## GW-280 — Documentation

- [ ] Document first-run setup.
- [ ] Document Quick versus Advanced setup.
- [ ] Document local versus cloud provider choices.
- [ ] Document New Deep Dive guided workflow.
- [ ] Document Quick Deep Dive shortcut semantics.
- [ ] Document advanced navigation.
- [ ] Document keyboard controls.
- [ ] Document terminal-size requirements.
- [ ] Document Save/Exit/resume behavior.
- [ ] Document common setup/preflight blockers and recovery.
- [ ] Document that wizard flows reuse the same production services as CLI and advanced TUI.
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
- Focused first-run tests:
- Focused New Deep Dive tests:
- Keyboard/focus/layout tests:
- Recovery/resume tests:
- Security/redaction tests:
- Quick Deep Dive parity tests:
- Multi-episode isolation tests:
- Compatibility tests:
- Final master SHA:
- Final exact-head CI run:
- Quality job:
- Fresh-machine installed-wheel result:
- Mandatory KittenTTS result:
- Compatibility/migration decision:
