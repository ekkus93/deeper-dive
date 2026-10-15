# Deeper Dive second post-review consumer inventory

> **Path note (2026-10-14):** `tests/test_guided_episode_wizard.py` was split into `tests/test_guided_episode_wizard_part1.py` and `..._part2.py`, and `tests/test_second_post_review_dirty_navigation.py` into `..._part1.py`, `..._part2.py` and `..._part3.py` (commit `4ede40e`). Test function names are unchanged; find one with `grep -l "def test_name" tests/`.

**Baseline:** `master` at `493b1a76b02719f9973dbdcc3f86931c90624bd1`, 2026-10-12.
**Purpose:** Source inventory for the unchecked SPR-000 consumer-audit item of
`DEEP_DIVE_TUI_SECOND_POST_REVIEW_REMEDIATION_TODO_2026-10-09.md`.
This is an orientation map, **not** a test pass, reproduction, or checkbox reconciliation.

## Guided state, navigation, and rehydration (SPR-01/02)

- `src/deeper_dive/wizard_shell.py`: `WizardShell` owns the per-step editable
  widget matrix, snapshot baselines, dirty transitions, Save/Discard/Cancel modal,
  explicit navigation targets, default Cancel focus, checkpoint-and-exit,
  typed `WizardSaveResult`, and shell Back/Continue.
- `src/deeper_dive/guided_workflow.py`: `WizardState` and
  `WizardNavigator` define first-run and New Deep Dive step transitions,
  completion prerequisites, and UI-only serializable navigation state.
- `src/deeper_dive/guided_app.py`: `GuidedDeeperDiveApp.action_navigate`
  intercepts wizard global navigation and initializes/reloads New Deep Dive
  project/episode/run identity; Quick Deep Dive enters production setup/preflight.
- `src/deeper_dive/guided_draft.py`: `GuidedDraftStore` persists/resumes
  minimal safe wizard state; project/episode/run identities must remain durable
  service-owned records rather than unsaved form content.
- `src/deeper_dive/guided_first_run.py`: `GuidedFirstRunWizard` owns
  provider/model/speech/voice/default inputs, preset selector changes,
  discovery, runtime readiness updates, and provider-backed save actions.
  Review `on_select_changed`, `_sync_setup_controls`,
  `action_discover_models`, `action_discover_voices`, and
  `_load_existing_setup` together for asynchronous rehydration.
- `src/deeper_dive/guided_new_deep_dive.py`: project create/save/validation.
- `src/deeper_dive/guided_source_wizard.py`: pasted/file/URL source imports,
  source selection and inclusion, policy selection, `_refresh_research_choice`.
- `src/deeper_dive/guided_host_wizard.py`: loaded host ID, profile form,
  episode-ordered host IDs, selection guards, `_load_selected_host`,
  paired profile/membership save and discard restoration.
- `src/deeper_dive/guided_episode_wizard.py`: episode settings and plan segment
  forms, screen resume, segment-picker guards, `_load_episode_form`,
  `_refresh_plan`, `_load_selected_segment`, and production save paths.
- `src/deeper_dive/guided_ready.py` and
  `src/deeper_dive/guided_generation.py`: downstream screen resumes
  and generation entry points that must not silently reset a pending wizard edit.

## Readiness and provider I/O (SPR-03)

- `src/deeper_dive/guided_async_readiness.py`: bounded
  `FirstRunReadinessCoordinator`, worker budget, fingerprint supersession,
  callback publication, timeout state, and close behavior.
- `src/deeper_dive/guided_first_run.py`: readiness status rendering,
  setup-step relocation, refresh and retry entry points.
- `src/deeper_dive/provider_tui.py` and concrete provider adapters:
  `health()`, `models()`, `voices()`, runtime construction and transport
  deadlines require end-to-end verification; a UI timeout alone cannot cancel
  an uninterruptible adapter call.

## Configuration and sanitization (SPR-04/05/06)

- `src/deeper_dive/user_config.py`: `UserConfig` semantic defaults,
  `ProviderConfig` URL/credential-reference validation, `UserConfigStore`
  revision/CAS, locks, unique temp write, fsync and atomic replace.
- `src/deeper_dive/provider_tui.py`: `ProviderController` candidate
  validation and publication; inspect all save and CLI/TUI mutation call sites.
- `src/deeper_dive/settings_screen.py`: user defaults and provider settings.
- `src/deeper_dive/diagnostics.py`: recursive value/exception redaction,
  HTTP authentication headers, URL queries/fragments/userinfo, log payloads,
  and support-bundle export.
- CLI entry points under `src/deeper_dive/` and Textual status/error displays
  remain separate *publication surfaces* to check for credential canaries.

## Episode lifecycle, planning, and output (SPR-07)

- `src/deeper_dive/episode_config.py`: `EpisodeConfigurationService`
  durable episode editing, plan invalidation, lifecycle/CAS rules.
- `src/deeper_dive/episode_planner.py`: `EpisodePlannerService` plan inputs,
  snapshots and regeneration.
- `src/deeper_dive/preflight.py` and
  `src/deeper_dive/generation_start.py`: generation admission,
  preflight checks and durable run creation.
- `src/deeper_dive/episode_library_screen.py`: Library selection and
  resume/playback surfaces; verify project/episode/run artifact identity.
- `src/deeper_dive/guided_episode_wizard.py`: saved settings and plan
  rehydration; no-op editing must preserve non-draft runs and plans.

## Existing deterministic coverage and open verification

- `tests/test_second_post_review_first_run_form_matrix.py` and
  `tests/test_second_post_review_dirty_navigation.py`: form navigation,
  cancel/discard, screen resume, selector and order regression pilots.
- `tests/test_second_post_review_create_host_dirty.py`,
  `tests/test_second_post_review_model_discovery_dirty.py`,
  `tests/test_second_post_review_voice_rediscovery.py`, and
  `tests/test_second_post_review_speech_reselection.py`: explicit
  potentially destructive actions and rediscovery/reselection cases.
- `tests/test_second_post_review_readiness_budget.py` and
  `tests/test_second_post_review_readiness_publication.py`: worker budget,
  supersession and callbacks.
- `tests/test_second_post_review_config_failure_matrix.py` and
  `tests/test_second_post_review_security_cross_surface.py`: persistence
  failure paths and diagnostic canary surfaces.
- `tests/test_second_post_review_tui_episode_lifecycle.py` and
  `tests/test_second_post_review_tui_lifecycle_acceptance.py`: lifecycle
  and production TUI regression tests.

**Remaining to qualify:** Each consumer path must be exercised against
the SPR specification, including invalid saves, parallel writers, actual
adapter transport deadlines, restart/installed-wheel runs and all cross-surface
canary sinks. The authoritative TODO stays unchecked until qualifying tests,
exact-head CI and evidence reconciliation are complete. No untested concern
above is represented as a reproduced defect.
