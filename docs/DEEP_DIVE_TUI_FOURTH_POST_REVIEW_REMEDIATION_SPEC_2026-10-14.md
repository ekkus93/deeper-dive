# Deeper Dive TUI — Fourth Post-Review Remediation Specification

**Created:** 2026-10-14 (America/Los_Angeles)  
**Status:** Not started  
**Reviewed `master` baseline:** `4ede40e` (module split of `wizard_shell`, `guided_first_run`, `guided_episode_wizard`, `guided_host_wizard` and two test files; line references below are valid against this commit)  
**Companion authoritative implementation checklist:** `docs/DEEP_DIVE_TUI_FOURTH_POST_REVIEW_REMEDIATION_TODO_2026-10-14.md`  
**Predecessor (historical, do not rewrite checked state):** `docs/DEEP_DIVE_TUI_THIRD_POST_REVIEW_REMEDIATION_TODO_2026-10-13.md` and its spec  
**CI at baseline:** run 38674826121 on `4ede40e` **failed** — `quality` passed, `fresh-machine` failed because `.github/workflows/ci.yml` still named the pre-split `tests/test_second_post_review_dirty_navigation.py`. Last green exact-head CI: run 38650789774 on `d29524d`.

## 1. Executive summary

A read-only review of the completed third post-review cycle (every item ticked; full local suite 2,260 passed on `4ede40e`) was carried out by three independent reviewers who traced production code without the implementer's conclusions. The `4ede40e` module split was verified to be behavior-preserving (every attribute resolved through each concrete wizard's MRO is identical before and after; no new `on_*` handler duplication). The review nevertheless found defects inside ticked items: three app crashes, one durable-config corruption path, an approval that can approve an unseen plan, a duplicate active generation run, several sanitizer leaks, and a stale evidence ledger.

| ID | Priority | Status | Topic | Main production surface |
| --- | --- | --- | --- | --- |
| FPR-01 | High | Reproduced | Discarding a preset change leaves `setup-ai-choice` stale; Save Provider then rewrites the durable provider with the wrong adapter | `guided_first_run.py`, `guided_first_run_form.py`, `wizard_transitions.py` |
| FPR-02 | High | Reproduced (real clicks) | Legacy Episode Plan screen crashes on Regenerate Plan / Regenerate Segment / Save Segment errors | `episode_plan_screen.py` |
| FPR-03 | High | Reproduced | Guided resume crashes when the stored episode audience is free text | `guided_episode_form.py` |
| FPR-04 | Medium | Reproduced (seeded) | Fail-closed discard without a baseline crashes on `allow_blank=False` Selects | `wizard_shell.py` |
| FPR-05 | Medium | Reproduced | Executing a host-select (and plan-select) transition after the target vanished crashes | `guided_host_wizard.py`, `guided_episode_wizard.py`, `guided_first_run.py` |
| FPR-06 | Medium | Reproduced (DB level) | A second active generation run can be created while a cancel-requested run is still running | `storage/run_repositories.py` |
| FPR-07 | Medium | Reproduced (service level) | Approval approves whatever plan is stored, not the plan the user reviewed | `episode_planner.py`, `storage/episode_plan_repository.py`, `episode_plan_screen.py` |
| FPR-08 | Medium | Reproduced | Sanitizer leaks and over-redaction | `diagnostics.py` |
| FPR-09 | Medium | Reproduced (seeded) | First-run Back after an external config change shows a false dirty state; Discard restores stale values | `wizard_shell.py`, `guided_first_run.py` |
| FPR-10 | Low | Source-verified | Picker changes under an open prompt silently replace the pending transition | `guided_host_wizard.py`, `guided_episode_wizard.py` |
| FPR-11 | Low | Reproduced | Discard on the "dirty prior wizard" prompt during Resume never resumes the draft | `guided_app.py` |
| FPR-12 | Low | Source-verified | Save on a profile-scoped host prompt also saves membership/order without saying so | `guided_episode_wizard.py`, `wizard_transitions.py` |
| FPR-13 | Low | Source-verified | Swallowed or narrow error handling: `_refresh_plan`, setup-screen planning step, host-order load on resume | `guided_episode_form.py`, `episode_setup_screen.py`, `guided_episode_wizard.py`, `guided_host_support.py` |
| FPR-14 | Low | Reproduced (hook) | `regenerate_segment` / `edit_segment` can persist stale segments under a newer config | `episode_planner.py` |
| FPR-15 | Low | Source-verified | Readiness build failures are never surfaced; capability and error-message gaps | `provider_tui.py`, `provider_factory.py`, `guided_readiness.py` |
| FPR-16 | Low | Reproduced | Config lock re-entrancy keyed on an unresolved path deadlocks on aliases; handle leak if unlock raises | `user_config.py` |
| FPR-17 | Low | Source-verified | Episode configuration normalization gaps and stale no-op return | `episode_config.py` |
| FPR-18 | Medium (quality) | — | Tests that missed the above: seeded "pilots", non-discriminating race tests, sanitizer canary gaps, weak assertions | `tests/` |
| FPR-19 | Low (design) | — | Repeated `on_mount` dispatch and scattered baseline bookkeeping | `wizard_shell.py` and guided wizards |
| FPR-20 | Process | — | Fix the broken CI path, reconcile the third-cycle ledger and docs, re-qualify at head | `.github/workflows/ci.yml`, third-cycle TODO, `docs/ARCHITECTURE.md` |

**Mandatory distinction:** "Reproduced" means a reviewer's throwaway test demonstrated the failure; those tests were not committed and must be rewritten as permanent regression tests. "Source-verified" means the defect follows from reading the code; the first task for each is a deterministic reproducer that fails on the baseline. If a reproducer disproves a finding, record the evidence and a narrowly justified N/A rather than deleting the task.

## 2. Governing execution contract

- Work on current `master`; reload this spec, the TODO, `master` head and CI at session start and after each commit. Do not duplicate landed work.
- Direct-`master` commits, one task per commit with the task ID in the message, no `Co-Authored-By` trailers; push after `./scripts/check.sh` exits 0 with an `N passed` line.
- **Exact-head CI is part of done.** `./scripts/check.sh` does not run the `fresh-machine` job; any change that renames, moves or deletes a test file must update `.github/workflows/ci.yml` in the same commit, and the commit is not complete until its CI run is green.
- Write a failing regression test first, at the highest practical boundary. For wizard defects this means a Textual pilot that reaches the state through real key presses/clicks (`tests/guided_pilot.py`), not by assigning `context.state` or calling `action_*` directly, unless the TODO records why real input cannot reach it.
- **Sweep sibling call sites.** Each fix must grep for the same pattern elsewhere (other screens, other `Select` assignments, other actions) and either fix or explicitly list them as out of scope with a reason. Two FPR items (02, 05) exist only because the third cycle fixed the reported site and not its siblings.
- Preserve production boundaries: `WizardShell`, `ProviderController`, `UserConfigStore`, `EpisodeConfigurationService`, `EpisodePlannerService`, `GenerationStartService`, `GenerationRunRepository`, `FirstRunReadinessCoordinator`, `GuidedDraftStore`.
- Artificial canaries and fake providers only; no network, credentials or hardware.
- Do not change checked state in the third-cycle TODO; FPR-20 adds dated annotations and ledger corrections only.

## 3. FPR-01 — Stale AI choice after discarding a preset change corrupts the provider

### Defect
`#setup-ai-choice` lives on the `ai-provider` step; the provider fields it pre-fills live on `provider-config`. TPR-08 captures the provider-field baseline before the preset is applied (`guided_first_run_form.py:296-315`), so Discard on `provider-config` restores the fields — but the AI choice is in no `_FORM_FIELDS` entry for `provider-config` and is not restored. `_selected_llm_adapter()` (`guided_first_run_form.py:366-372`) derives the adapter from the choice, so the form is now internally inconsistent.

Reproduced: durable provider `local` = Ollama → choose OpenAI → Continue → Back → **Discard** (fields show Ollama, choice still `openai`) → Continue (form looks clean) → **Save Provider** → `local` is persisted as `provider_type=openai` with the Ollama base URL.

Secondary: when a stored baseline exists but differs from the widgets, `_capture_preset_baseline` returns without adding the step to `_preset_baseline_steps` (`guided_first_run_form.py:307-308`); `action_continue` (`guided_first_run.py:278-279`) then adopts the preset as the clean baseline — the original TPR-08 defect on that path.

### Required behavior
1. Discard of a preset-dirtied `provider-config` restores the AI choice that corresponds to the durable provider (or, equivalently, the adapter used by Save is derived from durable/restored state, never from a stale choice). Choose one design and document it.
2. Save Provider must refuse (visible status, durable bytes unchanged) if the selected choice and the provider fields disagree on adapter type.
3. `_capture_preset_baseline` must never let a preset become the clean baseline on any path.

### Acceptance
Real-input pilot reproducing the scenario above: after Discard → Continue → Save Provider, the durable config is byte-identical to before; the AI choice shows the durable adapter. Variant for the secondary path.

## 4. FPR-02 — Legacy Episode Plan screen crashes

### Defect
`EpisodePlanScreen.action_regenerate_plan` and `action_regenerate_segment` (`episode_plan_screen.py:144-160`) have no exception handling. With a generation run present, Regenerate raises `ValueError("plan is frozen…")` and the app exits with return code 1 (reproduced with real clicks). Provider errors and the TPR-12 revision-CAS `ValueError` have the same effect. `action_save_segment` (`:122-135`) catches only `ValueError`; `KeyError` (plan removed by a concurrent edit), `IndexError` and `sqlite3.Error` crash it.

### Required behavior
All mutating plan-screen actions (save, regenerate plan, regenerate segment, approve) catch the same error set as the guided equivalents (`KeyError`, `ValueError`, `RuntimeError`, `OSError`, `sqlite3.Error`, typed episode errors), show sanitized guidance, keep the screen and its current plan view, and leave durable state unchanged. Sweep every other legacy `tui.py` screen action that calls a planner/config/run service for the same gap.

### Acceptance
Real-click pilots: frozen-plan regenerate (plan and segment), provider failure, plan deleted between load and save → app alive, sanitized status, durable plan unchanged.

## 5. FPR-03 — Guided resume crashes on a free-text audience

### Defect
`_load_episode_form` assigns `Select.value = config.audience` unguarded (`guided_episode_form.py:74`). The guided Select offers only `general`/`technical`/`expert`, but the CLI (`--audience`) and the legacy Episode Setup screen accept free text. Resuming a guided draft whose episode audience is e.g. "college students" raises `InvalidSelectValueError` on mount, Continue, Back and screen resume.

### Required behavior
1. Every hydration of a `Select` from stored data uses the guarded `_assign_select` (or an equivalent that adds the stored value as an option). Audit all raw `Select.value =` assignments in `src/deeper_dive/guided_*.py` and `wizard_shell*.py`; list each with its disposition.
2. Decide the policy for a stored value the guided form cannot represent: either show it as an extra option ("Custom: college students") so a no-op save preserves it, or show BLANK with a status and never overwrite the durable value unless the user saves. The policy must not silently rewrite the durable value.

### Acceptance
Pilot: create an episode via the service with a free-text audience, save a guided draft at that episode, start a fresh app, Resume → app alive, value preserved per the chosen policy, Save without edits leaves the durable audience unchanged.

## 6. FPR-04 — Fail-closed discard crashes on non-blank Selects

### Defect
TPR-09's `_clear_editable_fields` (`wizard_shell.py:501-503`) sets `Select.BLANK` on every `_FORM_FIELDS` Select, including `allow_blank=False` ones (project, research, episode, speech, voice-defaults steps), which raises `InvalidSelectValueError`. The TPR-09 test only covers the Inputs-only sources step. Reachable when a step is left before its scheduled baseline is recorded (first-run Back only schedules one).

### Required behavior
Fail-closed discard first reloads durable state for the step where a loader exists; otherwise it clears Inputs and resets non-blank Selects to their first/default option via the guarded helper. It never raises and never adopts the current unsaved values. The missing-baseline diagnostic is asserted by a test.

### Acceptance
Parametrized test over every `_FORM_FIELDS` step with the baseline removed → Discard → no exception, no unsaved value retained, diagnostic status present.

## 7. FPR-05 — Executing a select transition after the target vanished crashes

### Defect
Revert paths use `_assign_select`, but the paths that execute the confirmed transition assign raw: `guided_host_wizard.py:269` (host select), `guided_episode_wizard.py:294` (plan segment select), `guided_first_run.py:353` (speech choice). Reproduced for hosts: edit host A, pick host B (prompt), delete B from another surface, choose "Save host then select…" → `action_save_host` refreshes options, `picker.value = B` raises and the app exits.

### Required behavior
Transition execution uses the guarded helper; if the destination no longer exists, the save still completes, the picker stays on the saved target, and a status says the selected item is no longer available.

### Acceptance
Pilot for the host case through real input plus a service-level delete; deterministic test for the plan and speech paths.

## 8. FPR-06 — Second active generation run

### Defect
`GenerationRunRepository.select_or_create` (`storage/run_repositories.py:80-87`) inspects only the latest run (`ORDER BY modified_at DESC LIMIT 1`) and treats a `running` run with `cancel_requested=1` as inactive. Cancellation is honored only at a stage boundary (`pipeline.py:216`), so Generate pressed after Cancel inserts a new `pending` run while the old one is still running (reproduced: rows `r1 running cancel=1`, `r2 pending`). Both runs then share episode-keyed state such as `conversation_states`.

### Required behavior
Inside the existing `BEGIN IMMEDIATE`, refuse to create a run while **any** run for the episode is `pending` or `running`, regardless of `cancel_requested`; surface "the previous run is still stopping" through the start service and both UIs. `docs/ARCHITECTURE.md` "refuses a second active run" must then be true as written.

### Acceptance
SQLite test with a cancel-requested running row → start refused, no new row; once the old run reaches a terminal state, start succeeds. Thread test: concurrent starts still yield exactly one run.

## 9. FPR-07 — Approval approves a plan the user did not review

### Defect
`approve_plan(episode_id)` approves whatever plan is stored; the CAS covers only the config revision (`episode_planner.py:156-188`, `episode_plan_repository.py:84-86`). If another surface regenerates P1 → P2 under the same config while the plan screen shows P1, Approve approves P2; the screen then replaces `self.plan` and reports success. The third-cycle TODO also claims the update is `WHERE id=? AND status='draft'`; the code uses `WHERE id=? AND episode_id=?`, so re-approval of an approved plan succeeds.

### Required behavior
1. Approval takes the plan ID (and optionally its content digest) the user reviewed and fails with a typed conflict if the stored plan differs; both legacy and guided callers pass it.
2. Decide whether re-approving an approved plan is a no-op success or an error; implement `status='draft'` in the CAS if it is an error, and make docs match.

### Acceptance
Service test: load P1, regenerate to P2, approve with P1's ID → conflict, P2 still draft. Pilot on the legacy plan screen showing the sanitized conflict.

## 10. FPR-08 — Sanitizer leaks and over-redaction

### Defects (all reproduced against `redact()` at `4ede40e`)
| Case | Input | Output |
| --- | --- | --- |
| Empty username userinfo | `redis://:CANARY9x@localhost:6379/0` | unchanged |
| `@` in password | `https://user:p@CANARY9x@host/x` | `https://[REDACTED]@CANARY9x@host/x` |
| `/` in password | `postgresql://app:ab/CANARY9x+e==@db:5432/x` | unchanged |
| Encoded separators, non-http scheme | `wss://h/p?token%3DCANARY9x` | unchanged |
| Custom-scheme OAuth fragment | `myapp://cb#code=CANARY9x` | unchanged |
| Unclosed quoted Authorization (also produced by the length cap) | `{"authorization": "Basic CANARY9x` | unchanged |
| `)` in fragment value | `https://h/cb#access_token=ab)CANARY9x` | `#[REDACTED])CANARY9x` |
| Comma swallowed (TPR-19.4 spec says `,` is a delimiter) | `see https://h/x#access_token=C, then` | `see https://h/x#[REDACTED] then` |
| Benign anchor over-redacted | `…/Headers/Authorization#credentials`, `?lang=en&code=python` | redacted |
| Lower priority | `'Ocp-Apim-Subscription-Key': 'C'`; `password: correct horse C` (only first word redacted) | partial leak |

Locations: `_CREDENTIAL_URL` (`diagnostics.py:64`), the http(s)-only partial-decode and fragment passes (`:68`, `:391`), `_FRAGMENT_BODY` (`:78`), `_AUTH_QUOTED` (`:30`), key classification via `parse_qsl(keep_blank_values=True)` (`:231-235`).

### Required behavior
1. Userinfo redaction covers empty usernames and passwords containing `@`/`/` (split on the **last** `@` before the host, as `urlsplit` does).
2. Partial-decode and fragment-key redaction apply to every scheme matched by the URL tokenizer, not only http(s).
3. An unterminated quoted Authorization value is redacted to the end of the line/input.
4. Fragment values stop at the documented delimiters including `,`; `)` handling is decided and tested (prefer redacting to the next delimiter that is not inside the value).
5. A bare fragment/query key with no `=` is not treated as a secret.
6. All patterns stay linear; extend the performance test to the new shapes at the input cap.

### Acceptance
Canary matrix test with every row above; benign corpus (MDN-style anchors, `?code=python`, prose with commas) unchanged; timing test at the cap.

## 11. FPR-09 — False dirty state after an external config change

### Defect
After a step's baseline is recorded, an external change (e.g. speech provider changed on the Providers screen) followed by `on_screen_resume` re-hydrates the widgets. On Back to that step, `_schedule_form_baseline` refuses to re-baseline because a different baseline exists (`wizard_shell.py:370-371`), and `GuidedFirstRunWizard.action_back` (`guided_first_run.py:282-287`) only schedules. The step is dirty with no user edits, and Discard writes the stale old values into the widgets as the new baseline.

### Required behavior
App-initiated re-hydration from durable state replaces the baseline for steps that were clean before the re-hydration, and preserves (does not overwrite) steps that had unsaved edits. Back uses the same synchronous baseline timing in first-run and New Deep Dive.

### Acceptance
Real-input pilot: save speech → Continue → change the speech provider through the Providers screen → return → Back → no prompt, values show the new durable config.

## 12. FPR-10 — Picker changes under an open prompt replace the pending transition

### Defect
With a Back/Continue prompt open, a host-picker (`guided_host_wizard.py:124-147`) or plan-picker (`guided_episode_wizard.py:252-262`) change calls `_request_dirty_transition` again, replacing the user's pending transition and its discard scope. The speech-choice handler already guards this (`guided_first_run.py:323`).

### Required behavior
While a confirmation is pending, picker changes are reverted via the guarded helper and ignored (or the pickers are disabled, matching TPR-07 for buttons).

### Acceptance
Pilot: open a Back prompt, change the host picker, choose Discard → the executed transition is Back with Back's scope.

## 13. FPR-11 — Resume swallowed after discarding a dirty prior wizard

### Defect
`_surface_dirty_prior_wizard` re-enters `action_navigate("resume")` after Discard, and the guard at `guided_app.py:142-143` returns early, leaving the user on the discarded wizard; the draft is never resumed.

### Required behavior
After Save or Discard on that prompt, the original destination (`new` or `resume`) is executed exactly once.

### Acceptance
Pilot for both destinations × Save/Discard.

## 14. FPR-12 — Profile-scoped host Save is not scoped

### Defect
Discard on a profile-scoped host prompt keeps order edits (TPR-06), but Save (`guided_episode_wizard.py:77-98`) also saves membership/order and can create an episode. The prompt label "Save host then select…" does not say so.

### Required behavior
Either scope Save to the profile like Discard, or label the prompt with exactly what Save persists. Document the choice in the user guide.

## 15. FPR-13 — Swallowed or narrow error handling

- `_refresh_plan` swallows planning-service construction errors (`guided_episode_form.py:105-108`); an existing plan shows as "No plan loaded". Show a sanitized status instead.
- The legacy setup screen's planning step (`episode_setup_screen.py:142-152`) catches only `KeyError`/`ValueError`/`RuntimeError`; `sqlite3.OperationalError` ("database is locked") from `build_plan`'s `BEGIN IMMEDIATE` crashes the app.
- `on_screen_resume` clears `_selected_host_ids` before `_load_episode_host_order` (`guided_episode_wizard.py:210`, `guided_host_support.py:36-43`); a load failure leaves an empty order and re-baselines it, contradicting "keeps the current order". Keep the previous order on failure.

Acceptance: one deterministic test per bullet using service-boundary fault injection (`tests/fault_injection.py` or a failing database), not wizard-method monkeypatches.

## 16. FPR-14 — Stale segments persisted under a newer config

### Defect
In `regenerate_segment` / `edit_segment`, `load_plan` runs before `_snapshot`, and `_require_plan_matches_revision` passes when no plan exists (`episode_planner.py:104-108, 226-229`). An edit landing between the two deletes the plan; the operation then persists the old segments with the new digest and `evaluate_episode_plan` reports them usable (reproduced with a hook; window is microseconds).

### Required behavior
Read the config snapshot first, then load the plan, and fail with a typed conflict if the plan is missing or its digest does not match the snapshot.

## 17. FPR-15 — Readiness build failures and capability gaps

- `ProviderBuildResult.build_failures` is never consumed: `readiness_probe_controller` discards it (`provider_tui.py:254-261`); a failed provider just looks "not ready". Surface the sanitized reason in the readiness view.
- Only `ProviderConfigurationError` is caught per provider (`provider_factory.py:185`); other constructor `ValueError`s still fail the whole build.
- `_normalized_type` interpolates the user-supplied provider type via `{value!r}` (`provider_factory.py:233`) against the module's "never echo" rule.
- `supports_probe_timeouts` is inherited by subclasses that override `build()` without the `probe_timeout_seconds` keyword; such a subclass fails the whole probe. Check the signature or require explicit opt-in.
- `docs/ARCHITECTURE.md` probe bound: the deadline starts after `config()` and `build()`, and one lookup can issue both `health()` and `models()`; state the bound accurately.

## 18. FPR-16 — Config lock path aliasing

`UserConfigStore._locked` keys re-entrancy on `path.absolute()` (`user_config.py:573`), which does not resolve `..` or symlinks: nesting `_locked()` for `d/config.json` inside `d/sub/../config.json` on one thread deadlocks (reproduced). Key on `path.resolve()` (or the opened file's `(st_dev, st_ino)`). Also ensure the descriptor is closed even if `LOCK_UN` raises (`:590`). Add a cross-thread exclusion test (thread A holds nested, thread B waits) and an alias test under a timeout.

## 19. FPR-17 — Normalization gaps

`EpisodeConfiguration.normalized` (`episode_config.py:53-77`) does not normalize `source_overrides`/`model_overrides`, does not strip non-blank `research_overrides` values, and raises `AttributeError` (not `ValueError`) for `focus=None`. `edit()` re-reads the episode for the no-op comparison (`:126`) and can return a stale revision. Extend the table test.

## 20. FPR-18 — Test quality

1. Regression tests for FPR-01, 03, 04 and 05 must use real input through `tests/guided_pilot.py`.
2. Make `guided_pilot` honest: `reach_hosts` calls `app._first_run_readiness.close()` and `app.action_navigate("new")` (`tests/guided_pilot.py:63-66`), and the restart test calls `action_navigate("resume")`. Replace with key presses/clicks or document each exception in the helper docstring.
3. The TPR-04 approval race test is not discriminating (the hook's edit deletes the plan, so the plan-ID rowcount alone fails approval). Add a variant where the plan survives (e.g. a revision bump that keeps the plan) so the revision CAS is the only guard.
4. Add an edit-after-preflight test that goes through `GenerationStartService.start()`.
5. Replace TPR-03 "concurrent writer" cases that patch `edit()` to raise with a real concurrent edit.
6. Assert that a raising readiness subscriber's log entry is sanitized (TPR-14).
7. Fix weak assertions: `test_typed_host_edit_blocks_reselect_until_discarded` (`name.value != durable_name` is trivially true after switching hosts — assert host A's stored name is unchanged); `test_third_post_review_real_input_flow.py` "discard_is_scoped" checks no scope and asserts `open_project(...) is not None`; fix the restart test's "move it up" comment.
8. Replace fixed `pilot.pause(0.3)` waits where an event/condition wait is possible; document the button debounce where it is not.

## 21. FPR-19 — Design follow-ups (decide, then fix or document)

- `on_mount` still multi-dispatches through the MRO: on the episode wizard `WizardShell.on_mount` runs five times and `_load_project_form` four times, and base-class bodies run after the subclass set its baseline. Make `on_mount` single-dispatch like the button/select handlers (TPR-18 found the same class of bug), or document why repeated execution is idempotent and test it.
- Baseline bookkeeping is spread across `_schedule_form_baseline`, `_remember_current_form`, the host profile/order variants and `_capture_preset_baseline`, with different sync/async timing per wizard. Consolidate to one API or document the invariants in `docs/ARCHITECTURE.md`.
- Status messages show raw widget IDs (e.g. "setup-host1-voice"); map them to field labels.
- The project step button still says "Create Project" in edit mode (TPR-11).
- Create Host's idempotence signature blocks a deliberate later create of an identical host; scope it to the double-submit window.

## 22. FPR-20 — Process, CI and documentation reconciliation

1. **CI:** update `.github/workflows/ci.yml` `fresh-machine` to the three `test_second_post_review_dirty_navigation_part{1,2,3}.py` files; verify every test path in the workflow exists; get a green exact-head run.
2. **Third-cycle TODO** (annotations and ledger corrections only, no unchecking):
   - Header still says `**Status:** Not started`.
   - Ledger TPR-16 says "aggregate budget documented, not enforced" (enforced by `3bc5929`); TPR-17 and TPR-18 rows say "partial" although every box is ticked; rows omit `50eeef5` (TPR-10), `fad174b`, `b89c9a3`, `4ecd7cf`, `e7364d1` (TPR-17), `6c80ed0`, `eaecdc2`, `d29524d` (TPR-18) and the new test files.
   - TPR-910 qualified `6d6d1a6`; four later commits changed production code (`3bc5929`, `50eeef5`, `e7364d1`, `4ede40e`) without recorded re-qualification, and `4ede40e`'s CI failed.
   - Add a dated "Post-closeout review 2026-10-14" note pointing to this spec for each contradicted item (TPR-01, 02, 03, 04, 08, 09, 12, 16, 19.4, 19.5, 600, 700).
   - Correct overstated claims: TPR-04 `status='draft'`; TPR-600 "navigates only through real key presses/clicks"; TPR-700's statement about what `ARCHITECTURE.md` says.
3. **`docs/ARCHITECTURE.md`:** remove "TPR-17 … remains open" (`:203-204`); make "refuses a second active run" (`:201`) true via FPR-06; qualify "the UI thread never waits on a writer" (many UI paths still call the locked `config()`); fix the probe-bound wording (FPR-15).
4. Historical docs that cite pre-split test paths (`DEEP_DIVE_TUI_GUIDED_WORKFLOW_TODO_2026-10-08.md`, `DEEP_DIVE_SECOND_POST_REVIEW_CONSUMER_INVENTORY_2026-10-12.md`) get a one-line note mapping old → new paths; do not rewrite them.
5. Final qualification at the exact head: `uv lock --check`, ruff format/lint, mypy, full pytest count, `uv build`, fresh-venv wheel smoke, green CI (both jobs) with run/job IDs.
