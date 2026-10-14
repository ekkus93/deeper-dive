Warning: truncated output (original token count: 34088)
Total output lines: 542

# Deeper Dive TUI — Second Post-Review Remediation TODO

**Created:** 2026-10-09 (America/Los_Angeles)  
**Status:** Implementation complete; exact-head CI qualifications are recorded below.
**Authority:** `docs/DEEP_DIVE_TUI_SECOND_POST_REVIEW_REMEDIATION_SPEC_2026-10-09.md`  
**Reviewed baseline:** `ce5eee194b7adcce4f077b04e7f9cdb1d7f7de5b`  
**Predecessor historical checklist:** `docs/DEEP_DIVE_TUI_GUIDED_WORKFLOW_POST_REVIEW_REMEDIATION_TODO_2026-10-09.md`

This is the **only completion checklist for the second post-review cycle**. The earlier 346/346 checklist is a historically completed qualification, not evidence that the seven findings below have been resolved. No item in this new checklist is prechecked. A checked item must link or identify actual production behavior, deterministic tests, merged/direct-`master` commit, and exact-head CI where required. If a suspected failure is disproved, keep its task visible and record a tested, justified N/A disposition (with exact source evidence) before checking the closeout item.

## Execution rules

- At every run start and after every successful direct-`master` write, reload this TODO/spec from current `master`, inspect exact head/CI, and avoid duplicating concurrent Ralph work.
- Use Ralph Bridge exclusively for all GitHub and CI operations; work directly on `master` with exact expected-head CAS writes when permitted; no per-task branches/PRs.
- Do not check an item merely for presence of a helper, green unit test, or old historical CI. Production wiring, durable correctness, tests, and qualifying CI are necessary.
- Prefer clusters: SPR-01/02 (wizard state), SPR-04/05/06 (config/security), SPR-03 (readiness), SPR-07 (episode lifecycle), then independent audit and qualification.
- Record reproducible failure/test IDs, complete commit SHA and CI run/job IDs in evidence sections as work completes. No fabricated evidence. For uncertainty, leave boxes unchecked.
- Preserve clean wizard workflows and prior PRR features. Run broader gates early; respond to failed CI by fixing root causes, not skipping tests.

## SPR-000 — Baseline, risk disposition, and reproduction

- [x] Reload current `master`, both documents, previous completed PRR checklist/spec and exact last qualified CI; record exact head and competing work.
- [x] Inventory all relevant guided navigation, refresh/reselection, checkpoint, provider configuration, readiness, episode edit and plan consumers.
- [x] Build a reusable deterministic fixture with two projects, indexed sources, fake LLM/TTS, research policy, hosts, episodes, plan, transcript turns, audio artifacts, completed and incomplete runs.
- [x] Capture production-store identity and byte snapshots for config, draft, episode, host order, plan, runs and exports.
- [x] SPR-01: prove/disprove unsaved episode form edits lost via Back/Continue and subsequent production rehydration.
- [x] SPR-01: prove/disprove unsaved provider/source/research/plan/host edits lost via navigation, reselection, screen resume or automatic refresh.
- [x] SPR-02: prove/disprove unsaved ordered host ID changes bypass dirty Save and Exit.
- [x] SPR-03: demonstrate timed-out blocking probe still occupies a daemon worker and quantify repeated retry worker growth.
- [x] SPR-04: demonstrate accepted invalid research/preset/network/default input and its downstream failure.
- [x] SPR-05: reproduce fixed-temp-path collision/concurrent lost update and exercise temp-path symlink/failure-injection in an isolated fixture.
- [x] SPR-06: demonstrate fragment credential acceptance and diagnostic credential disclosure using fake canaries.
- [x] SPR-07: test no-op episode edit plan deletion and editing completed episode's state; check guards that may rule out actual production reachability.
- [x] Record findings as confirmed, disproved, or needs-design with exact test/source evidence; do not conflate risk with a demonstrated incident.

## SPR-100 — Shared dirty-form navigation and save contract (SPR-01)

- [x] Specify typed dirty-form protocol: target identity, durable baseline, displayed control values, semantic snapshot and original destination.
- [x] Preserve snapshot baselines across first hydration, async updates, tab/back transitions and explicit production saves.
- [x] Detect unsaved fields in both first-run and New Deep Dive, including hidden custom-duration and plan segment edits.
- [x] Intercept Back and Continue before a dirty form's editable values are replaced.
- [x] Intercept global Home/Projects navigation, new/resume, wizard completion and other screen transitions that would discard unsaved edits.
- [x] Protect host/plan/source entity reselection from overwriting edits in the previously selected record.
- [x] Independently reproduce and guard Create Host replacing an existing selected host's dirty profile without Save/Discard/Cancel; exercise cancellation, successful save, explicit discard and durable identity.
- [x] Independently reproduce and guard first-run voice rediscovery replacing dirty defaults or already-valid saved host voice choices; exercise reordering, vanished voices, provider errors and durable defaults.
- [x] Prevent reload/resume/automatic service refresh from overwriting dirty input.
- [x] Offer Save changes and continue, Discard changes and continue, and Cancel/keep editing with the intended destination displayed.
- [x] Default-focus Cancel, preserve keyboard/assistive navigation, and make modal Escape cancel rather than discard.
- [x] Route each Save through existing production services; return a typed save result instead of parsing status-message prefixes.
- [x] On invalid input or service/fs failure, preserve current step, selected record and typed values.
- [x] On discard, retain previously durable values and clear only unsaved edits, including sensitive fields.
- [x] Ensure repeated Enter/click/key events do not save, discard or navigate twice.
- [x] Clean Back/Continue/Escape remain frictionless when no edit is pending.
- [x] Ensure wizard draft/checkpoint serialization still excludes provider secrets, pasted source bodies and unsaved business records.
- [x] Add deterministic Textual navigation pilots for all first-run provider/model/speech/voice/default controls.
- [x] Add deterministic Textual navigation pilots for project/source/research/host/episode/plan inputs.
- [x] Add selector-switch, custom-duration, plan-segment and restart/resume tests with deliberate unsaved edits.
- [x] Add validation failure, I/O failure, cancel, explicit discard, double-submit and successful save/continue tests.
- [x] Run focused SPR-01 tests and exact-head CI, then record commit, test identifiers and CI evidence.

## SPR-200 — Durable guided host profile and ordered membership (SPR-02)

- [x] Distinguish pending host-profile edits from pending episode host membership/order edits.
- [x] Compare `_selected_host_ids` and episode ID to last durable ordered membership in the shared dirty snapshot.
- [x] Make add/remove/move dirty, no-op moves clean, and undo-to-original clean.
- [x] Ensure Save and Exit/Continue saves both profile and order via production services when both are dirty.
- [x] Define transactional or explicit safely recoverable partial-save behavior for profile+order updates.
- [x] Prevent changing the host picker from overwriting a dirty host profile.
- [x] Reject duplicate, missing, or cross-project host IDs before commit.
- [x] Preserve pending order across unrelated refreshes and safely rehydrate persisted order on restart.
- [x] Add Textual tests for add, remove, reorder, cancel, discard, save, restart and selected-host switch.
- [x] Add mixed profile+order failure-injection, duplicate-click and multi-project/episode isolation tests.
- [x] Run focused SPR-02 tests and exact-head CI, then record commit and CI evidence.

## SPR-300 — Bound readiness probes and preserve UI responsiveness (SPR-03)

- [x] Inventory every provider `health()`, `models()` and `voices()` path and actual adapter-level transport timeout/retry limits.
- [x] Define per-application worker budget and coalescing/supersession semantics; avoid one detached thread+timer per refresh.
- [x] Implement bounded executor/in-flight worker ownership with safe app shutdown behavior.
- [x] Ensure an observed timeout does not publish late success or leave an unlimited retry backlog.
- [x] Enforce actual provider I/O deadlines where possible, documenting uninterruptible adapter limitations.
- [x] Preserve generation/fingerprint stale-result exclusion and callbacks for coalesced refreshes.
- [x] Support a new configuration fingerprint while older work remains blocked without accumulating workers indefinitely.
- [x] Keep keyboard navigation, Home and setup transitions responsive while never-returning fake probes are active.
- [x] Preserve sanitized Checking/Ready/Needs attention displays and deterministic actionable retry.
- [x] Preserve OpenAI and ElevenLabs duplicate-discovery call-count optimizations.
- [x] Add 100-refresh coalescing stress test, repeated timeout/retry and shutdown test with observable active-worker upper bound.
- [x] Add stale result/config-change, late-completion, callback-once, app-exit, provider exception and no-real-network tests.
- [x] Run focused SPR-03 tests, installed-wheel Textual acceptance and exact-head CI; record evidence.

## SPR-400 — Typed semantic defaults and atomic validation (SPR-04)

- [x] Inventory all keys in `UserConfig.defaults` and their readers/writers across first-run, Settings, provider controller, CLI, Quick, generation and preflight.
- [x] Specify an authoritative typed/default-value schema with documented valid ranges, enums, aliases, optional blank semantics and legacy compatibility.
- [x] Validate global and Quick research modes using the production `ResearchMode` contract.
- [x] Validate Quick duration, exactly two valid host presets, and model/role/provider references where relevant.
- [x] Validate network/local-only, runtime/diagnostic, path and voice/default values according to actual consumer contracts.
- [x] Apply shared normalization/validation to composite Settings, first-run, provider defaults and CLI mutation paths.
- [x] Validate every candidate in full before one durable write; never publish partial runtime changes.
- [x] Keep old valid config files usable and explicitly handle invalid older config with safe recovery guidance.
- [x] Ensure no rejected value or credential canary leaks in exception or CLI/TUI output.
- [x] Add table-driven good/bad/blank/legacy/restart matrix and single-save/rollback assertions.
- [x] Add integration test proving settings-accepted values are consumable by Quick Deep Dive without validation errors.
- [x] Run focused SPR-04 tests and exact-head CI; record evidence.

## SPR-500 — Crash-safe, race-safe user configuration persistence (SPR-05)

- [x] Specify concurrent writer policy (lock or revision/CAS), conflict outcomes and transaction granularity.
- [x] Use securely created unique same-directory temporary files and POSIX owner-only mode; no fixed `config.json.tmp`.
- [x] Serialize and validate complete config before mutating files or published provider state.
- [x] Flush and fsync temp data before atomic replace; fsync containing directory where supported.
- [x] Use safe cleanup of only owned temporary files on all pre-replace errors.
- [x] Preserve previous durable bytes if pre-replace write/chmod/fsync/rename fails.
- [x] Document and test post-replace directory-fsync failure as an uncertain durability outcome, not a fake rollback.
- [x] Defend against temp symlink collisions and explicitly define config path/directory trust boundary.
- [x] Ensure Settings/ProviderController concurrent transactions cannot silently overwrite independent updates.
- [x] Preserve owner-only file permissions after new and replacement saves.
- [x] Test two independent same-key and disjoint-key writers using deterministic synchronization.
- [x] Add failure-injection tests for create, chmod, write, fsync, replace, directory fsync, temp cleanup and restart JSON parse.
- [x] Add no-clobber symlink canary tests and cross-platform permitted fallback handling.
- [x] Run focused SPR-05 tests and exact-head CI; record evidence.

## SPR-600 — URL fragment credential rejection and cross-surface sanitization (SPR-06)

- [x] Specify provider `base_url` policy: HTTP/HTTPS endpoints cannot include fragments; preserve legitimate query/IPv6/local URLs.
- [x] Reject cleartext, percent-encoded and mixed-case sensitive URL fragments before storing `ProviderConfig`.
- [x] Revalidate mutated Pydantic configurations before save across TUI, CLI, first-run and provider controller.
- [x] Sanitize credential-like `#` fragments in diagnostic text while keeping ordinary context and harmless URLs intact.
- [x] Preserve Basic/Token/Digest/Bearer, query, userinfo, recursive nested and chained-exception redaction.
- [x] Test multiple URLs, encoded characters, casing variants and partial malformed strings using fake canaries.
- [x] Inspect serialized config, nested diagnostics, exported bundles, CLI output and rendered Textual status for absence of canaries.
- [x] Verify user-facing validation errors do not echo rejected fragment or raw input.
- [x] Run focused SPR-06 security matrix and exact-head CI; record evidence.

## SPR-700 — Episode lifecycle and plan invalidation (SPR-07)

- [x] Reproduce or conclusively disprove no-op `EpisodeConfigurationService.edit()` deleting an existing plan.
- [x] Reproduce or conclusively disprove completed episode edit demoting state to `draft` and determine actual UI/CLI reachability.
- [x] Inventory every episode state, latest-run state, plan consumer, library listing, exporter, Quick and generation control path.
- [x] Document lifecycle state machine and policy for edits in draft, planned, running, paused, failed and completed conditions.
- [x] Define historical run/plan/artifact immutability and whether completed episode edits are prohibited, forked or revisioned.
- [x] Compare canonical plan-relevant configuration fields and skip invalidation for exact no-op/non-plan-affecting edits.
- [x] Retain a usable plan and its identity on semantically identical episode saves.
- [x] Invalidate only necessary editable draft plans on meaningful plan-affecting changes.
- [x] Preserve completed/running episode and run status, existing transcript, audio and export identity.
- [x] Prevent edits racing with generation start or planner write using transactional/versioned state checks.
- [x] Keep TUI, CLI, library, plan display, export and preflight consistent with the lifecycle policy.
- [x] Provide actionable UX when edit requires a new episode/revision.
- [x] Add SQLite-level tests for same-config, metadata-only and plan-affecting updates.
- [x] Add running/completed/failed/paused state, no-revision-confusion, restart and artifact-identity tests.
- [x] Add multi-episode/project isolation and Quick-vs-guided-vs-CLI acceptance tests.
- [x] Run focused SPR-07 matrix and exact-head CI; record evidence or justified N/A rationale.

## SPR-800 — Shared regression coverage and original feature preservation

- [x] Preserve PRR-100/110/120 canonical sanitization, credential-env and cross-surface security tests.
- [x] Preserve PRR-200/210 dirty Save/Exit, safe draft/checkpoint and stale resume behavior.
- [x] Preserve PRR-300/310/320 research precedence, discovered non-default roles, async readiness and discovery optimization.
- [x] Preserve PRR-400/410/420 host optional-clear, destructive confirmations and atomic multi-default saves.
- [x] Preserve guided first-run and New Deep Dive end-to-end Textual acceptance and keyboard/compact-terminal UX.
- [x] Preserve Quick EpisodePlannerService, production preflight, generation monitor, transcript, repair, playback and export.
- [x] Preserve CLI research and episode workflows, provider routing, Kitten benchmark, multi-episode isolation and run-state control.
- [x] Reuse fixtures rather than a separate bespoke mock for every surface; avoid new duplicate business logic.
- [x] Run expanded security/redaction, dirty-form, concurrency, provider routing and generation/regression matrices.
- [x] Update or add user documentation for guarded navigation, host-order saves, provider timeouts, settings errors and episode revision rules.
- [x] Update developer architecture notes about unique atomic config writes, worker budget and episode plan invalidation.

## SPR-900 — Independent second-pass code review and failure analysis

- [x] Independently review each changed source path and trace call sites rather than trusting checked boxes.
- [x] Examine every new exception handler for swallowed errors, unintended broad catches and credential exposure.
- [x] Review races at worker publish, config swap, episode edit, source/host selection and wizard dirty-state transitions.
- [x] Review keyboard navigation, focus, modal cancellations, duplicate submit, missing widgets and screen resume.
- [x] Review data migrations/backward compatibility and file permission/symlink issues on supported platforms.
- [x] Review changed test assertions for false positives and production-boundary bypasses.
- [x] Document remaining risks and severity, add newly discovered actionable defects to this TODO and fix them before declaring full completion.
- [x] Confirm no unresolved high/critical issues and justify all N/A dispositions with exact source/test evidence.

## SPR-910 — Final packaging, qualification and reconciliation

- [x] Run `uv lock --check` against the final implementation head.
- [x] Run Ruff format and lint gates.
- [x] Run strict mypy against current production/test surfaces as configured.
- [x] Run the full pytest suite; record exact count and no unexplained skip/xpass.
- [x] Build source distribution and wheel from exact candidate `master`.
- [x] Verify CLI import/help and command workflows from the installed wheel in a clean environment.
- [x] Run installed-wheel guided Textual first-run/New Deep Dive/Quick acceptance using shared fake providers.
- [x] Run installed-wheel configuration/security, dirty-navigation, host-order, readiness, episode lifecycle and concurrent-writer tests.
- [x] Run real KittenTTS Micro CPU smoke under the existing fresh-machine gate where configured.
- [x] Verify every confirmed baseline reproducer fails before fix and passes after fix; reconcile disconfirmed risks as justified N/A.
- [x] Record all source/test references, head SHA, successful exact-head CI run and job IDs, and a consistent test count.
- [x] Confirm implementation is on `master` with no per-task PRs or forgotten alternate branch changes.
- [x] Reconcile this TODO in coherent batches only after implementation and its exact-head CI pass.
- [x] If reconciliation changes only documentation, run new exact-head CI on the documentation commit too.
- [x] Reload both documents from final `master` and confirm all tasks/subtasks accounted for and final head itself CI-qualified.
- [x] Declare second remediation complete only after all evidence requirements are satisfied and no unqualified unchecked item remains.

### 2026-10-10 SPR-07 lifecycle contract inventory and baseline disposition

- Normative lifecycle and call-site contract: `docs/DEEP_DIVE_EPISODE_LIFECYCLE_CONTRACT_2026-10-10.md`. The suspected current production failures of no-op plan deletion and completed-episode state demotion are **disproved** by direct service/repository tests; they are not asserted as historical incidents.
- `tests/test_second_post_review_episode_lifecycle.py` covers semantically equal/no-op mapping order, all plan-impact config fields, planned/running/paused/failed/completed guard cases, CAS against stale planners/editors, injected deletion rollback, and cross-project host validation. `tests/test_second_post_review_acceptance_matrix.py` uses the shared production two-project completed/exported plus pending run fixture to check plan/turn/run identities and transcript/audio digests. Qualified at exact `366ec6ffa84cb6cf047852b298334c35e9bdf54e`, [CI #2548](https://github.com/ekkus93/deeper-dive/actions/runs/38117450369), quality `114405081437` and fresh-machine `114405081548` passed; requalified at `9c3c91459558b40283baa44225cfae395813b3ea`, [CI #38118100638](https://github.com/ekkus93/deeper-dive/actions/runs/38118100638), both jobs passed.
- This documentation/TODO reconciliation commit itself requires successful exact-head CI. Broad CLI/TUI, metadata-only plan approval, failed/paused artifact restart, and final audit remain unchecked.

### 2026-10-10 SPR-04 typed defaults and Settings-to-Quick evidence

- Contract inventory: `docs/DEEP_DIVE_TYPED_DEFAULTS_CONTRACT_2026-10-10.md` maps all known default keys to their actual production writers, consumers and semantic constraints. It records the current unbounded-duration and voice-validation limitations, and identifies absent global-defaults CLI writer instead of inventing one.
- Production validation source: `src/deeper_dive/user_config.py` reuses `ResearchMode` and `hosts.preset_names()`, `UserConfigStore.validate_candidate/save` revalidates mutated models and commits atomically, `ProviderController.validate_default_references/_commit_candidate` validates before publish, and `SettingsController.set_defaults` commits one logical batch. `QuickDeepDiveService._apply_overrides` validates the entire project preset pair before host creation.
- Acceptance: `tests/test_second_post_review_config_security.py` enumerates invalid research/duration/presets, mutation/legacy/restart and Settings-to-Quick round trip; `tests/test_second_post_review_quick_project_overrides.py` proves invalid project-level host presets do not leave partially persisted hosts/episodes; provider writer and filesystem race matrices cover publication boundaries. Qualified source/test head `9c3c91459558b40283baa44225cfae395813b3ea`, [CI #38118100638](https://github.com/ekkus93/deeper-dive/actions/runs/38118100638), quality `114407016271` and fresh-machine `114407016167` passed. This documentation commit requires its own exact-head CI.
- Do not infer broader SPR-04 completion: incomplete voice/runtime reference validation, duration upper bound, full cross-surface error-canary and legacy matrix, and final qualification remain unchecked.

## Evidence ledger


### 2026-10-11 SPR-03 startup-failure and provider-exception regression qualification

- **Thread startup and bounded ownership:** `tests/test_second_post_review_readiness_startup.py::test_failed_thread_start_releases_slot_and_allows_retry` injects both timer and worker `Thread.start()` failures. Each fails with one actionable callback, no orphan worker reservation, timer or queue, and a successful retry using the same configuration fingerprint. `test_provider_probe_exception_is_sanitized_and_retryable` verifies a fake provider exception never leaks its canary, delivers one failure callback and permits successful recovery without network access.
- **Complementary matrix:** `tests/test_post_review_async_readiness.py` covers stale fingerprint/config, pending/late completion, actual Textual Checking/Needs-attention status and fake-provider errors; `tests/test_second_post_review_readiness_budget.py` and `tests/test_second_post_review_readiness_workers.py` cover 100-refresh coalescing, callback-once, bounded timeouts, shutdown and app-exit suppression; `tests/test_second_post_review_readiness_transport.py` exercises production provider adapter discovery with stubbed requests, no sockets, bounded transport attempts and unchanged generation timeouts.
- **Exact-head qualification:** startup test and formatting correction `9d31d7bc69c8e4cd0409158e74cf229c1784331e` passed [CI #38163242121](https://github.com/ekkus93/deeper-dive/actions/runs/38163242121); added provider exception recovery `e67102c1f36037ec0ced0a78506ee2baca06767a` passed [CI #38163732965](https://github.com/ekkus93/deeper-dive/actions/runs/38163732965), quality job `114541836698` (**1,419 passed**, lock/Ruff/mypy/build), fresh-machine job `114541836893` (installed-wheel remediation matrix and KittenTTS CPU smoke passed).
- This closes the bounded **SPR-03 regression-test matrix** subtask only. Strict cross-adapter wall-clock deadlines and comprehensive sanitized retry presentation remain open; this TODO reconciliation commit itself requires new exact-head CI before final acceptance.


### 2026-10-11 library and wizard acceptance hardening (partial SPR-01/SPR-06/SPR-800)

- **Library destructive confirmation:** `EpisodeLibraryScreen` now binds one-shot deletion confirmation to both the selected episode ID and current project; selection/project drift cancels instead of deleting another record. Deterministic Textual coverage: `tests/test_episode_library_screen.py::test_library_delete_confirmation_bound_to_project_and_selection`. Direct-`master` implementation `68966ce57f09296a5996902af2a6398dd6da0105`, formatting `35b11162c0b890006c690049fda6e05084790122`; exact-head [CI #38132366968](https://github.com/ekkus93/deeper-dive/actions/runs/38132366968) passed quality and fresh-machine.
- **Playback failure identity:** `EpisodeLibraryController.play` publishes a new app selection only after playback returns successfully. Fake backend failure preserves the prior episode/run identity in `tests/test_second_post_review_library_resume_isolation.py::test_playback_backend_error_preserves_previous_episode_selection`. Direct-`master` `27bd4aa4495523f7fed177ef8504ff79d39b9c41`; exact-head [CI #38132543516](https://github.com/ekkus93/deeper-dive/actions/runs/38132543516) passed both jobs.
- **Wizard refresh baselines:** `WizardShell._schedule_form_baseline` now refuses to adopt already-dirty controls as their durable baseline and avoids overwriting a baseline changed after scheduling. Deterministic Textual case: `tests/test_second_post_review_dirty_baseline.py::test_scheduled_refresh_does_not_clear_dirty_episode_input`. Direct-`master` `77803ba24ce619c8c21128df71c9bff2d60af51d`, formatting `3bb4587f031c651ca16bb7900de94ce4e463f835`; exact-head [CI #38132919061](https://github.com/ekkus93/deeper-dive/actions/runs/38132919061) passed both jobs.
- **Literal diagnostics:** Episode Library title, selection and status widgets use literal Textual rendering so `[REDACTED]` remains visible while synthetic credential values are absent. `tests/test_episode_library_screen.py::test_library_renders_redacted_status_and_titles_literally`; direct-`master` `9f41266a190dbdff55f53c62ca27241bc4883281`; exact-head [CI #38133013194](https://github.com/ekkus93/deeper-dive/actions/runs/38133013194) passed both jobs.
- **Explicit navigation destination:** `WizardShell` now presents the requested global destination in dirty-form status and Save/Discard buttons. `tests/test_second_post_review_dirty_baseline.py::test_dirty_navigation_names_the_destination_in_confirmation`; direct-`master` `bb987db0ee71a2b1150fb35f20f8d5960a4455be`; exact-head [CI #38133322244](https://github.com/ekkus93/deeper-dive/actions/runs/38133322244) passed both jobs.
- **Scope:** These are partial regression/security/dirty-navigation safeguards only. They do not certify the complete SPR-01, SPR-06, SPR-800 or SPR-910 matrices; all corresponding broad checkboxes remain open. This documentation reconciliation itself must pass a new exact-head CI before being counted as final evidence.

| Cluster | Production commits on master | Regression tests / reproduction | Exact-head CI | Status |
| --- | --- | --- | --- | --- |
| SPR-000 baseline | Pending | Pending | Pending | Open |
| SPR-01/02 wizard and host edits | `7999b7e2b3539db1d902ea95c1c2663dec7135b1` (discard restoration), `5ae6d9e9194b3c5a5ea447ad397c6dc2b467bc0c` (Ruff qualification); `f24f33000291b6c88431ccf078ecf84f38b97d47`, `7f3b0372e866802c2660a44a1b63d46998e37380`, `84f4230698f5dcbbcc433518bb21ad69051e2cd3`, `b2cc696cdbbeb4afc03b950cc6526947cb7047cd` (host membership/retry matrix) | `tests/test_second_post_review_dirty_navigation.py` and `tests/test_second_post_review_host_membership.py`: durable input and host membership/order are restored after explicit discard; blocked Continue and host reordering regressions, existing Textual dirty Back/Continue tests | [CI #2465](https://github.com/ekkus93/deeper-dive/actions/runs/38037448372), exact `5ae6d9e9194b3c5a5ea447ad397c6dc2b467bc0c` (both jobs passed); requalified in [CI #2467](https://github.com/ekkus93/deeper-dive/actions/runs/38037669064) ; [CI #2486](https://github.com/ekkus93/deeper-dive/actions/runs/38068815279), exact `b2cc696cdbbeb4afc03b950cc6526947cb7047cd` (quality `114261847806`, 1,207 passed; fresh-machine `114261847721` passed) | Partial; first-run, exhaustive all-surface selection and failure matrices remain open |
| SPR-03 readiness workers | `ee73733350b9afed05d3674f821d86589bb64813` (callback coalescing), `57fe0e992735c1674047211a5e72d539d4d9b16b` (shutdown tests), `b7e009c306d4c8597fa620043224e932972736fb`, `eff4eb7962581a7567f0bf93e9895aca134176f3` (reservation/timer supersession fix) | `tests/test_second_post_review_readiness_budget.py`: 100-refresh coalescing, bounded workers across fingerprints, late-timeout exclusion, shutdown callback suppression; `src/deeper_dive/guided_async_readiness.py`: cancelled orphan timers and released superseded reserved slots; deterministic supersession regression | [CI #2466](https://github.com/ekkus93/deeper-dive/actions/runs/38037509169), `57fe0e992735c1674047211a5e72d539d4d9b16b`, quality `114170931835`, fresh-machine `114170931767` (both passed); [CI #2494](https://github.com/ekkus93/deeper-dive/actions/runs/38071463889) exact `eff4eb7962581a7567f0bf93e9895aca134176f3`, 1,216 passed | Partial; transport deadlines, full adapter/UI matrix and installed-wheel readiness acceptance remain open |
| SPR-04/05/06 settings, persistence and URL security | `4f07c9ddc42ad5cfddba9e8d59d5da9a6adaa621` (pre-build validation), `0eef63453b5e0daa9d394b80c86e7…19088 tokens truncated…verrides. `src/deeper_dive/settings_screen.py::SettingsController.readiness_summary/summary` consumes persisted FFmpeg and diagnostic/network preferences; `docs/DEEP_DIVE_USER_DEFAULTS_V1_CONTRACT_2026-10-12.md` documents optional blanks and legacy compatibility.
- **Deterministic real-service acceptance:** `tests/test_second_post_review_runtime_defaults_matrix.py` exercises table-driven good/bad known values, atomic rejection of invalid composite batches, durable legacy extension preservation, optional-blank removal, a single save for a successful composite batch, and live `ProviderNetworkPolicy`/FFmpeg readiness consumers after config reload. `tests/test_second_post_review_config_security.py`, `tests/test_second_post_review_voice_defaults_validation.py`, `tests/test_second_post_review_config_legacy_recovery.py` and `tests/test_second_post_review_model_role_control_validation.py` provide complementary voice/provider/role, invalid restart recovery and control-character cases. No non-existent runtime setting is claimed; path existence remains a readiness/preflight concern.
- **Qualification:** Test matrix head `d897fa3b9050bd7d897edc9edd35a84cda9a6fd4` passed exact-head [CI #2818](https://github.com/ekkus93/deeper-dive/actions/runs/38368028102). Consumer test `b571dcf34990722e386b22373daedb595c404f74` initially failed only Ruff formatting; formatting correction `fa5f9fcd40760919d0318548808af32d830354e1` passed exact-head [CI #2820](https://github.com/ekkus93/deeper-dive/actions/runs/38371633155), quality job `115209776155` (**1,878 passed**, Ruff/mypy/build) and fresh-machine job `115209775885` (installed-wheel and KittenTTS gate passed).
- **Disposition:** The narrowly scoped SPR-400 network/runtime/voice-default consumer-validation checkbox is reconciled; broader cross-surface CLI mutation, complete error/canary matrices, baseline reproducer dispositions, independent review and SPR-910 remain **unchecked**. The user guide now explicitly distinguishes bounded UI worker ownership from adapter calls that cannot be forcibly cancelled. This reconciliation/documentation commit must itself pass new exact-head CI before the new checkbox is counted as qualified.

### 2026-10-13 SPR-04 normalization-boundary control-byte regression (partial)

- **Production validation:** `src/deeper_dive/user_config.py::UserConfig.validate_defaults` rejects ASCII terminal controls before whitespace/case normalization for eight recognized semantic default keys (research modes, Quick duration/host presets, local-only/network policy, diagnostics and speech setup). Path defaults now check the original raw string before trimming, preventing a trailing CR/LF from silently disappearing. Existing model-role, provider/voice and local-provider-ID validation remains in force; unknown legacy extension values retain their prior semantics.
- **Regression coverage:** `tests/test_second_post_review_default_control_matrix.py` parameterizes all eight normalized keys across six control bytes and both edge positions, plus both runtime paths, mutable Pydantic config revalidation, byte-for-byte rejection rollback and printable/legacy compatibility. This is bounded direct-model/store evidence, **not** full first-run/CLI/TUI cross-surface or restart acceptance.
- **Qualified exact-head CI:** Source commits `8c456a86b6c3e6cb1d85b789a9d4683d22fb497b` and formatting correction `009ae237492e305fe9cce03b89943f085cb43a49`; regression commit `39ae524d78194d35fbdf813bc63afb5dd48c75d2` passed [CI #2833](https://github.com/ekkus93/deeper-dive/actions/runs/38383351289), quality job `115248964630` and fresh-machine job `115248964243` both successful. The intermediate unformatted source commit failed Ruff format and is **not** qualification evidence.
- **Scope:** No broad SPR-400, SPR-600, SPR-800 or SPR-910 checkbox is claimed. This documentation-only reconciliation must independently pass exact-head CI before counting its evidence as final.


### 2026-10-13 SPR-06 cross-surface credential preservation and SPR-800 user guide reconciliation

- **SPR-06 credential regression contract (reconciled):** Production sanitizer `src/deeper_dive/diagnostics.py` preserves contextual status while redacting Basic, Token, Digest, and Bearer authorization forms; URL credential queries/fragments/userinfo; sensitive nested lists, tuples, mappings; chained exception text; and unquoted punctuated keys such as `client.secret`, `api[key]`, `api/key`, and `refresh+token`. The updated candidate-key regex avoids swallowing nonsecret outer `body=` wrappers around sensitive nested `api_key=` assignments. Exact production changes: `b7914758a4a776b38f5b09d0f5299fcfa7057df2` and `828f42d3ebb01ff0ca8ab2acebe31946175a8723`; preceding Ruff correction `fe19f1363f76d988829a2c35e008a99cf961fff0`.
- **Reproducible test/sink evidence:** `tests/test_second_post_review_nested_secret_container_redaction.py::test_all_authorization_schemes_are_scrubbed_before_log_or_export`, `test_stringified_nested_secret_list_in_chained_exception_log_and_bundle`, `test_tuple_header_chained_cli_exception_and_diagnostic_bundle`, `test_textual_provider_error_redacts_tuple_header`, and `test_unquoted_punctuated_secret_keys_are_redacted_in_every_diagnostic_sink`; `tests/test_diagnostics.py::test_provider_error_sanitization_covers_sdk_exception_shapes`, `test_redact_covers_assignment_forms_and_credential_bearing_urls`; plus `tests/test_second_post_review_security_cross_surface.py`. These cover real diagnostic logging/export, CLI and Textual errors, credential canaries and preservation of nonsensitive context.
- **SPR-800 user documentation (reconciled):** `docs/GUIDED_WORKFLOW_USER_GUIDE.md` documents Back/Continue/Home/selector dirty Save/Discard/Cancel, host-profile vs. episode host-order durable saves and partial failure recovery, bounded provider readiness and retry limitations, typed Settings validation/config conflicts, and immutable generated episode revisions. `README.md` links that guide. Both were updated at `28a3eac0baa635d06e315a9d9698186a3af45745` to reflect the actual fresh-install vs. returning-user Setup navigation policy in `GuidedDeeperDiveApp.on_ready`.
- **Related SPR-04/06 partial progress, not separate completion credit:** `UserConfig.validate_defaults` now rejects unsafe extension-key names without rejecting legacy multiline extension *values*; the formerly strict-xfail direct model tests are normal passing assertions. `tests/test_user_config.py` verifies invalid mutable Pydantic provider/default candidates cannot overwrite durable config bytes. Related commits `122de026a071ba74fee13c66cc9fa2b287b85caa` and `e05d211f72fdf0844cd3e414f81538ea55beaef7` (with Ruff follow-up `cf80851f59e946dd6db736b68c2db793aa63297d`). Full SPR-04 and SPR-06 cross-surface matrices remain unchecked.
- **Exact-head CI qualification:** direct-`master` combined source/docs head `28a3eac0baa635d06e315a9d9698186a3af45745` passed [CI #38399285246](https://github.com/ekkus93/deeper-dive/actions/runs/38399285246), quality job [115302435289](https://github.com/ekkus93/deeper-dive/actions/runs/38399285246/job/115302435289) and fresh-machine/installed-wheel job [115302435494](https://github.com/ekkus93/deeper-dive/actions/runs/38399285246/job/115302435494) both successful. **This checklist-only reconciliation commit still requires its own successful exact-head CI**; do not count the two new checkmarks as finally qualified before that passes. SPR-000/100/300/400/600 remaining items and SPR-700/800/900/910 open items are not implicitly closed.


### 2026-10-13 SPR-03 readiness adapter transport timeout qualification

- **Source/behavior:** `FirstRunReadinessCoordinator._probe_runtime` in `src/deeper_dive/guided_async_readiness.py` requests isolated readiness adapters through `ProviderController.readiness_probe_controller(request_timeout_seconds=min(self.timeout_seconds / 4, 1.0))` without mutating production registries. `ProviderFactory.build` applies `min(configured_timeout, probe_timeout_seconds)` to per-adapter HTTP timeouts and disables OpenAI LLM readiness retries. Ollama, llama-server, OpenAI LLM, OpenAI speech, ElevenLabs, and compatible TTS adapters pass their configured `_timeout` to the actual `urlopen(..., timeout=...)` path where they issue network requests. Static health/voice checks perform no network request where designed.
- **Deterministic tests:** `tests/test_provider_factory.py::test_readiness_factory_enforces_short_real_adapter_transport_budgets` builds all six HTTP adapter types without network calls, obtains the production and isolated readiness instances via the production `ProviderController`, asserts 45-second production settings versus 0.25-second readiness socket timeouts for every adapter, confirms persisted provider settings are unchanged, and proves OpenAI readiness requests disable retries. Existing `tests/test_second_post_review_readiness_budget.py` and `tests/test_second_post_review_readiness_publication.py` verify bounded in-flight workers, timeouts, stale result exclusion, callbacks, and recovery. Actual adapters pass their budget to urllib transport.
- **Limitation documented in `docs/GUIDED_WORKFLOW_USER_GUIDE.md`:** socket-operation timeouts are not absolute end-to-end deadlines and cannot kill blocked Python threads, DNS waits, or indefinitely streaming servers. Worker budget (two by default) bounds accumulation even when work cannot be interrupted; users can retry after a slot frees. Do not claim guaranteed hard cancellation.
- **Exact-head source/test CI:** direct `master` test commit `2e82df4296e7329f90e5a0235a4f00c0c2cf85ca` passed [CI #38403224637](https://github.com/ekkus93/deeper-dive/actions/runs/38403224637), including quality and installed-wheel/fresh-machine jobs. This checklist plus guide edit requires **its own new exact-head CI** before the SPR-03 checkbox is finally accepted. The remaining SPR-03 readiness-display/retry checklist item remains unchecked pending its independent full acceptance matrix.


### 2026-10-13 SPR-03 readiness status and SPR-07 actionable historical-episode lifecycle (reconciled)

- **SPR-300 sanitized readiness and deterministic retry:** `src/deeper_dive/guided_async_readiness.py::FirstRunReadinessCoordinator` publishes bounded failed/checking/ready states and sanitizes provider exceptions before presentation; `src/deeper_dive/guided_first_run.py::GuidedFirstRunWizard._checking_text` exposes actionable error/retry status and `action_retry_readiness` invokes the same coordinator. `tests/test_second_post_review_readiness_status_pilot.py::test_textual_readiness_failure_checking_retry_ready` uses a real Textual pilot and injected fake provider failure containing a Bearer credential canary plus benign status context. It checks canary absence in the coordinator message and rendered Needs attention, Checking, and Ready states, explicit Retry button, second probe, and eventual ready status. Additional worker/callback/timeout isolation is exercised by `tests/test_second_post_review_readiness_budget.py` and `tests/test_second_post_review_readiness_publication.py`.
- **SPR-700 actionable edit UX:** `src/deeper_dive/episode_config.py::EpisodeConfigurationService.edit` rejects a meaningful change to a frozen/historical episode with actionable guidance to create a new episode; `src/deeper_dive/guided_episode_wizard.py::GuidedEpisodeWizard.action_save_episode` preserves typed input and shows the sanitized guidance, and the CLI returns a safe nonzero status. `tests/test_second_post_review_tui_episode_lifecycle.py::test_completed_episode_tui_edit_requires_new_episode_without_mutating_artifacts` verifies both TUI and CLI, unaltered bytes and production identities, and an independent second project. `tests/test_second_post_review_tui_lifecycle_acceptance.py::test_completed_run_library_review_export_duplicate_and_project_isolation` verifies the Library's explicit draft-copy alternative without rewriting completed history.
- **SPR-700 run-state, restart and identity tests:** `tests/test_second_post_review_episode_lifecycle.py::test_non_draft_episode_edit_cannot_demote_state_or_delete_plan` covers planned/running/paused/failed/completed states; `test_durable_run_freezes_legacy_draft_episode_configuration` and `test_restarted_historical_run_is_immutable_while_sibling_draft_remains_editable` cover pending/running/paused/failed/completed/cancelled generation histories across reopened SQLite clients and unaffected sibling episodes. The two production-boundary TUI tests above preserve transcript/audio/export bytes, plans, run IDs, and separate-project data.
- **Exact-head source/test qualification:** direct `master` commit `270e35609ec5ee3783afafebd538142b18dc9254` passed [CI #38444447397](https://github.com/ekkus93/deeper-dive/actions/runs/38444447397): quality job `115459060857` (**2,061 passed**, Ruff, mypy, packaging) and fresh-machine job `115459060277` (installed-wheel guided acceptance and real KittenTTS CPU smoke) both succeeded. This documentation-only reconciliation commit **also requires its own exact-head CI pass** before the newly checked items are finally qualified.
- **Explicit limits:** The baseline reproduction/disposition ledger, complete SPR-100/400/600/700 matrices, independent review, regression requalification and SPR-910 final signoff remain open. The evidence above does not establish completion of adjacent unchecked items.


### 2026-10-13 SPR-01 shared guided dirty-form behavior — qualified evidence reconciliation

- **Scope/production boundary:** This batch reconciles 12 existing SPR-100 behavior contracts whose production wiring and Textual acceptance tests were already present on qualified `master`. It does not claim the full SPR-01 protocol/matrix, historical baseline reproduction, or final signoff. The shared `src/deeper_dive/wizard_shell.py::WizardShell` implements `_FORM_FIELDS`, `_editable_snapshot`, `_schedule_form_baseline`, `_current_form_dirty`, `action_back`, `action_continue`, `request_external_navigation`, `_request_dirty_transition`, three-way confirmation, typed `WizardSaveResult` outcomes, fail-closed save/transition, and durable-form discard. `src/deeper_dive/guided_app.py::GuidedDeeperDiveApp.action_navigate` guards global transitions. `src/deeper_dive/guided_first_run.py::GuidedFirstRunWizard._save_dirty_step` and `src/deeper_dive/guided_episode_wizard.py::GuidedEpisodeWizard._save_dirty_step` delegate through production provider, settings, project/source/research, host, episode configuration and planner services; partial failures retain the unresolved inputs. `src/deeper_dive/guided_host_wizard.py` preserves the selected host identity, handles picker reselect confirmation and restores durable host order on discard; `src/deeper_dive/guided_episode_wizard.py` protects segment reselect, custom-duration input and screen resume. The source picker only reloads source details, not the independent unsaved import fields. `src/deeper_dive/guided_draft.py::GuidedDraftStore.save` serializes only step/navigation state and durable IDs, not pasted source text, provider credentials, or unsaved business fields.
- **Deterministic production/Textual acceptance:** `tests/test_second_post_review_dirty_navigation.py` covers dirty episode Back/Continue/save/discard; global navigation; first-run provider/model/speech/voice-defaults; partial source import retaining unsuccessful input; dirty episode resume; async readiness recovery; host profile/order and selector guards; plan-segment selection, edit/regeneration/generation/preflight guards; double-submit; historical-episode validation failure; and host/episode stale-writer preserving typed values. Named tests include `test_dirty_episode_back_requires_explicit_discard`, `test_dirty_episode_save_and_back_persists_before_transition`, `test_dirty_wizard_global_navigation_uses_same_confirmation`, `test_first_run_dirty_guard_covers_each_editable_stage`, `test_partial_file_import_retains_unresolved_input_on_save_exit`, `test_dirty_episode_screen_resume_preserves_typed_values`, `test_dirty_host_profile_blocks_picker_reselection_until_discard`, `test_dirty_plan_segment_blocks_reselection_until_explicit_discard`, `test_async_readiness_recovery_preserves_unsaved_setup_edits`, `test_combined_host_profile_and_membership_save_is_durable_and_single_shot`, `test_duplicate_save_confirmation_cannot_create_or_navigate_twice`, `test_escape_dirty_confirmation_cancels_transition_without_losing_edits`, `test_concurrent_episode_update_cannot_be_overwritten_by_stale_guided_form`, and `test_concurrent_host_edit_rejects_stale_guided_profile_and_preserves_input`. The `test_guided_noop_save_keeps_exact_non_minute_duration_and_plan` fixture proves an unchanged displayed custom-duration value does not round and invalidate a durable plan.
- **Prior exact-head qualification:** all the listed paths and tests were present in direct-`master` source head `037698de44cdfe3ee19f48f9487add94ed5e5f21`, qualified by [CI #38452127599](https://github.com/ekkus93/deeper-dive/actions/runs/38452127599): quality job [115485423778](https://github.com/ekkus93/deeper-dive/actions/runs/38452127599/job/115485423778) (**2,078 passed**; Ruff, mypy and wheel/sdist build) and fresh-machine/installed-wheel job [115485423868](https://github.com/ekkus93/deeper-dive/actions/runs/38452127599/job/115485423868) both successful. **The checklist-only reconciliation head still requires its own exact-head CI pass before these checked items count as finally qualified.**
- **Explicit non-claims:** The comprehensive typed form identity/semantic snapshot protocol, full selector/custom-duration/restart qualification matrix, all filesystem-failure injection, clean-navigation matrix and focused SPR-01 run signoff remain unchecked, as do all other unqualified TODO items. Do not infer historical reproduction or SPR-900/910 final signoff from current green tests.


### 2026-10-13 SPR-01 focused dirty-navigation matrix and reusable acceptance fixtures (reconciled)

- **Production contract completed by the preceding qualified source heads:** `src/deeper_dive/wizard_shell.py` clean navigation and shared dirty confirmation; `src/deeper_dive/guided_episode_wizard.py` custom-duration, plan selector and normal durable episode Save; `src/deeper_dive/guided_host_wizard.py::GuidedHostWizard.action_save_host_order` now compares the originally displayed host order with the latest durable order before calling `EpisodeConfigurationService.edit`, whose `EpisodeConfigurationRepository.update` atomically CAS-checks the config JSON and its associated host membership. Changed external host order results in a safe actionable message without changing unsaved selection. Earlier version `75a33f78dcbb59daf00622cc92008a79deb15b1f` exposed a generic status in the new host-order regression, repaired by `ff0eb07371470b87438e16963934968371a6f00a` (qualified [CI #38458426192](https://github.com/ekkus93/deeper-dive/actions/runs/38458426192)).
- **Focused SPR-01 acceptance evidence:** `tests/test_second_post_review_dirty_navigation.py` reuses a single `_episode_fixture` production service setup across host/profile/order, plan, navigation and lifecycle tests. `test_hidden_custom_duration_edits_are_guarded_across_back_and_explicit_discard` checks the otherwise hidden custom-duration input survives Back/Cancel and explicit Discard restores the persisted exact-second value. `test_failed_episode_storage_write_keeps_dirty_fields_and_current_target` injects an `OSError` through `EpisodeConfigurationService.edit`, verifies the original target, typed text, durable bytes and selection are retained, then exercises a successful production retry. `test_stale_guided_host_order_does_not_replace_other_editor_membership` proves a separate production writer wins and the stale wizard never silently replaces its ordered IDs, then verifies a deliberate reload/save. `test_clean_first_run_back_continue_and_escape_do_not_request_discard` verifies clean Welcome → System Check → Welcome → Save/Exit without unnecessary confirmation. `test_switching_source_details_never_replaces_unsaved_import_fields` switches production source detail records while preserving the separate unsaved source import fields. Earlier `test_dirty_plan_segment_blocks_reselection_until_explicit_discard`, `test_dirty_episode_screen_resume_preserves_typed_values`, `test_host_order_survives_unrelated_refresh_and_app_restart`, `test_duplicate_save_confirmation_cannot_create_or_navigate_twice`, `test_escape_dirty_confirmation_cancels_transition_without_losing_edits`, `test_dirty_episode_save_and_back_persists_before_transition`, and `test_completed_episode_edit_guides_user_to_create_new_episode_without_plan_loss` complete the enumerated navigation/failure matrix.
- **Shared production fixture evidence for SPR-800:** `tests/conftest.py::completed_episode_acceptance`, `two_project_completed_acceptance` and `second_post_review_acceptance` create real projects, sources, hosts, fake LLM/TTS provider configuration, Quick episode configuration, `EpisodePlannerService` plan, `GenerationStartService` run, transcript turns, exported audio/metadata, pending generation, and separate-project immutable artifact identities through production services without direct repository-row seeding. `tests/test_second_post_review_tui_lifecycle_acceptance.py` and `tests/test_second_post_review_tui_episode_lifecycle.py` reuse these fixtures for Textual Episode Library, transcript review/export/duplicate, historical editing, and CLI configure rejection. This checks fixture reuse; it does not declare the entire SPR-700 cross-surface acceptance matrix or all SPR-800 preserved features complete.
- **Exact-head qualification:** source and test head `a376e2a8140ad28f3db17e2c5b09d4371ad40a65` passed [CI #38459294477](https://github.com/ekkus93/deeper-dive/actions/runs/38459294477) with quality job [115509995235](https://github.com/ekkus93/deeper-dive/actions/runs/38459294477/job/115509995235) (**2,083 passed**, Ruff format/lint, mypy, wheel/sdist) and fresh-machine/installed-wheel job [115509994901](https://github.com/ekkus93/deeper-dive/actions/runs/38459294477/job/115509994901). **This new documentation reconciliation commit also requires its own exact-head CI pass before the additional five checkmarks count as finally qualified.**
- **Remaining open:** The SPR-01 typed identity/semantic snapshot protocol is not implemented as a complete shared typed contract and stays unchecked. SPR-000 historical reproduction, SPR-400/600 extended cross-surface matrices, SPR-700 cross-surface acceptance signoff, SPR-800 remaining feature regressions, independent SPR-900 review, and SPR-910 final certification remain open.


### 2026-10-14 SPR closeout: baseline evidence, cross-surface matrices, audit, and final qualification

- **Historical baseline:** reviewed source SHA `ce5eee194b7adcce4f077b04e7f9cdb1d7f7de5b` was checked in detached worktree `/tmp/deeper-dive-spr-baseline-ce5`; no task branch was created. Current regression pilots copied into that worktree failed before the fixes: `test_dirty_episode_back_requires_explicit_discard` replaced the dirty episode step without confirmation; `test_unsaved_host_order_is_dirty_and_save_exit_persists_order` treated in-memory host ordering as clean; `test_first_run_dirty_guard_covers_each_editable_stage` let Back leave dirty provider setup; `test_dirty_plan_segment_blocks_reselection_until_explicit_discard` reselected a segment without guarding edits. The current fragment provider model accepted credential-bearing endpoint fragments, and `redact()` retained the synthetic fragment canary. Baseline scripts also confirmed the fixed `config.json.tmp` symlink overwrote its target, two stale store instances silently lost the first writer's update, and eight successive blocking readiness fingerprints left eight live readiness worker threads. `test_invalid_research_defaults_are_rejected[research_policy]` failed on that baseline because invalid research mode was accepted. These are reproducible historical failures, not claims of production data loss.
- **Dispositions:** `test_switching_source_details_never_replaces_unsaved_import_fields` passed on the reviewed baseline; the detail selector is separate from the unsaved source-import fields. SPR-07 no-op plan deletion and completed-episode demotion are disproved on the production service path by `test_noop_episode_edit_preserves_plan_segment_and_episode_identity` and `test_non_draft_episode_edit_cannot_demote_state_or_delete_plan`. The episode metadata-only edit case is N/A: all current editable `EpisodeConfiguration.snapshot()` fields are planner inputs, and the schema has no independent editable, non-plan-affecting metadata. The global `UserConfig.defaults` CLI write path is N/A: `command.py` has provider inspection/discovery/health commands and project/source/research/host/episode mutation commands, but no user-global-defaults mutation command. Actual Settings, provider-controller, first-run and store mutation paths are covered by production boundary tests; no fictitious CLI writer was added.
- **SPR-100 typed snapshot:** `WizardDirtyFormSnapshot` records wizard kind/step, target and baseline identities, durable raw baseline, displayed raw controls, semantic projection, and original pending destination. `test_shared_typed_dirty_snapshot_carries_target_values_and_intended_destination` verifies raw-vs-normalized dirty comparison, identity drift, and the intended destination; `test_dirty_navigation_names_the_destination_in_confirmation` covers user-visible destination. Architecture wording describes the destination and target-drift protections without claiming that every concrete selection handler uses one shared immutable target token.
- **SPR-400/600/700 coverage:** `test_v1_defaults_good_bad_blank_restart_and_single_write` is the table-driven defaults acceptance/rollback matrix; the full `test_second_post_review_config_security.py`, `test_second_post_review_security_cross_surface.py`, and `test_second_post_review_fragment_matrix.py` suites cover mutated models, URL/query/fragment encodings, nested diagnostic bundles, persisted bytes, CLI bootstrap and literal Textual provider status. The added fragment surface pilots are `test_fragment_canary_is_not_rendered_by_provider_screen` and `test_invalid_fragment_canary_is_not_echoed_by_cli_bootstrap`. The added shared fixture acceptance `test_quick_cli_and_guided_surfaces_share_historical_episode_policy` checks Quick creation, CLI rejection, Guided TUI rejection, project/episode/plan/run identity, and transcript/audio preservation. Existing `test_second_post_review_episode_lifecycle.py`, `test_second_post_review_tui_lifecycle_acceptance.py`, `test_second_post_review_cli_lifecycle_acceptance.py`, and `test_second_post_review_tui_episode_lifecycle.py` exercise lifecycle consistency, restart, preflight/export/library and isolation.
- **SPR-800 preservation:** the full suite includes the existing PRR sanitization/credential, draft/checkpoint/resume, research precedence/readiness, host clear/confirmation/settings atomicity, first-run/New Deep Dive, Quick generation/preflight/monitor/transcript/repair/playback/export, CLI workflows, provider routing, run-state and multi-episode isolation regression suites. The suite was run as a whole rather than inferred from the presence of individual test files.
- **Independent second-pass review:** traced `UserConfigStore.validate_candidate/save` through `ProviderController._commit_candidate` and Settings/default writers; inspected URL validators and recursive sanitizers; reviewed readiness generation/fingerprint checks, timer/worker ownership, shutdown, and stale completion handling; traced dirty snapshot and save/discard handlers into host/plan/source selection and production saves; reviewed `EpisodeConfigurationService.edit` and its immediate SQLite CAS/invalidation transaction. Reviewed broad catches at the provider-worker boundary (sanitized and callback-preserving), temporary-file cleanup (re-raises the original exception), and Textual dispatch boundary (closes on rejected pump message). The test matrix covers keyboard focus, Escape/Cancel, double submit, screen resume and failed persistence. No new high- or critical-severity defect was found. Documented residual constraints: Python cannot forcibly terminate an uninterruptible adapter call, so worker capacity remains bounded and timed-out workers retain their slots until they return; non-POSIX config locking is process-local; the config parent directory remains a same-user trusted boundary. These are documented limitations, not unbounded growth or silent overwrite paths.
- **Local full qualification:** `./scripts/check.sh` on the implementation/test working tree passed Ruff format over 435 files, Ruff lint, strict mypy over 123 source files, and **2,088 passed** in the complete pytest suite (no skips/xfails reported), in 581.85 seconds. `git diff --check` passed. The focused SPR-01/04/06/07 matrices are included in this complete suite.
- **Exact implementation/test-head qualification:** direct `master` implementation/test commit `5553bf68d5200274db4d552916d84938c49b76a1` passed [CI run 38490936001](https://github.com/ekkus93/deeper-dive/actions/runs/38490936001): quality job [115615684929](https://github.com/ekkus93/deeper-dive/actions/runs/38490936001/job/115615684929) passed lock validation, Ruff format/lint, strict mypy, **2,088 pytest tests**, source/wheel build and CLI/import smoke; fresh-machine job [115615684692](https://github.com/ekkus93/deeper-dive/actions/runs/38490936001/job/115615684692) passed clean wheel installation, CLI/TUI launch, installed-wheel production/guided/remediation acceptance and KittenTTS Micro CPU smoke. Both required jobs passed on the exact SHA. This final TODO/architecture reconciliation is a documentation-only commit and must also pass a new exact-head CI run before the cycle is complete.
