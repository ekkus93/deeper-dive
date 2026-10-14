# Deeper Dive TUI — Third Post-Review Remediation Specification

**Created:** 2026-10-13 (America/Los_Angeles)  
**Status:** Not started  
**Reviewed `master` baseline:** `57b23c9` (`origin/master`; production `src/` identical to `c7ba241`, so every line reference below is valid against either)  
**Companion authoritative implementation checklist:** `docs/DEEP_DIVE_TUI_THIRD_POST_REVIEW_REMEDIATION_TODO_2026-10-13.md`  
**Predecessor (historical, do not rewrite):** `docs/DEEP_DIVE_TUI_SECOND_POST_REVIEW_REMEDIATION_TODO_2026-10-09.md` and its spec  
**Previous qualified CI:** https://github.com/ekkus93/deeper-dive/actions/runs/38492780359 (2,088 tests; not qualification for changes proposed here)

## 1. Executive summary

A read-only code review of the completed second post-review cycle (all 145 items checked; full suite 2,088 passed locally) traced the production code directly rather than trusting the evidence ledger. It found defects that the checked items claim to cover, including two crash paths, one silent data-integrity path (stale approved plan), one duplicate-record path, a regular-expression denial-of-service in the diagnostic sanitizer, and a set of partially met contracts and weak tests. Several were reproduced with throwaway pilot tests; others are source-level findings that still require a deterministic reproducer.

| ID | Priority | Status | Topic | Main production surface |
| --- | --- | --- | --- | --- |
| TPR-01 | High | Reproduced | Discard after a saved voice vanishes crashes the app | `wizard_shell.py`, `guided_first_run.py` |
| TPR-02 | High | Reproduced | New Deep Dive after Save-and-Exit shows stale data, false dirty state, and Save creates a duplicate project | `guided_app.py`, `guided_episode_wizard.py`, `guided_new_deep_dive.py` |
| TPR-03 | Medium | Reproduced | Legacy Episode Setup crashes on frozen/concurrent episode edit | `episode_setup_screen.py` |
| TPR-04 | Medium | Reproduced | Plan approval can resurrect a stale plan against a newer configuration | `episode_planner.py`, `storage/episode_plan_repository.py` |
| TPR-05 | Medium | Source-verified | Readiness Retry is a silent no-op when the worker budget is saturated | `guided_async_readiness.py`, `guided_first_run.py` |
| TPR-06 | Medium | Source-verified | Discarding a host-profile prompt also discards pending host membership/order | `guided_host_wizard.py` |
| TPR-07 | Low–Medium | Source-verified | Host actions lack double-submit guards and remain active under an open Save/Discard prompt | `guided_host_wizard.py` |
| TPR-08 | Low–Medium | Reproduced | Changing the AI preset silently becomes the clean baseline | `guided_first_run.py`, `wizard_shell.py` |
| TPR-09 | Low–Medium | Source-verified | Discard with no recorded baseline adopts unsaved input (fail-open) | `wizard_shell.py` |
| TPR-10 | Low | Source-verified | Confirmation prompt omits the destination for host/plan selection transitions; duplicate label maps have drifted | `wizard_shell.py` |
| TPR-11 | Low | Source-verified | Project step edits after creation cannot be saved | `guided_new_deep_dive.py` |
| TPR-12 | Low | Source-verified | Generation-start, plan-build and guided-save read/write races | `generation_start.py`, `storage/run_repositories.py`, `episode_planner.py`, `guided_episode_wizard.py` |
| TPR-13 | Low | Source-verified | No-op episode comparison is not normalized across surfaces | `episode_config.py` |
| TPR-14 | Low | Source-verified | Readiness callback contract inconsistencies | `guided_async_readiness.py` |
| TPR-15 | Low | Source-verified | Readiness fingerprint performs locked disk I/O on the UI thread | `guided_async_readiness.py`, `user_config.py` |
| TPR-16 | Low | Source-verified | Readiness probe budget/robustness gaps | `provider_tui.py`, `guided_readiness.py` |
| TPR-17 | Medium (contract) | Partial implementation | Typed dirty-form protocol is a computed view, not a shared contract; subclasses bypass the baseline guard | `wizard_shell.py`, all guided wizards |
| TPR-18 | Medium (quality) | Partial implementation | Acceptance tests bypass real input and production failure boundaries | `tests/test_second_post_review_*` |
| TPR-19 | Medium (19.1) / Low | Reproduced / Source-verified | Sanitizer ReDoS, rejected-value echo, inconsistent normalization, fragment truncation, sanitizer gaps, lock re-entrancy | `diagnostics.py`, `quick_deep_dive.py`, `settings_screen.py`, `user_config.py` |
| TPR-20 | Process | — | Reconcile overstated second-cycle checklist items | second-cycle TODO |

**Mandatory distinction:** "Reproduced" means a throwaway pilot demonstrated the failure during review; those pilots were not committed and must be rewritten as permanent regression tests. "Source-verified" means the defect follows from reading the code but has not yet been demonstrated; the first task for each is a deterministic reproducer that fails on the baseline. If a reproducer disproves a finding, record the evidence and a narrowly justified N/A rather than deleting the task.

## 2. Governing execution contract

- Work on current `master`; reload this spec, the TODO, `master` head and CI at session start and after each commit. Do not duplicate landed work.
- Follow the existing repository workflow for GitHub/CI (Ralph Bridge, direct-`master` exact-head CAS writes, no per-task branches/PRs) unless the user directs otherwise.
- Write a failing regression test first for every finding, at the highest practical boundary (Textual pilot with real key presses/clicks, production service, or SQLite).
- Preserve production boundaries: `WizardShell`, `ProviderController`, `UserConfigStore`, `EpisodeConfigurationService`, `EpisodePlannerService`, `GenerationStartService`, `FirstRunReadinessCoordinator`, `GuidedDraftStore`. No parallel guided-only stacks.
- Use artificial canaries and fake providers only; no network, credentials or hardware.
- Do not rewrite checked items in the second-cycle TODO; TPR-20 adds dated annotations only.
- Record source references, test IDs, exact commit SHA and CI run/job IDs when reconciling.

## 3. TPR-01 — Discard after a vanished voice crashes the app

### Defect
First-run voice rediscovery sets the voice `Select` to `BLANK` when the saved voice is no longer offered, which marks the form dirty. On Back → **Discard**, `WizardShell._restore_discarded_form` (`wizard_shell.py:546-548`) assigns the durable baseline value (e.g. `"voice-b"`) directly to the `Select`. That value is no longer an option, so Textual raises `InvalidSelectValueError`, which is uncaught and terminates the app. The rediscovery path is in `guided_first_run.py` (around line 770).

### Required behavior
1. Restoring any `Select` from a baseline must check the value against the widget's current options. If the durable value is not offered, set `BLANK` (or the documented fallback), keep the durable config unchanged, and show a non-sensitive status naming the field that needs reselection.
2. The form after such a discard must be internally consistent: the dirty predicate must not immediately report dirty again in a way that traps the user in a loop. Define and document whether "durable value unavailable" counts as dirty.
3. Apply the same guarded restore everywhere a `Select` is set from stored data (host picker, plan segment picker, provider/model selects).

### Acceptance
Textual pilot: save voices → rediscover with one voice removed → Back → Discard → app still running, durable config bytes unchanged, status explains the missing voice. Repeat for a provider error during rediscovery and for voice reordering.

## 4. TPR-02 — New Deep Dive after Save-and-Exit: stale state, false dirty, duplicate project

### Defect
`GuidedDeeperDiveApp` resets `_new_context` for destination `"new"` (`guided_app.py:141-145`: `project_id`/`episode_id`/`run_id` → `None`, state → `project`) and pushes the existing `"new"` screen. `GuidedEpisodeWizard.on_screen_resume` (`guided_episode_wizard.py:207-216`) checks `_current_form_dirty()` first. Because the dirty snapshot includes target identity and the identity changed from the old project to `None`, it reports dirty and returns before reloading. The user sees the previous project's fields and host/source state, sees "Unsaved changes remain", and gets prompted on Back/Continue. Choosing **Save** runs `action_create_project` with `project_id=None` and creates a duplicate project from the stale fields.

### Required behavior
1. Starting a fresh New Deep Dive must reset the wizard instance's form state, baselines, baseline targets, selected host IDs, loaded episode/plan state and pending transitions *before* any dirty evaluation. Either push a fresh screen instance or provide an explicit `reset_for_new_context()` that the app calls.
2. A target-identity change caused by the app deliberately switching context must never count as user edits. Identity drift may only mark a form dirty when the user's own edits are still pending against the old target.
3. When a genuinely dirty form exists from the prior context, the app must prompt **before** resetting the context (Save / Discard / Cancel), naming the old target.
4. Resuming a saved draft (`restored is not None`) must load that draft's durable state, never stale widget contents.

### Acceptance
Pilot: complete or Save-and-Exit a project → Home → New Deep Dive → empty project form, no dirty prompt on Back/Continue, project count unchanged until the user creates one. Also: abandon flow; dirty prior context prompts before reset; resume-draft path loads the correct project.

## 5. TPR-03 — Legacy Episode Setup crashes on frozen or concurrent edits

### Defect
`EpisodeSetupScreen.action_build_plan` (`episode_setup_screen.py:125-132`) calls `service.create()` / `service.edit()` outside its `try` block. Since the second cycle, `EpisodeConfigurationService.edit` raises `ValueError` for a frozen (historical) episode or a concurrent configuration change. In Textual an unhandled action exception terminates the app. Both `tui.py` and `guided_app.py` reach this screen.

### Required behavior
1. Catch the same typed failures the guided wizard handles (`ValueError`, `KeyError`, persistence `OSError`/`sqlite3` errors as appropriate), show the sanitized actionable message (e.g. "create a new episode"), and keep the typed form values and `current_episode_id`.
2. Do not attempt planning after a failed edit.
3. Prefer a typed exception (e.g. `EpisodeFrozenError`, `EpisodeConfigurationConflict`) over `ValueError` string matching so every surface can render consistent guidance. Keep `ValueError` subclassing for backward compatibility.

### Acceptance
Pilot on the legacy setup screen: Build Plan → create run → edit title → Build Plan → app alive, status shows guidance, durable episode/plan/run unchanged. Same for a concurrent writer between load and save. Repeat via the `tui.py` app.

## 6. TPR-04 — Plan approval can resurrect a stale plan

### Defect
`EpisodePlannerService.approve_plan` (`episode_planner.py:146-150`) loads the plan and calls `_persist(plan, status="approved")` **without** `expected_episode_config_json`. The repository's version check (`storage/episode_plan_repository.py`, around line 65) is skipped. If the episode is edited between `load_plan` and `_persist`, the edit invalidates (deletes) the plan, and `replace` then re-inserts the old plan as *approved* against the new configuration. The review reproduced a stored plan with duration 600 and lead host h1 after the episode had been changed to 3000 and h2. `plan_validity.py` detects only the host mismatch, so stale duration or focus passes silently. This contradicts `docs/ARCHITECTURE.md` lines 189-191. Approval also deletes and re-inserts segments with new UUIDs, so segment identity changes on every approval.

### Required behavior
1. Approval must be a CAS operation: capture the episode configuration revision with the plan load (one read or one transaction) and pass it to `_persist`. If the revision changed or the plan no longer exists, fail with a typed conflict and do not insert.
2. Approval should update plan status in place (`UPDATE … WHERE id=? AND status='draft'`) rather than delete and re-insert, preserving plan and segment identity.
3. Persist the configuration revision (or a hash of `config.snapshot()`) with each plan so `plan_validity` can detect any stale-input plan, not just host mismatches.
4. Correct `ARCHITECTURE.md` if the final mechanism differs.

### Acceptance
SQLite-level test using a deterministic hook between load and persist: concurrent edit → approval fails, no plan row exists. Identity test: plan ID and segment IDs unchanged after approval. Validity test: plan built for old duration is reported stale after a duration-only edit.

## 7. TPR-05 — Readiness Retry is a silent no-op when workers are saturated

### Defect
In `FirstRunReadinessCoordinator.request` (`guided_async_readiness.py:199-204`), when the state is `failed`, the fingerprint is unchanged, and `len(_active_workers) >= max_workers`, the method returns `False` without updating the view or invoking callbacks. With `max_workers=2`, two consecutive timeouts for the same config (one automatic, one Retry) fill the budget. Further Retry presses (`guided_first_run.py:110-119`) do nothing, and the status still says "…retry". The "workers are still finishing" message appears only for a *different* fingerprint (`:210-219`). Nothing re-requests when a slot frees.

### Required behavior
1. When Retry cannot start because the budget is full, publish an explicit view/message (same wording family as `:213-218`) and fire the callback so the UI updates.
2. Choose and document one policy: (a) a single pending re-request that starts automatically when a slot frees (coalesced to the latest fingerprint, bounded to one), or (b) Retry disabled with a visible reason until a slot frees, then re-enabled via callback.
3. `request()` should return a typed outcome (started / coalesced / saturated / closed) rather than bare `bool`, so callers and tests can assert the reason.

### Acceptance
Coordinator test plus Textual pilot: two blocking timeouts → Retry press → visible saturated message (canary-free); release one worker → Retry works (or auto-retry fires exactly once). The existing assertion of 20 no-op `request()` calls must also assert the rendered message.

## 8. TPR-06 — Host-profile discard drops pending membership/order

### Defect
`GuidedHostWizard._restore_discarded_form` (`guided_host_wizard.py:269-279`) always clears `_selected_host_ids` and reloads order from the store, even when the prompt was triggered by a profile-only transition (host picker reselect, Create Host). Unsaved add/move/remove edits are lost. When no episode exists yet, `_load_episode_host_order` (`:557-558`) returns early, so `_selected_host_ids` becomes `[]` and every selected host is lost. `_load_episode_host_order` also silently swallows `KeyError`/`ValueError` (`:563-564`).

### Required behavior
1. Discard must restore only the dirty scope that triggered the prompt: profile-only transitions restore the profile; membership-scoped transitions restore order; leaving the step restores both. Show which scope will be discarded in the prompt.
2. With no episode, the membership baseline is the in-memory baseline captured at step entry, not "empty".
3. Replace silent swallowing with a visible, sanitized status and keep current in-memory order when the durable order cannot be loaded.

### Acceptance
Pilot: add/reorder hosts, edit profile, reselect host → Discard → profile reverted, order edits retained. No-episode variant retains selections. Leave-step Discard reverts both. Load failure shows status and keeps order.

## 9. TPR-07 — Host action double-submit and actions under an open prompt

### Defect
`action_create_host` (`guided_host_wizard.py:381`) has no in-flight guard; after a successful create the form is clean, so a repeated Enter/click creates another host. `save-host`, `select-host`, `host-up`/`host-down`, `remove`, `save-host-order` (`:326-343`, `:444-552`) do not check `_exit_confirmation_pending`, and those buttons are not disabled while the Save/Discard/Cancel prompt is visible. The user can mutate membership under an open prompt, which invalidates the prompt's premise.

### Required behavior
1. While a confirmation is pending, all mutating actions on the step are inert (disabled widgets and guarded handlers) except the three prompt buttons.
2. Mutating host actions are single-shot per user intent: an in-flight flag cleared on completion, plus idempotency for create (e.g. reject an identical create within the same interaction or require the form to change).

### Acceptance
Pilot with repeated key presses/clicks: one host created; membership unchanged while the prompt is open; normal operation after Cancel.

## 10. TPR-08 — AI preset change silently becomes the baseline

### Defect
`GuidedFirstRunWizard.on_select_changed` (`guided_first_run.py:349-359`) force-applies preset defaults when `setup-ai-choice` changes. `setup-ai-choice` is not in `_FORM_FIELDS`, so the change is not dirty. After `action_continue`, the wizard calls `_remember_current_form()` unconditionally (`:336`), adopting the OpenAI preset values as the clean baseline while the stored provider is still Ollama. Back/Escape then leave without a prompt and the user's choice is lost.

### Required behavior
1. Include the AI choice selector, and any field that `force=True` overwrites, in the dirty snapshot of the step it belongs to.
2. Baselines may only be recorded from durable state after a successful save or confirmed discard (see TPR-17). Remove unconditional `_remember_current_form()` calls after navigation in `guided_first_run.py` and `guided_episode_wizard.py` (reviewer cites `:205`, `:233`, `:242`) unless they are provably called on clean durable state.
3. Applying a preset over user-typed values must itself be a guarded transition when those values are dirty.

### Acceptance
Pilot: durable Ollama → select OpenAI preset → Continue → Back → prompt appears; Discard restores Ollama values; Save persists OpenAI. Typed custom base URL then preset change prompts before overwrite.

## 11. TPR-09 — Discard without a baseline is fail-open

### Defect
`WizardShell._restore_discarded_form` (`wizard_shell.py:531-549`) uses `self._form_baselines.get(step, ())`. If no baseline exists, it restores nothing and then calls `_remember_current_form()`, promoting the unsaved text (including pasted source bodies) to the baseline. This contradicts its docstring and SPR-100's "on discard, retain durable values and clear only unsaved edits, including sensitive fields".

### Required behavior
A missing baseline must fail closed: reload from the durable store for that step, or clear editable (especially sensitive) fields to empty. Never adopt current values. Log a non-sensitive diagnostic for the missing-baseline condition.

### Acceptance
Unit and pilot tests deleting the baseline before Discard: sensitive/source-body fields cleared or durable-reloaded, never retained; the form reads clean only when it equals durable state.

## 12. TPR-10 — Destination labels and duplicated label maps

### Defect
Transition labels exist in two maps (`wizard_shell.py:367-386` and `:593-631`) that have drifted. `host-select:<id>`, `plan-select:<id>` and `create-recommended-hosts` are in neither, so the prompt falls back to "leave this screen" / "Save changes and leave", which is misleading for in-place reselection. Transitions are string-encoded and parsed with `split`.

### Required behavior
Represent transitions as a typed value (e.g. a small dataclass or enum plus target ID) with a single label function. Every transition kind used anywhere in the guided app has an explicit, user-facing destination label, and a test asserts exhaustiveness.

### Acceptance
Parameterized test over every transition kind emitted by the wizards: label is specific and not the fallback. Pilot snapshots for host-select and plan-select prompts.

## 13. TPR-11 — Project step edits after creation are unsavable

### Defect
`guided_new_deep_dive.py:69-71` returns `False` with "Project already created." whenever `context.project_id` is set. A dirty project step after creation can therefore only be discarded; Save always fails, leaving the user in a prompt loop.

### Required behavior
Either support updating name/topic/audience through the production project service (preferred), or make the project fields read-only after creation with a visible explanation so they can never become dirty.

### Acceptance
Pilot: create project → Back → edit topic → Continue → Save persists the edit (or fields are read-only and no prompt appears).

## 14. TPR-12 — Generation-start, plan-build and guided-save races

### Defects
1. `EpisodePlannerService.build_plan` (`episode_planner.py:70-74`) loads the config and then reads the revision separately. An edit in between stores an old-config plan under the new revision.
2. `GenerationStartService.start` (`generation_start.py:107-115`) runs preflight, then `select_or_create_generation_run`, which reads the latest run and inserts in a separate plain `BEGIN` (`storage/run_repositories.py:43`) with no config-version or duplicate-pending check. Two concurrent starts can create two pending runs, and an edit can land between preflight and run creation.
3. `GuidedEpisodeWizard` checks for concurrent change (`guided_episode_wizard.py:343-347`) before `edit()` re-reads, leaving a narrow window. The repository CAS should be the sole authority.

### Required behavior
1. Read config and revision atomically (single row read) in `build_plan`.
2. Run creation uses `BEGIN IMMEDIATE`, re-checks the episode configuration revision captured at preflight, and refuses a second pending/running run for the same episode.
3. The guided save passes the loaded revision into the service, which enforces it inside the update transaction. The pre-check may remain for UX but is not the guard.

### Acceptance
Deterministic hook-injected race tests for each window; two concurrent starts yield exactly one run; edit-after-preflight start fails with a typed conflict.

## 15. TPR-13 — Normalize no-op episode comparison

### Defect
`EpisodeConfigurationService.edit` (`episode_config.py:67`) compares raw `snapshot()` dicts. The guided wizard strips the title; a CLI-stored title with trailing whitespace makes an unchanged guided save look meaningful and drops the plan. List vs tuple and `None` vs `""` are latent mismatches.

### Required behavior
Define one canonical normalization (strip text, tuple host IDs, `None`/blank policy, integer duration seconds) applied at the service boundary for both storage and comparison. All surfaces (CLI, Quick, guided, legacy setup) go through it.

### Acceptance
Table test across surfaces: whitespace-only, `None`/`""`, list/tuple host IDs → no-op preserves plan identity; a real change still invalidates.

## 16. TPR-14 — Readiness callback contract

### Defects
1. `request()` replaces callbacks with `[callback]` (`guided_async_readiness.py:230`), dropping subscribers of a superseded pending generation; the saturated branch and `_fingerprint_failed` preserve them.
2. Callback loops in `_start_failed` (`:322`), `_complete` (`:441`) and `_timeout` (`:467`) do not isolate exceptions; one failing subscriber prevents later ones.

### Required behavior
Every subscriber registered for any generation is notified exactly once when that generation is superseded, completed, timed out or fails to start. Each callback is invoked in isolation with sanitized logging of failures.

### Acceptance
Unit tests with two distinct subscribers across supersession; a raising subscriber does not block the next.

## 17. TPR-15 — Locked config I/O on the UI thread

### Defect
`_configuration_fingerprint` → `ProviderController.config()` → `UserConfigStore.load()` takes the config `flock` (`user_config.py` around lines 400 and 539-551) and is called from `request()`/`_complete()` on the Textual thread. A concurrent writer holding the lock stalls the UI.

### Required behavior
Compute the fingerprint from an in-memory snapshot published by the controller (updated on commit), or load off-thread. The UI thread must never block on the config lock.

### Acceptance
Test holding the config lock from another thread while calling `request()`: returns within a small bound and the UI stays responsive (pilot key press processed).

## 18. TPR-16 — Readiness probe budget and robustness

### Defects
1. The per-request socket budget is `min(timeout/4, 1.0)`, but calls are sequential. With N unreachable LLM providers (up to two calls each, plus system checks), total wall time can exceed the UI deadline. This is not documented as such.
2. `readiness_probe_controller` (`provider_tui.py:220-238`) applies bounded timeouts only when `type(factory) is ProviderFactory`; any subclass silently gets unbounded probes.
3. Each probe rebuilds every adapter, and one unbuildable provider (e.g. a missing credential env var) fails the whole snapshot instead of degrading per provider.

### Required behavior
1. Enforce an aggregate deadline across sequential calls (remaining-time budget passed to each call) or document the bound precisely in the user guide and architecture notes.
2. Replace the exact type check with an explicit capability or protocol method.
3. Build/probe failures are reported per provider; other providers' readiness is still shown.

### Acceptance
Tests: many unreachable fakes complete within the aggregate deadline; a factory subclass gets bounded probes; one unbuildable provider yields per-provider "needs attention" while others report ready.

## 19. TPR-17 — Make the typed dirty-form protocol the real contract

### Gap
SPR-100's first item was checked, but `WizardDirtyFormSnapshot` (`wizard_shell.py:60-83`) is built fresh in `_dirty_form_snapshot` (`:428-453`) and production reads only `.dirty` (`:484`). `semantic_snapshot` and `original_destination` are read only by tests. The pending destination is a separate string (`_pending_transition`). Host and plan target drift is handled by ad-hoc sentinels (`_ignore_host_picker_value`, `_pending_host_form_values`, `_enforce_dirty_host_selection`; `guided_host_wizard.py:120-197`), and host dirty checks parse `_form_baselines` directly (`:228-292`). `_form_target_identity` reads subclass-private attributes via `getattr`. `_editable_snapshot` silently skips missing widgets. Subclasses call `_remember_current_form()` unconditionally, undoing the shell's `_schedule_form_baseline` race guard (`:455-476`). This is the root cause class behind TPR-02, TPR-06, TPR-08 and TPR-09.

### Required behavior
1. Capture a `WizardDirtyFormSnapshot` when a confirmation opens and carry it through to save/discard; save/discard act on the snapshot's target identity and destination, and reject execution if the live target drifted.
2. Baselines are set only via one shell API invoked after durable load, successful save, or confirmed discard. Remove ad-hoc subclass baseline calls.
3. Subclasses declare their target identity via an overridable method, not `getattr` on private names.
4. Replace host/plan sentinels with the shared snapshot mechanism.
5. A test asserts every `_FORM_FIELDS` ID resolves to a widget on every step where it is declared; missing widgets raise in tests.

### Acceptance
All TPR-01/02/06/08/09 regressions pass through the shared mechanism; existing dirty-navigation suites stay green; code search shows no `_remember_current_form()` calls outside the sanctioned API sites.

## 20. TPR-18 — Strengthen acceptance tests

### Gaps
- `tests/test_second_post_review_dirty_navigation.py` has 35 tests but only 4 `pilot.press` calls; about 37 tests set `context.state` directly and about 40 calls set baselines manually.
- I/O failures are mostly injected by monkeypatching wizard methods (e.g. `test_second_post_review_host_membership.py:242`, `lambda: False`) rather than at the service or filesystem layer.
- "Restart" tests hydrate by hand instead of going through `GuidedDraftStore` resume and screen mount.
- The readiness responsiveness test calls `action_continue()` / `action_navigate()` directly; only `tab` is a real key press.
- Timing-dependent sleeps (`asyncio.sleep(0.12)` vs 0.05s timeout; `time.sleep(0.02)` vs 0.01s) can flake on loaded CI.
- `queued_worker_count` is a constant 0 (`guided_async_readiness.py:113-117`), so assertions on it are vacuous.

### Required behavior
1. Add a shared pilot helper that drives navigation only through key presses/clicks and reaches steps through real flows.
2. Inject failures at the service or filesystem boundary (fault-injecting store/repository fixtures), not on wizard methods.
3. Restart tests use `GuidedDraftStore` and a fresh app instance.
4. Replace wall-clock races with events or a controllable clock.
5. Remove `queued_worker_count` or make it meaningful, and fix the assertions that use it.

### Acceptance
Each strengthened test is shown to fail when its guarded production code is reverted (mutation check recorded in the evidence ledger).

## 21. TPR-19 — Configuration and security findings

The SPR-500 persistence contract was found sound: a stable `.config.json.lock` held with `flock` across the CAS and `os.replace`, a `mkstemp` temp file, fsync ordering, owner-only cleanup and mode 0600 were all verified. The "no CLI global-defaults writer" N/A was confirmed (`command.py:95` only loads). The findings below concern the sanitizer and validation paths.

### TPR-19.1 — Exponential backtracking (ReDoS) in `redact()` — Medium, reproduced

`_AUTH_QUOTED` (`diagnostics.py:27`) uses `(?:\\.|(?!\3).)*?\3`. A backslash can match either alternative, so the search is exponential when the closing quote is missing. Measured during review: `redact('"authorization": "' + "\\a"*n)` took 0.009s, 0.037s, 0.145s and 0.534s for n = 16, 18, 20, 22, and the reviewer saw about 2.2s at n=24 and a hang at n=500. Any provider error that echoes a JSON body reaches this through `sanitize_exception_message` and can hang the readiness/generation worker or the UI. The pattern predates the second cycle but is in SPR-600's sanitizer scope.

**Required:** make the second alternative exclude backslash (`[^\\]` combined with the quote exclusion, as `_QUOTED_MAPPING_ASSIGNMENT` already does). Audit every pattern in `diagnostics.py` for ambiguous alternation or nested quantifiers. Cap input length processed by `redact()` (truncate with a marker) as defense in depth.
**Acceptance:** a performance regression test runs each sanitizer pattern on adversarial inputs of 10k characters under a tight bound (e.g. under 50 ms). Existing redaction tests stay green.

### TPR-19.2 — Quick Deep Dive echoes a rejected research value — Low–Medium, reproduced

`quick_deep_dive.py:127` calls `ResearchMode(research)` on the project-instructions override without catching its `ValueError`, so `{"quick_deep_dive_research_policy": "sk-CANARY"}` surfaces `'sk-CANARY' is not a valid ResearchMode`. This contradicts the comment at line 111 ("never echo arbitrary project instructions"). The override is also not case-normalized, so `Standard` fails here while user config accepts it.

**Required:** parse through the same normalizer that `UserConfig` uses (case and alias handling), and raise a generic message `from None`.
**Acceptance:** canary test across Quick CLI and TUI surfaces; a mixed-case valid value is accepted consistently with Settings.

### TPR-19.3 — Settings validates references before normalization — Low, reproduced

`settings_screen.py:54` calls `validate_default_references` on the raw candidate before `UserConfig` normalization. `save_model_default("research_planning", "p :m")` fails with the misleading "references an unknown provider", while `save_provider(..., default_updates={"research_planning": "p :m"})` accepts it and stores `p:m`. The split between `ProviderController.validate_default_references` and `UserConfig` normalization is the root cause.

**Required:** one shared path, `validate_candidate` (normalize then reference-check), used by Settings, ProviderController and first-run, as `provider_tui.py:196` already does.
**Acceptance:** table test that the same input yields the same outcome and stored value through every writer.

### TPR-19.4 — Fragment redaction truncates the rest of the line — Low, reproduced

`_URL_FRAGMENT` (`diagnostics.py:60`) replaces `#([^\s]+)`, which consumes everything up to the next whitespace. `{"url":"https://h/x#access_token=C","k":1}` becomes `{"url":"https://h/x#[REDACTED]`, losing the closing quote and the following fields. This is privacy-safe but breaks the SPR-600 "keep ordinary context intact" requirement and makes diagnostics harder to read.

**Required:** end the fragment at URL delimiters (quotes, `<>`, `)`, `]`, `}`, `,` and whitespace), so surrounding JSON and prose are preserved.
**Acceptance:** tests on JSON, prose, Markdown links and multiple URLs per line; no canary present and context intact.

### TPR-19.5 — Sanitizer coverage gaps — Low, reproduced

- `_CREDENTIAL_URL` (`diagnostics.py:55`) covers only `http(s)`, so `wss://user:CANARY@h` and `ftp://user:CANARY@h` keep their userinfo.
- `?code=`, `?sig=`, `X-Amz-Signature=` and OAuth hybrid fragments such as `#state=1&code=C` are not redacted.
- Partly encoded `https://h/x%23access_token%3DC` is not redacted.

**Required:** scheme-agnostic userinfo redaction for any `scheme://user:pass@host`. Extend the sensitive key list (`code`, `sig`, `signature`, `x-amz-signature`, `x-goog-signature`, `id_token`, `refresh_token`). Decode `%23` and `%3D` within the bounded decode loop before fragment and query matching.
**Acceptance:** matrix test with canaries for each case. Benign URLs (no credentials) are unchanged.

### TPR-19.6 — Re-entrant lock wrapper deadlocks on nesting — Low, source-verified

`UserConfigStore._locked` (`user_config.py:542-544`) pairs a re-entrant `RLock` with a fresh `flock` file descriptor per call. A nested `_locked()` call on the same thread would block forever on the second `flock`. Nothing nests today, but the `RLock` implies re-entry is safe.

**Required:** either track depth and reuse the held descriptor (real re-entrancy) or use a plain `Lock` and assert non-nesting.
**Acceptance:** test that nested acquisition either succeeds or fails fast with a clear error, never hangs (run under a timeout).

### TPR-19.7 — Minor validation and code-quality items — Low

- An uppercase scheme (`HTTP://`) is rejected (`user_config.py:149`). Accept it case-insensitively and normalize to lowercase.
- `UserConfig.validate_defaults` is a 135-line procedural validator that repeats the control-character check about 10 times. Extract one helper and keep behavior unchanged.
- `_redact_text` chains about 10 regex passes and three different bounded-decode loops (4, 5 and 5 iterations). Consolidate the decode loop and document the pass order.
- `os.fchmod` in `_write_temporary` is redundant after `mkstemp`. Keep it only if documented as defense against a hostile umask.

**Acceptance:** existing config and diagnostics suites unchanged and green after the refactors.

## 22. TPR-20 — Reconcile the second-cycle checklist

Without changing checked state, add a dated "Post-closeout review 2026-10-13" note to `docs/DEEP_DIVE_TUI_SECOND_POST_REVIEW_REMEDIATION_TODO_2026-10-09.md` listing each second-cycle item contradicted by a TPR finding (at minimum: SPR-100 typed protocol, baselines, voice rediscovery, reload/resume, destination labels, discard, double-submit, clean navigation, pilot matrices; SPR-200 profile/membership distinction and tests; SPR-300 deadlines and retry display; SPR-700 races, TUI/CLI consistency and actionable UX; SPR-900 review completeness), with a pointer to this spec. Also correct `docs/ARCHITECTURE.md` lines 189-191 per TPR-04.

## 23. Delivery plan and exit gates

1. **Reproducers first:** permanent failing tests for every TPR item (or recorded N/A).
2. **Crash, hang and integrity fixes:** TPR-01, 02, 03, 04, 19.1.
3. **Wizard contract:** TPR-17, then TPR-06, 07, 08, 09, 10, 11 on top of it.
4. **Readiness:** TPR-05, 14, 15, 16.
5. **Lifecycle races:** TPR-12, 13.
6. **Config/security:** TPR-19.2 to TPR-19.7.
7. **Test hardening:** TPR-18, then TPR-20 documentation.
8. **Exit gates:** `uv lock --check`, Ruff format and lint, strict mypy, full pytest with exact count and no unexplained skip/xfail, wheel/sdist build, installed-wheel guided acceptance, exact-head CI on the final implementation and documentation commits.
