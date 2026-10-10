# Deeper Dive TUI — Second Post-Review Remediation Specification

**Created:** 2026-10-09 (America/Los_Angeles)  
**Status:** Proposed / implementation not started  
**Reviewed `master` baseline:** `ce5eee194b7adcce4f077b04e7f9cdb1d7f7de5b`  
**Companion authoritative implementation checklist:** `docs/DEEP_DIVE_TUI_SECOND_POST_REVIEW_REMEDIATION_TODO_2026-10-09.md`  
**Predecessor (historical, do not rewrite):** `docs/DEEP_DIVE_TUI_GUIDED_WORKFLOW_POST_REVIEW_REMEDIATION_TODO_2026-10-09.md`  
**Previous qualified CI:** https://github.com/ekkus93/deeper-dive/actions/runs/38014377685 (1,068 tests; not qualification for changes proposed here)

## 1. Executive summary

A follow-up read-only review of the previously qualified guided workflow found seven additional possible defects or hardening gaps. The first two are high-severity data-loss paths, four concern background-worker lifecycle, domain validation, configuration durability, and credential-bearing URL fragments, and the seventh is a high-severity potential episode-state/plan-invalidation regression. This document is the source-of-truth **behavioral contract**, not proof that every suspected failure is reproducible. Every finding must first be independently reproduced using an exact-master fixture or explicitly disposed of with evidence. Do not claim reproduction, an exploit, or final qualification without running it.

| ID | Priority | Topic | Main production surface |
| --- | --- | --- | --- |
| SPR-01 | High | Dirty guided forms lose input through navigation/rehydration | `wizard_shell.py`, `guided_episode_wizard.py`, all guided steps |
| SPR-02 | High | Unsaved host membership/order omitted from dirty tracking | `guided_host_wizard.py`, `wizard_shell.py` |
| SPR-03 | Medium | Timed-out provider probes continue as accumulating daemon threads | `guided_async_readiness.py`, provider adapters |
| SPR-04 | Medium | Composite setting saves accept semantically invalid defaults | `settings_screen.py`, `user_config.py`, consumers |
| SPR-05 | Medium | Config writes lack secure unique temp files, fsync and concurrency contract | `user_config.py`, `provider_tui.py` |
| SPR-06 | Medium | Credential-bearing URL fragments are not rejected or sanitized | `user_config.py`, `diagnostics.py` |
| SPR-07 | High, pending reproduction | Editing episodes resets state to draft and deletes plan even on no-op edit | `episode_config.py`, `storage/episode_configuration.py` |

**Mandatory distinction:** A source-level risk is not a confirmed user-visible bug until its failure path is demonstrated. Tests must fail on the reviewed baseline and pass after the repair whenever a deterministic reproducer is practical. If code inspection disproves an issue, record exact evidence and a narrowly justified N/A; do not quietly delete it.

## 2. Governing execution contract

- Work against the current `master` head. Use **Ralph Bridge exclusively** for GitHub/CI operations and direct-to-`master` exact-head compare-and-swap commits where authorized. Never create per-checkbox branches or PRs.
- At the start of each session and after each successful commit, reload this specification, the TODO, current `master`, relevant CI and conflicting work. Do not duplicate already-landed code.
- Optimize for coherent behavioral slices; group wizard navigation/host state (SPR-01/02), configuration/security (SPR-04/05/06), background readiness (SPR-03), and episode lifecycle (SPR-07). Avoid single-checkbox reconciliation commits.
- All new tests use deterministic fixtures, fake providers and isolated temporary workspaces; do not depend on private data, cloud credentials, external APIs, hardware, or a developer desktop.
- Preserve original production boundaries (`ProviderController`, `UserConfigStore`, `EpisodeConfigurationService`, `GuidedDraftStore`, `ProductionWizardCompletion`, `FirstRunReadinessCoordinator` and shared planners/preflight). Do not invent a parallel guided-only storage, generation, or repair stack.
- Previously completed remediation and the 2026-10-08 predecessor are historical evidence; do not rewrite their checked states or equate their CI results with new implementation qualification.
- Record code references, test identifiers, exact tested commit SHA, CI URLs/run/job IDs, and observed outcomes when reconciling each task. The final TODO must show no unchecked tasks unless marked as justified N/A with explicit evidence.
- Security-sensitive regression fixtures must use artificial canaries and never include real credentials in logs, exceptions, configs, TODO or CI artifacts.

## 3. SPR-01 — Guard all dirty wizard navigation and rehydration

### Baseline signal
`WizardShell.action_back` and `action_continue` can transition without calling `_current_form_dirty()`; concrete wizards then refresh controls from durable values. A Save-and-Exit-specific guard does not protect Back, Continue, automatic recovery, global navigation, or screen resume.

### Required behavior
1. Define a shared edit-session contract for each guided step: persisted baseline, current UI snapshot (including non-Input model state), dirty flag, destination/action, save transaction, and safe discard. Compute cleanliness against **actual last successfully persisted state**, not merely whichever snapshot happened to be taken most recently.
2. A dirty form must never be discarded on Back, Continue, Escape, Home/global navigation, step jump, resumed screen rehydration, wizard completion, or external state refresh without explicit user choice. Block the transition, present **Save changes and continue**, **Discard changes and continue**, **Cancel/keep editing**, and bind continuation to the original intended destination and original form identity.
3. Cancel is the initial focused action; keyboard navigation works; Escape in the modal cancels. Saving through the existing production service and validating all fields is mandatory. Failed validation or persistence keeps typed input and current step. Save/discard is single-shot and resistant to key repeat/double-submit.
4. Do not write raw provider credentials, pasted source body, invalid edits or unsaved business objects into `GuidedDraftStore`. Persisted checkpoints represent only safe durable boundaries. Explicit discard preserves previously durable data, not the user's unsaved edits.
5. Automatic UI hydration (`_load_episode_form`, `_refresh_research_choice`, `_load_selected_host`, `_load_selected_segment`) may replace fields only when initializing a step, after confirmed discard, after successful save, or when a controlled external-change merge was accepted. An unrelated Select change must not overwrite a dirty form.
6. Changing selected entities (e.g., host/plan segment) while dirty must use the same contract and guard against stale selection identity. Snapshot/commit receipts must identify the correct target.
7. A successful Save operation is signaled by its production result, not by matching user-visible status-string prefixes; distinguish no-op, validation failure and I/O failure.
8. Where source imports are partial, do not silently mark the entire mixed-input form clean; present imported/skipped breakdown and keep any unprocessed input editable.

### Acceptance
Deterministic Textual pilot tests for every editable first-run and New Deep Dive step; unsaved episode title/focus/audience/depth/duration; plan segment fields; host text; source title/body/path/URL; research selection; provider/model/TTS/default choices; all navigation actions and initial focus; clean navigation remains low-friction. Include a test that fails on baseline then passes after repair.

## 4. SPR-02 — Make host selection and host ordering transactional UI edits

### Baseline signal
`_FORM_FIELDS` covers guided host text but not in-memory `_selected_host_ids`, which can change through add/remove/move actions before `action_save_host_order()`.

### Required behavior
1. Include ordered host IDs **and selected episode identity** in the dirty-form snapshot. Distinguish editing a host profile from editing episode membership/order; both may be simultaneously pending.
2. Detect add, remove, reorder and selected-host identity changes. A no-op move or move-then-undo to the persisted order returns to clean.
3. Save changes and exit/continue must save the host profile if dirty and then the order via `EpisodeConfigurationService`, with explicit handling of multi-operation failure. Do not silently commit only the profile and discard order.
4. If profile + order cannot be stored in one transaction, either provide an explicit two-stage result with safe retained edits/retry or implement a production-layer transactional operation. No UI-level hidden partial success.
5. On load/restart, derive order from the durable episode config. Host membership cannot contain duplicates, cannot reference another project, and remains ordered across process restart. Avoid resetting `_selected_host_ids` during unrelated refreshes.
6. Changing the host selector while profile fields are dirty must block/warn rather than replace the existing profile edit.

### Acceptance
Textual pilots add/remove/reorder, Save+Exit, navigation, discard, cancel, failed save, restart, separate projects/episodes, mixed profile+order edits, host-selector changes and double submission. Verify exact ordered IDs persisted; no loss and no unrelated episode mutation.

## 5. SPR-03 — Bounded, non-blocking and race-safe readiness worker lifecycle

### Baseline signal
`FirstRunReadinessCoordinator.request()` starts a fresh daemon `Thread` and `Timer`. `_timeout()` marks a view as failed but does not cancel the underlying blocking probe. Subsequent retries may accumulate live threads.

### Required behavior
1. Provider sockets, HTTP clients and adapter health/discovery calls must enforce real transport deadlines; a UI timeout alone does not cancel a network request.
2. Use bounded worker capacity and explicit in-flight ownership. Prefer one reusable executor/coordinator per application (or tightly bounded per provider) with a well-defined queue/reject/coalesce policy. No unbounded pending threads/timers on repeated refresh, failure, navigation or shutdown.
3. Coalesce identical fingerprints; allow superseding configurations without letting an old worker publish stale results. Generation ID and fingerprint must be checked at every publish/error/timeout boundary. Do not block the Textual event loop while enforcing limits.
4. A timed-out probe must not promote stale success after its timeout. Retries must remain possible without losing callbacks; close/quit must release owned resources or explicitly bound uninterruptible in-flight tasks.
5. Preserve existing discovery de-duplication, local/offline policy and sanitized status text. Report Checking/Ready/Needs attention with a retry path.
6. Instrument deterministic counters for running/queued/live probes and expose safe test introspection; avoid asserting that Python forcibly kills uninterruptible threads.

### Acceptance
Blocking and never-returning fake probes; 100 rapid refreshes, repeated timeout/retry cycles, config changes midflight, app exit, callback coalescing, wrong-thread UI protection, call-count bounds, and proof no unbounded worker growth. Run installed-wheel guided TUI acceptance.

## 6. SPR-04 — Validate semantic defaults before durable composite saves

### Baseline signal
`SettingsController.set_defaults()` strips values/keys and atomically writes them, but fields in `UserConfig.defaults` remain generally free-form. Domain values such as research mode or Quick host presets can pass save and fail later.

### Required behavior
1. Define one typed/validated contract or shared per-key validators for persisted defaults. Cover `research_policy` and `quick_deep_dive_research_policy`, network/local-only policy, Quick duration and two valid host presets, provider/voice references, model role references, ffmpeg path semantics where applicable, Kitten model path, and boolean/diagnostic values. Do not inadvertently reject documented free-form values.
2. Normalize whitespace and aliases consistently with the consuming services. Preserve already-valid configurations and explicit blank-as-clear behavior. Do not turn optional unset values into invalid required values.
3. Validate the entire candidate before a **single** durable save, covering first-run, advanced Settings, provider mutations, and CLI mutations. Invalid input must be rejected before touching in-memory published provider state or persisted bytes. Error text must not echo secrets.
4. Existing invalid configs should fail safely and offer actionable nonsecret recovery guidance; no silent partial migration. Consider schema-compatible rollout for backward compatibility.
5. Protect against TOCTOU between validation and commit. Multiple field updates either all apply or none do.

### Acceptance
Table-driven good/bad settings matrix, all mutation surfaces, round-trip/restart, current config fixtures, rollback and counting-store tests. Quick Deep Dive must never encounter a preventable invalid mode/preset from a previously accepted settings save.

## 7. SPR-05 — Harden user configuration persistence and concurrency

### Baseline signal
`UserConfigStore.save()` writes to a predictable `config.json.tmp`, chmods and replaces the destination without an explicit flush/fsync or directory fsync. Two writers can race, and a writable config directory permits temp-path tampering.

### Required behavior
1. Use a securely created, unique temp file in the same directory with `0o600` owner-only permissions on POSIX. Do not follow an attacker-controlled temp symlink. Flush, `fsync` and atomically `os.replace`; `fsync` the containing directory where supported. Do not rely on `write_text` + fixed temp path.
2. Make failure atomic: parse/validate and serialize before mutation; on temp creation/write/sync/rename failure preserve previous file bytes where the rename did not complete and clean up owned temp files. Define behavior if post-rename directory sync fails (durability uncertain, not falsely reported as rolled back).
3. Define multi-writer semantics for independent screens/processes. Use a documented lock with bounded timeout or an optimistic revision/compare-and-swap contract with retry/conflict. Never silently lose settings updated by another writer. Writes from `ProviderController` and `SettingsController` follow the same policy.
4. Enforce permissions and handle pre-existing symlinks/directory substitution safely within the supported threat model. The config directory must have documented trust/ownership expectations. Do not claim protection against a fully compromised same-UID process.
5. File contents remain non-secret and validated even for mutated Pydantic objects; existing environment credential references continue working.
6. Provide failure-injection hooks that exercise rename, fsync, chmod, concurrent writers and cleanup deterministically on supported platforms.

### Acceptance
Parallel writer barrier tests (threads/processes as feasible), conflict/retry result checks, no stale overwrite, no orphan temps, zero partial JSON, owner-only mode, fixed-temp symlink canary protection, crash-step simulation and restart/parse tests on Linux.

## 8. SPR-06 — Reject and redact URL fragments with credentials

### Baseline signal
`ProviderConfig.validate_base_url()` rejects credentials in userinfo and sensitive query parameters, but does not constrain `urlsplit(...).fragment`. Diagnostic URL redaction focuses on query pairs and userinfo.

### Required behavior
1. Provider endpoint URLs reject nonempty fragments entirely: HTTP fragments are not sent to the server and are not meaningful as base endpoints. Reject percent-encoded or mixed-case credential-looking fragments without echoing their contents. Preserve legitimate HTTP/HTTPS localhost/remote URLs, IPv6 and permitted query parameters.
2. Diagnostic text sanitizer must hide credential-like data after `#` for URLs encountered in existing logs/error text, including mixed case, encoded separators and multiple URLs, while preserving benign message context. Prefer parsing/tokenization with well-defined boundaries over broad destructive regex.
3. Keep Bearer/Basic/Token/Digest, userinfo, query, recursive mapping, nested exception, CLI and TUI canary behavior unchanged. Do not leak rejected input in Pydantic error rendering.
4. Review all provider URL mutation paths to ensure validation runs at save, even after models are mutated post-validation.

### Acceptance
Provider URL fragment test matrix, encoded/mixed-case canaries, nonsecret URLs, whole-config byte-level absence assertions, recursive diagnostics, and installed-wheel CLI/TUI error-canary tests.

## 9. SPR-07 — Preserve episode lifecycle and avoid needless plan invalidation

### Baseline signal (requires reproduction)
`EpisodeConfigurationService._record()` always produces `state="draft"`; `edit()` calls it for existing episodes. `EpisodeConfigurationRepository.update()` unconditionally deletes segment plans and episode plans, even when a submitted config is semantically identical.

### Required behavior
1. Establish an explicit authoritative episode state machine and define how draft, planned, running, paused, failed and completed episodes interact with later edits. Inspect every generation, library and CLI consumer before choosing whether completed episodes are immutable, revised in place, or forked into a new draft episode.
2. **Never silently demote a historical completed episode or active run to draft.** Preserve run IDs, run state, audio, transcript and export references. Active generation edits must be rejected, deferred or explicitly revisioned in a way consistent with existing run-state contracts.
3. Determine plan invalidation by comparing canonical plan-relevant fields: hosts/order, focus, duration, relevant model/research/source overrides, and any other fields the planner snapshots. No-op saves and non-plan-affecting metadata changes must not delete usable plans.
4. For meaningful plan changes, invalidate/regenerate **only** affected draft plans or create a new revision as needed. Existing historical generation artifacts must remain immutable and discoverable; do not silently erase a completed episode's plan evidence.
5. All state/update/invalidation changes occur inside an appropriate database transaction; account for concurrent generation/plan writes and stale UI snapshots using a version/revision or CAS precondition where appropriate.
6. Align CLI and TUI services, library status, plan/show/export, Quick Deep Dive and multi-episode isolation. Friendly errors must explain whether an edit requires a new episode/revision.
7. First reproduce baseline no-op plan deletion and completed-state demotion with persisted fixtures. If actual production guards prevent the sequence, document their exact code/tests and adjust the repair scope based on evidence.

### Acceptance
No-op edit retains plan identity; metadata-only edit follows a documented policy; plan-relevant edit invalidates in the permitted draft state only; concurrent start/edit cannot race; completed, failed, paused and running cases are explicit; historical exports and transcript/audio survive; restarting retains state; project/episode isolation holds.

## 10. Shared deterministic qualification fixture

Provide a reusable fixture that builds a temporary workspace with two projects, indexed sources, multiple hosts, configured fake LLM/TTS, research policy, independent episodes, plan(s), transcript turns, audio artifact(s), a completed run and an incomplete run. Expose precise identity snapshots and byte-level config/draft snapshots. Use factory/dependency injection only at existing production boundaries; no bespoke guided-only shortcuts. Reuse for wizard navigation, host membership, episode lifecycle, Quick/CLI/TUI equivalence, installed-wheel acceptance and failure injection.

## 11. Cross-cutting test and security matrices

- **Dirty state matrix:** every wizard step × dirty/clean × Back/Continue/Escape/Home/reselection/reload × save/discard/cancel/fail × keyboard/double submit.
- **Race matrix:** readiness timeout/refresh/config-change/exit × stale/blocked/failed probe; config writer A/B × same/different keys and failure points; episode edit × plan/generation transitions.
- **Security matrix:** invalid credential references, userinfo/query/fragment payloads, mixed-case/encoded credentials, recursive diagnostics, read/write permission controls, symlink/temp-file canaries, no-credential persisted/exported output.
- **Packaging matrix:** locked dependency resolution, Ruff format/lint, strict mypy, full pytest, wheel/sdist build, installed-wheel fresh-machine CLI and guided TUI, real KittenTTS Micro CPU smoke where available in the existing CI job.
- **Behavior preservation:** first-run, New Deep Dive, source indexing, research default precedence, model-role readiness, Quick generation, preflight, repair, transcript, playback, export, saved/resumed drafts, and multi-episode isolation.

## 12. Delivery plan and exit gates

1. Baseline/repro: capture exact current SHA and qualified CI; reproduce/disprove each candidate with deterministic failing tests and written risk assessment; preserve predecessor evidence.
2. Implement SPR-01/02 as one guided-edit consistency cluster, followed by targeted Textual pilots and CI.
3. Implement SPR-04/05/06 as one configuration/security cluster where transaction boundaries overlap; add rollback, concurrency, fragment and regression tests.
4. Implement SPR-03 worker lifecycle using bounded fakes and real adapter timeout policy; run responsiveness/race tests.
5. Implement SPR-07 after selecting an explicit episode lifecycle contract; run CLI/TUI/library/generation regressions together.
6. Run a fresh independent code review of all modified paths, including authorization/redaction and unhandled user-visible errors; record newly discovered problems in this TODO before closeout rather than declaring success prematurely.
7. Complete installed-wheel/fresh-machine and full static/runtime gates. Reconcile TODO only for qualified behavior on `master`, then run **new exact-head CI on any reconciliation-only commit**. Report exact full SHA, CI run/job URLs, test count, and outstanding justified N/A items.

**Completion definition:** Every unchecked subtask is implemented and verified or explicitly N/A with a defensible reproduction/evidence record; no open critical/high-severity regressions; exact final `master` SHA passes required CI. A green run against the *previous* 2026-10-09 remediation head is not proof for this new cycle.
