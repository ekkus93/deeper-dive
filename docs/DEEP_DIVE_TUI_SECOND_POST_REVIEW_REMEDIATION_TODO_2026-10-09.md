# Deeper Dive TUI — Second Post-Review Remediation TODO

**Created:** 2026-10-09 (America/Los_Angeles)  
**Status:** In progress / partial remediation CI-qualified  
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

- [ ] Reload current `master`, both documents, previous completed PRR checklist/spec and exact last qualified CI; record exact head and competing work.
- [ ] Inventory all relevant guided navigation, refresh/reselection, checkpoint, provider configuration, readiness, episode edit and plan consumers.
- [ ] Build a reusable deterministic fixture with two projects, indexed sources, fake LLM/TTS, research policy, hosts, episodes, plan, transcript turns, audio artifacts, completed and incomplete runs.
- [ ] Capture production-store identity and byte snapshots for config, draft, episode, host order, plan, runs and exports.
- [ ] SPR-01: prove/disprove unsaved episode form edits lost via Back/Continue and subsequent production rehydration.
- [ ] SPR-01: prove/disprove unsaved provider/source/research/plan/host edits lost via navigation, reselection, screen resume or automatic refresh.
- [ ] SPR-02: prove/disprove unsaved ordered host ID changes bypass dirty Save and Exit.
- [ ] SPR-03: demonstrate timed-out blocking probe still occupies a daemon worker and quantify repeated retry worker growth.
- [ ] SPR-04: demonstrate accepted invalid research/preset/network/default input and its downstream failure.
- [ ] SPR-05: reproduce fixed-temp-path collision/concurrent lost update and exercise temp-path symlink/failure-injection in an isolated fixture.
- [ ] SPR-06: demonstrate fragment credential acceptance and diagnostic credential disclosure using fake canaries.
- [ ] SPR-07: test no-op episode edit plan deletion and editing completed episode's state; check guards that may rule out actual production reachability.
- [ ] Record findings as confirmed, disproved, or needs-design with exact test/source evidence; do not conflate risk with a demonstrated incident.

## SPR-100 — Shared dirty-form navigation and save contract (SPR-01)

- [ ] Specify typed dirty-form protocol: target identity, durable baseline, displayed control values, semantic snapshot and original destination.
- [ ] Preserve snapshot baselines across first hydration, async updates, tab/back transitions and explicit production saves.
- [ ] Detect unsaved fields in both first-run and New Deep Dive, including hidden custom-duration and plan segment edits.
- [ ] Intercept Back and Continue before a dirty form's editable values are replaced.
- [ ] Intercept global Home/Projects navigation, new/resume, wizard completion and other screen transitions that would discard unsaved edits.
- [ ] Protect host/plan/source entity reselection from overwriting edits in the previously selected record.
- [ ] Prevent reload/resume/automatic service refresh from overwriting dirty input.
- [ ] Offer Save changes and continue, Discard changes and continue, and Cancel/keep editing with the intended destination displayed.
- [ ] Default-focus Cancel, preserve keyboard/assistive navigation, and make modal Escape cancel rather than discard.
- [ ] Route each Save through existing production services; return a typed save result instead of parsing status-message prefixes.
- [ ] On invalid input or service/fs failure, preserve current step, selected record and typed values.
- [ ] On discard, retain previously durable values and clear only unsaved edits, including sensitive fields.
- [ ] Ensure repeated Enter/click/key events do not save, discard or navigate twice.
- [ ] Clean Back/Continue/Escape remain frictionless when no edit is pending.
- [ ] Ensure wizard draft/checkpoint serialization still excludes provider secrets, pasted source bodies and unsaved business records.
- [ ] Add deterministic Textual navigation pilots for all first-run provider/model/speech/voice/default controls.
- [ ] Add deterministic Textual navigation pilots for project/source/research/host/episode/plan inputs.
- [ ] Add selector-switch, custom-duration, plan-segment and restart/resume tests with deliberate unsaved edits.
- [ ] Add validation failure, I/O failure, cancel, explicit discard, double-submit and successful save/continue tests.
- [ ] Run focused SPR-01 tests and exact-head CI, then record commit, test identifiers and CI evidence.

## SPR-200 — Durable guided host profile and ordered membership (SPR-02)

- [x] Distinguish pending host-profile edits from pending episode host membership/order edits.
- [ ] Compare `_selected_host_ids` and episode ID to last durable ordered membership in the shared dirty snapshot.
- [ ] Make add/remove/move dirty, no-op moves clean, and undo-to-original clean.
- [ ] Ensure Save and Exit/Continue saves both profile and order via production services when both are dirty.
- [x] Define transactional or explicit safely recoverable partial-save behavior for profile+order updates.
- [x] Prevent changing the host picker from overwriting a dirty host profile.
- [x] Reject duplicate, missing, or cross-project host IDs before commit.
- [x] Preserve pending order across unrelated refreshes and safely rehydrate persisted order on restart.
- [ ] Add Textual tests for add, remove, reorder, cancel, discard, save, restart and selected-host switch.
- [ ] Add mixed profile+order failure-injection, duplicate-click and multi-project/episode isolation tests.
- [ ] Run focused SPR-02 tests and exact-head CI, then record commit and CI evidence.

## SPR-300 — Bound readiness probes and preserve UI responsiveness (SPR-03)

- [x] Inventory every provider `health()`, `models()` and `voices()` path and actual adapter-level transport timeout/retry limits.
- [x] Define per-application worker budget and coalescing/supersession semantics; avoid one detached thread+timer per refresh.
- [ ] Implement bounded executor/in-flight worker ownership with safe app shutdown behavior.
- [x] Ensure an observed timeout does not publish late success or leave an unlimited retry backlog.
- [ ] Enforce actual provider I/O deadlines where possible, documenting uninterruptible adapter limitations.
- [x] Preserve generation/fingerprint stale-result exclusion and callbacks for coalesced refreshes.
- [x] Support a new configuration fingerprint while older work remains blocked without accumulating workers indefinitely.
- [ ] Keep keyboard navigation, Home and setup transitions responsive while never-returning fake probes are active.
- [ ] Preserve sanitized Checking/Ready/Needs attention displays and deterministic actionable retry.
- [ ] Preserve OpenAI and ElevenLabs duplicate-discovery call-count optimizations.
- [ ] Add 100-refresh coalescing stress test, repeated timeout/retry and shutdown test with observable active-worker upper bound.
- [ ] Add stale result/config-change, late-completion, callback-once, app-exit, provider exception and no-real-network tests.
- [ ] Run focused SPR-03 tests, installed-wheel Textual acceptance and exact-head CI; record evidence.

## SPR-400 — Typed semantic defaults and atomic validation (SPR-04)

- [ ] Inventory all keys in `UserConfig.defaults` and their readers/writers across first-run, Settings, provider controller, CLI, Quick, generation and preflight.
- [ ] Specify an authoritative typed/default-value schema with documented valid ranges, enums, aliases, optional blank semantics and legacy compatibility.
- [ ] Validate global and Quick research modes using the production `ResearchMode` contract.
- [ ] Validate Quick duration, exactly two valid host presets, and model/role/provider references where relevant.
- [ ] Validate network/local-only, runtime/diagnostic, path and voice/default values according to actual consumer contracts.
- [ ] Apply shared normalization/validation to composite Settings, first-run, provider defaults and CLI mutation paths.
- [ ] Validate every candidate in full before one durable write; never publish partial runtime changes.
- [ ] Keep old valid config files usable and explicitly handle invalid older config with safe recovery guidance.
- [ ] Ensure no rejected value or credential canary leaks in exception or CLI/TUI output.
- [ ] Add table-driven good/bad/blank/legacy/restart matrix and single-save/rollback assertions.
- [ ] Add integration test proving settings-accepted values are consumable by Quick Deep Dive without validation errors.
- [ ] Run focused SPR-04 tests and exact-head CI; record evidence.

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
- [ ] Revalidate mutated Pydantic configurations before save across TUI, CLI, first-run and provider controller.
- [x] Sanitize credential-like `#` fragments in diagnostic text while keeping ordinary context and harmless URLs intact.
- [ ] Preserve Basic/Token/Digest/Bearer, query, userinfo, recursive nested and chained-exception redaction.
- [ ] Test multiple URLs, encoded characters, casing variants and partial malformed strings using fake canaries.
- [ ] Inspect serialized config, nested diagnostics, exported bundles, CLI output and rendered Textual status for absence of canaries.
- [x] Verify user-facing validation errors do not echo rejected fragment or raw input.
- [ ] Run focused SPR-06 security matrix and exact-head CI; record evidence.

## SPR-700 — Episode lifecycle and plan invalidation (SPR-07)

- [ ] Reproduce or conclusively disprove no-op `EpisodeConfigurationService.edit()` deleting an existing plan.
- [ ] Reproduce or conclusively disprove completed episode edit demoting state to `draft` and determine actual UI/CLI reachability.
- [ ] Inventory every episode state, latest-run state, plan consumer, library listing, exporter, Quick and generation control path.
- [ ] Document lifecycle state machine and policy for edits in draft, planned, running, paused, failed and completed conditions.
- [ ] Define historical run/plan/artifact immutability and whether completed episode edits are prohibited, forked or revisioned.
- [ ] Compare canonical plan-relevant configuration fields and skip invalidation for exact no-op/non-plan-affecting edits.
- [x] Retain a usable plan and its identity on semantically identical episode saves.
- [ ] Invalidate only necessary editable draft plans on meaningful plan-affecting changes.
- [ ] Preserve completed/running episode and run status, existing transcript, audio and export identity.
- [ ] Prevent edits racing with generation start or planner write using transactional/versioned state checks.
- [ ] Keep TUI, CLI, library, plan display, export and preflight consistent with the lifecycle policy.
- [ ] Provide actionable UX when edit requires a new episode/revision.
- [ ] Add SQLite-level tests for same-config, metadata-only and plan-affecting updates.
- [ ] Add running/completed/failed/paused state, no-revision-confusion, restart and artifact-identity tests.
- [ ] Add multi-episode/project isolation and Quick-vs-guided-vs-CLI acceptance tests.
- [ ] Run focused SPR-07 matrix and exact-head CI; record evidence or justified N/A rationale.

## SPR-800 — Shared regression coverage and original feature preservation

- [ ] Preserve PRR-100/110/120 canonical sanitization, credential-env and cross-surface security tests.
- [ ] Preserve PRR-200/210 dirty Save/Exit, safe draft/checkpoint and stale resume behavior.
- [ ] Preserve PRR-300/310/320 research precedence, discovered non-default roles, async readiness and discovery optimization.
- [ ] Preserve PRR-400/410/420 host optional-clear, destructive confirmations and atomic multi-default saves.
- [ ] Preserve guided first-run and New Deep Dive end-to-end Textual acceptance and keyboard/compact-terminal UX.
- [ ] Preserve Quick EpisodePlannerService, production preflight, generation monitor, transcript, repair, playback and export.
- [ ] Preserve CLI research and episode workflows, provider routing, Kitten benchmark, multi-episode isolation and run-state control.
- [ ] Reuse fixtures rather than a separate bespoke mock for every surface; avoid new duplicate business logic.
- [ ] Run expanded security/redaction, dirty-form, concurrency, provider routing and generation/regression matrices.
- [ ] Update or add user documentation for guarded navigation, host-order saves, provider timeouts, settings errors and episode revision rules.
- [x] Update developer architecture notes about unique atomic config writes, worker budget and episode plan invalidation.

## SPR-900 — Independent second-pass code review and failure analysis

- [ ] Independently review each changed source path and trace call sites rather than trusting checked boxes.
- [ ] Examine every new exception handler for swallowed errors, unintended broad catches and credential exposure.
- [ ] Review races at worker publish, config swap, episode edit, source/host selection and wizard dirty-state transitions.
- [ ] Review keyboard navigation, focus, modal cancellations, duplicate submit, missing widgets and screen resume.
- [ ] Review data migrations/backward compatibility and file permission/symlink issues on supported platforms.
- [ ] Review changed test assertions for false positives and production-boundary bypasses.
- [ ] Document remaining risks and severity, add newly discovered actionable defects to this TODO and fix them before declaring full completion.
- [ ] Confirm no unresolved high/critical issues and justify all N/A dispositions with exact source/test evidence.

## SPR-910 — Final packaging, qualification and reconciliation

- [ ] Run `uv lock --check` against the final implementation head.
- [ ] Run Ruff format and lint gates.
- [ ] Run strict mypy against current production/test surfaces as configured.
- [ ] Run the full pytest suite; record exact count and no unexplained skip/xpass.
- [ ] Build source distribution and wheel from exact candidate `master`.
- [ ] Verify CLI import/help and command workflows from the installed wheel in a clean environment.
- [ ] Run installed-wheel guided Textual first-run/New Deep Dive/Quick acceptance using shared fake providers.
- [ ] Run installed-wheel configuration/security, dirty-navigation, host-order, readiness, episode lifecycle and concurrent-writer tests.
- [ ] Run real KittenTTS Micro CPU smoke under the existing fresh-machine gate where configured.
- [ ] Verify every confirmed baseline reproducer fails before fix and passes after fix; reconcile disconfirmed risks as justified N/A.
- [ ] Record all source/test references, head SHA, successful exact-head CI run and job IDs, and a consistent test count.
- [ ] Confirm implementation is on `master` with no per-task PRs or forgotten alternate branch changes.
- [ ] Reconcile this TODO in coherent batches only after implementation and its exact-head CI pass.
- [ ] If reconciliation changes only documentation, run new exact-head CI on the documentation commit too.
- [ ] Reload both documents from final `master` and confirm all tasks/subtasks accounted for and final head itself CI-qualified.
- [ ] Declare second remediation complete only after all evidence requirements are satisfied and no unqualified unchecked item remains.

## Evidence ledger

| Cluster | Production commits on master | Regression tests / reproduction | Exact-head CI | Status |
| --- | --- | --- | --- | --- |
| SPR-000 baseline | Pending | Pending | Pending | Open |
| SPR-01/02 wizard and host edits | `7999b7e2b3539db1d902ea95c1c2663dec7135b1` (discard restoration), `5ae6d9e9194b3c5a5ea447ad397c6dc2b467bc0c` (Ruff qualification); `f24f33000291b6c88431ccf078ecf84f38b97d47`, `7f3b0372e866802c2660a44a1b63d46998e37380`, `84f4230698f5dcbbcc433518bb21ad69051e2cd3`, `b2cc696cdbbeb4afc03b950cc6526947cb7047cd` (host membership/retry matrix) | `tests/test_second_post_review_dirty_navigation.py` and `tests/test_second_post_review_host_membership.py`: durable input and host membership/order are restored after explicit discard; blocked Continue and host reordering regressions, existing Textual dirty Back/Continue tests | [CI #2465](https://github.com/ekkus93/deeper-dive/actions/runs/38037448372), exact `5ae6d9e9194b3c5a5ea447ad397c6dc2b467bc0c` (both jobs passed); requalified in [CI #2467](https://github.com/ekkus93/deeper-dive/actions/runs/38037669064) ; [CI #2486](https://github.com/ekkus93/deeper-dive/actions/runs/38068815279), exact `b2cc696cdbbeb4afc03b950cc6526947cb7047cd` (quality `114261847806`, 1,207 passed; fresh-machine `114261847721` passed) | Partial; first-run, exhaustive all-surface selection and failure matrices remain open |
| SPR-03 readiness workers | `ee73733350b9afed05d3674f821d86589bb64813` (callback coalescing), `57fe0e992735c1674047211a5e72d539d4d9b16b` (shutdown tests), `b7e009c306d4c8597fa620043224e932972736fb`, `eff4eb7962581a7567f0bf93e9895aca134176f3` (reservation/timer supersession fix) | `tests/test_second_post_review_readiness_budget.py`: 100-refresh coalescing, bounded workers across fingerprints, late-timeout exclusion, shutdown callback suppression; `src/deeper_dive/guided_async_readiness.py`: cancelled orphan timers and released superseded reserved slots; deterministic supersession regression | [CI #2466](https://github.com/ekkus93/deeper-dive/actions/runs/38037509169), `57fe0e992735c1674047211a5e72d539d4d9b16b`, quality `114170931835`, fresh-machine `114170931767` (both passed); [CI #2494](https://github.com/ekkus93/deeper-dive/actions/runs/38071463889) exact `eff4eb7962581a7567f0bf93e9895aca134176f3`, 1,216 passed | Partial; transport deadlines, full adapter/UI matrix and installed-wheel readiness acceptance remain open |
| SPR-04/05/06 settings, persistence and URL security | `4f07c9ddc42ad5cfddba9e8d59d5da9a6adaa621` (pre-build validation), `0eef63453b5e0daa9d394b80c86e713e1c0c0cc5` (fragment redaction), `c47368fd8823203d69765f706a9f4aff665abbb2` (pre-replace chmod), `e1594f3a66854c879ddd728bb5b5c6b5428194d0` (expanded tests); `c93a6b1130f99f2c541e2b3d0f79dbc37a37b993`, `88b10be272e261947bbc5ed80c8c18fb334f28b1` (failure injection and same-key revision CAS) | `tests/test_second_post_review_config_durability.py`, `tests/test_second_post_review_config_security.py`, `tests/test_provider_tui.py`, `tests/test_second_post_review_config_failure_matrix.py`: semantic defaults, CAS conflicts, temp/failure atomicity, URL canaries, Quick settings round-trip and nested diagnostic export | [CI #2467](https://github.com/ekkus93/deeper-dive/actions/runs/38037669064), `e1594f3a66854c879ddd728bb5b5c6b5428194d0`, quality `114171399979` (1,186 passed), fresh-machine `114171399887` (passed); [CI #2491](https://github.com/ekkus93/deeper-dive/actions/runs/38069863354) exact `935124fb0c4ccc259f38e2001b50a9a10367784c`, 1,214 passed | Partial; cross-surface security, process-level writers and independent audit remain open |
| SPR-07 episode lifecycle | `4c56332737cb00e97ac5f3d96c1dc826fee2839f`, `8b04f819c42ecde2235ef78d7b819d0f79302076` (regression tests), `42942b64d83be6210b276e778c73a120a827c058`, `935124fb0c4ccc259f38e2001b50a9a10367784c` (shared acceptance test) | `tests/test_second_post_review_episode_lifecycle.py`: no-op plan/segment identity, draft plan invalidation/isolation, non-draft state preservation (7 cases); `tests/test_second_post_review_acceptance_matrix.py`: shared two-project completed/exported plus pending run, no-op plan, transcript/audio/run identity, pending edit rejection | [CI #2453](https://github.com/ekkus93/deeper-dive/actions/runs/38035568941), `8b04f819c42ecde2235ef78d7b819d0f79302076`, quality job `114165154083` (1,152 passed), fresh-machine job `114165153972` (passed); [CI #2491](https://github.com/ekkus93/deeper-dive/actions/runs/38069863354) exact `935124fb0c4ccc259f38e2001b50a9a10367784c` | Partial; exhaustive lifecycle state, planner race and CLI/TUI acceptance still open |
| SPR-800/900 regression and independent audit | Pending | Pending | Pending | Open |
| SPR-910 final reconciliation | Pending | Pending | Pending | Open |


### 2026-10-10 verified partial behavior and unresolved scope

- The SPR-05 concurrency policy uses a process-local `RLock`, POSIX advisory flock where supported, and revision/CAS conflicts on stale writes (including two simultaneous first-time writers). Conflicts require explicit reload/retry rather than silent overwrites. `_write_temporary()` uses secure unique files, flush/fsync, atomic replace, and directory sync; the parent directory is assumed owned/trusted by the current user. A post-replace directory-sync failure is an **uncertain durability outcome**: it must not be described as rolled back. `tests/test_second_post_review_config_durability.py` exercises stale disjoint and same-key writers, temp chmod/fsync failures, replace failures, symlink canaries, and post-replace errors.
- `ProviderController._commit_candidate()` validates mutable Pydantic config before building a runtime, `UserConfigStore.save()` revalidates again, and `ProviderConfig` rejects URL fragments without echoing their values. `diagnostics.redact()` redacts nested and repeatedly encoded sensitive URL fragments while retaining benign anchors. Original `tests/test_second_post_review_config_security.py` was restored in full rather than replaced; the additional durability suite is separate.
- Shared wizard discard now restores baseline `Input`/`Select` values and host membership from the durable episode service; a blocked Continue cannot convert unsaved values into a clean baseline. Additional modal, first-run, selector and failure-injection cases remain unchecked.
- Host-profile reselection is now guarded by the existing Save / Discard / Cancel flow: `tests/test_second_post_review_dirty_navigation.py::test_dirty_host_profile_blocks_picker_reselection_until_discard` verifies the picker, while `test_recommended_hosts_guard_unsaved_profile` (four parameterized cases) verifies that the recommended-host action cannot silently replace a dirty profile. Production paths: `src/deeper_dive/guided_host_wizard.py` (`on_select_changed`, `action_create_recommended_hosts`, `_execute_custom_transition`). Direct-`master` commits: `6b620a951c79842f0854089e3d80e682fffe4c0d`, `99cead7e1e23be0f3ced5550380bbf79d1a2208d`; exact-head [CI #2479](https://github.com/ekkus93/deeper-dive/actions/runs/38048005891), quality job `114201337624` (**1,196 passed**, Ruff/mypy/build/CLI smoke), fresh-machine job `114201337738` (installed-wheel guided acceptance and real KittenTTS Micro CPU smoke), both passed. This evidence supports only the checked picker safeguard, not the remaining SPR-01/02 matrix.
- An unrelated host-order refresh no longer removes unavailable host IDs from pending membership; direct-`master` commit `019d9baeebf90843e80ef42581bee4ca9c9d9145` and exact-head [CI #2477](https://github.com/ekkus93/deeper-dive/actions/runs/38040740289) (1,192 tests and fresh-machine gate passed). Full restart/isolation acceptance remains open.
- The nine marked subitems above are supported by code and regression tests included in exact-head [CI #2467](https://github.com/ekkus93/deeper-dive/actions/runs/38037669064) at `e1594f3a66854c879ddd728bb5b5c6b5428194d0` (quality `114171399979`, **1,186 passed**; fresh-machine `114171399887`, passed). They remain subject to final full-cycle requalification. The current documentation-only reconciliation must also pass its own exact-head CI before it is final evidence.


### 2026-10-10 host membership and partial-save acceptance

- Shared production `EpisodeConfigurationService._validate_hosts()` rejects duplicate, missing and foreign-project members on create/edit before changing persistent episode, plans or other episodes. `tests/test_second_post_review_host_membership.py` verifies three invalid membership cases for both create and edit, plan/segment and unrelated episode preservation, plus a Textual pilot proving the rejected order remains pending and dirty.
- Host profile and episode membership have independently tracked dirty baselines. The guided Save confirmation routes through `GuidedEpisodeWizard._save_dirty_step()`, which records a typed PARTIAL result if the profile saved but order persistence failed, without navigating away or marking order clean. A Textual failure-injection/retry pilot verifies profile durability, unchanged episode order after failure and successful explicit order retry.
- Host order refresh/restart qualification includes `tests/test_second_post_review_dirty_navigation.py::test_host_order_survives_unrelated_refresh_and_app_restart`, plus move/no-op/undo and independent service rehydration tests. The remaining complete SPR-01/02 acceptance matrix stays unchecked.
- Direct-`master` exact-head [CI #2486](https://github.com/ekkus93/deeper-dive/actions/runs/38068815279), `b2cc696cdbbeb4afc03b950cc6526947cb7047cd`: quality job `114261847806` (1,207 pytest passed, Ruff and mypy gates), fresh-machine job `114261847721` (passed). TODO-only reconciliation itself must pass exact-head CI before its evidence is final.


### 2026-10-10 config fault injection and shared lifecycle requalification

- SPR-05 production persistence validates/serializes before publication, uses unique same-directory temp files with POSIX owner-only permissions, fsyncs data and parent directory, and removes owned temps where the OS permits. The failure-matrix regressions inject temp creation, temp write, pre-replace permission and rename/fsync errors; byte-level JSON snapshots confirm no partial config was published before replace. Explicit failing-cleanup tests retain the original exception rather than reporting a successful unlink, which cannot be guaranteed under OS-denied cleanup.
- Config-path symlink and advisory-lock symlink canaries are rejected on supported POSIX platforms without modifying target bytes. Supported trust boundary is an owned/trusted config directory; these checks are **not** protection against a fully compromised same-UID process. Post-rename directory-fsync failure is an uncertain crash-durability outcome; tests verify the published revision is retained for an explicit subsequent save. The entire multiprocess and cross-platform fallback matrix remains open.
- Reused the existing `second_post_review_acceptance` fixture from `tests/conftest.py` (fake LLM/TTS, two completed projects/episodes with transcripts/audio/exports and one pending generation) in `tests/test_second_post_review_acceptance_matrix.py`, verifying no-op episode saves preserve plan and segment identities and completed run/artifact hashes, and pending-run config mutations are rejected without touching plan/run state. CLI/TUI and full historical lifecycle acceptance remain unchecked.
- Qualified direct-`master` source/test head `935124fb0c4ccc259f38e2001b50a9a10367784c` with [CI #2491](https://github.com/ekkus93/deeper-dive/actions/runs/38069863354): quality job `114264901749` (**1,214 passed**; Ruff/mypy/package), fresh-machine job `114264901877` (passed). The present TODO reconciliation requires a **new** exact-head CI success before its evidence is final.


### 2026-10-10 readiness worker supersession qualification

- `FirstRunReadinessCoordinator` now discards superseded timeout timers when changing fingerprint, including when all capacity is occupied and the current request must fail with actionable Retry. Generation-tagged callbacks already ignore stale completion/timeout messages. Each coordinator has a configurable `max_workers` bound (default 2), a no-queue policy and explicit active-worker accounting; a timed-out uninterruptible provider call cannot be forcibly killed, but cannot grow the worker budget indefinitely.
- Removed an unlocked post-reservation `view` check that could abandon a reserved generation without starting its thread or releasing capacity. The subsequent timer-install lock atomically verifies current generation and releases abandoned slots. The deterministic `test_supersession_between_reservation_and_view_read_never_leaks_slot` simulates the specific old race; `test_superseded_probe_timers_are_cancelled_without_unbounded_growth` checks old deadlines are immediately retired even when two workers remain blocked. Existing 100-refresh coalescing, late timeout, worker-capacity and app-close tests are retained.
- Direct `master` exact-head [CI #2494](https://github.com/ekkus93/deeper-dive/actions/runs/38071463889) at `eff4eb7962581a7567f0bf93e9895aca134176f3`: quality `114269554734` (1,216 pytest passed), fresh-machine `114269554658` (passed). Adapter-specific actual network transport deadlines, never-returning thread shutdown and exhaustive TUI/fresh-wheel readiness remain explicitly unchecked. Documentation reconciliation needs its own exact-head CI.

### 2026-10-10 independent controller-writer concurrency acceptance

- SPR-05 controller-level races are exercised through the real `SettingsController`, `ProviderController`, and `UserConfigStore` rather than simulated direct config-map edits. `tests/test_second_post_review_controller_writer_races.py::test_independent_settings_controllers_do_not_silently_clobber` uses a deterministic `Barrier` to force two independent controllers to load the same durable revision before competing to save. Both same-key and disjoint-key inputs must produce exactly one successful write and one explicit `UserConfigConflictError`, with no silent overwrite; an explicit reload/retry preserves the other writer's independent settings.
- `tests/test_second_post_review_controller_writer_races.py::test_provider_and_settings_controller_race_is_detected_and_recoverable` races a fake-provider registration against a separate Settings default save using the same barrier and store contract. Exactly one change wins before retry; after an intentional reload/retry both changes are durably present.
- Source/test commits direct to `master`: `4b9083196bfb20856d1454317fe46d37089ea188` (controller race tests) and `9e19e1254af456ff366eca7904c5af943e5b187a` (Ruff formatting). Exact-head requalification at `901fee672f7dd770bed1318e569317648178df8c`: [CI #2509](https://github.com/ekkus93/deeper-dive/actions/runs/38080468783), quality job `114296149570` (**1,231 passed**, Ruff format/lint, strict mypy, wheel/sdist build), fresh-machine job `114296149502` (passed). This supports only the two SPR-05 controller-writer items above; multiprocess concurrency, platform fallback, failure-injection breadth, and the final cycle gates remain unchecked. This reconciliation-only change itself requires another successful exact-head CI run.

### 2026-10-10 SPR-03 transport inventory and SPR-05 failure/fallback matrix

- SPR-03: `docs/DEEP_DIVE_READINESS_TRANSPORT_INVENTORY_2026-10-10.md` inventories first-run `health/models/voices` dispatch for fake, OpenAI, Ollama, llama-server, Kitten, OpenAI-compatible/OpenAI speech, and ElevenLabs adapters, plus the separate system-check probes. It distinguishes per-operation socket timeouts (configured up to 600 seconds) and OpenAI retry budgets from the eight-second UI timeout. Full readiness-specific network deadlines and worker retirement remain open.
- SPR-05: `tests/test_second_post_review_config_failure_matrix.py` and `tests/test_second_post_review_config_durability.py` cover injected temporary creation/write/chmod/flush/fsync/replace failures, cleanups, uncertain durability after directory fsync, permissions, canaries for old predictable-temp paths and config/advisory-lock symlinks, and deterministic same-key/disjoint-key concurrent writers. `tests/test_second_post_review_config_fsync_matrix.py` adds invalid/partial JSON and actual invalid UTF-8 restart rejection, stale-writer refusal against corrupted durable bytes, and the non-POSIX `fcntl=None` in-process lock fallback. Cross-process locking is **not** guaranteed in the non-POSIX fallback and must not be claimed.
- Qualified source/test heads: `51c90e1f8cdada6cb9a4831de5ff9a079320cf08` at [CI #2514](https://github.com/ekkus93/deeper-dive/actions/runs/38081858191), quality job `114300250855` (**1,238 passed**, Ruff/mypy/build), fresh-machine job `114300251070` passed; and actual-invalid-UTF8 fixture correction `adc123441d7ad646c16dc6396764fcf6a9a87e8e` at [CI #2515](https://github.com/ekkus93/deeper-dive/actions/runs/38082274462), quality job `114301465562` and fresh-machine job `114301465743`, both passed. Focused SPR-05 cases are included in the full exact-head pytest suite. This inventory/reconciliation documentation itself must pass new exact-head CI, and other SPR-05 baseline/closeout work remains open.

**Documentation creation is not remediation completion.** Creation/commit of this TODO and spec may be reported separately with its exact GitHub commit and documentation-only CI outcome; no unchecked implementation task becomes complete from that action alone.
