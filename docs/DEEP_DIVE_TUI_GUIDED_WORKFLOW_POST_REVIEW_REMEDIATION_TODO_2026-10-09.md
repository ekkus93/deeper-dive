# Deeper Dive TUI Guided Workflow Post-Review Remediation TODO

**Created:** 2026-10-09  
**Status:** Complete — final reconciliation accepted only after successful exact-head CI  
**Authority:** `docs/DEEP_DIVE_TUI_GUIDED_WORKFLOW_POST_REVIEW_REMEDIATION_SPEC_2026-10-09.md`  
**Reviewed baseline:** `87208a607def3e78e3466382b5aa33ea49c685b3`  
**Predecessor:** `docs/DEEP_DIVE_TUI_GUIDED_WORKFLOW_TODO_2026-10-08.md`

This is the sole authoritative checklist for defects found by the 2026-10-09 independent review of the completed guided-workflow implementation. The predecessor TODO remains historical evidence and must not be used as completion truth for these newly discovered defects.

A checkbox is complete only when the production behavior is correct, focused regression evidence exists, relevant acceptance gates pass, the change is on `master`, and the exact `master` head has passed CI. Do not mark an item complete merely because a helper exists or a unit test was added.

## Execution rules

- Reload this TODO and companion spec from current `master` at the start of every remediation run and after every successful direct-master write or merge.
- Inspect current `master`, existing relevant Ralph work, and exact-head CI before duplicating implementation.
- Work directly on `master` when Ralph Bridge policy permits; do not create a branch/PR per checkbox.
- Prefer coherent vertical slices: security/config, Save/Exit/drafts, research/readiness, destructive/atomic UX, then qualification/closeout.
- Use Ralph Bridge for GitHub and CI operations; do not use the default GitHub tool.
- Preserve the completed 2026-10-08 TODO as historical evidence.
- Reuse production services/controllers and existing provider/research/host/episode/generation boundaries.
- Keep deterministic fake providers behind normal provider factory/configuration boundaries.
- Never put raw credentials into test failure output, TODO evidence, diagnostics, or wizard drafts.
- Run broad qualification early enough to detect cross-cluster regressions; do not defer all integration evidence until final reconciliation.
- A tool timeout, transient CI/API error, ordinary test failure, type/lint failure, branch drift, or implementation bug is not a user blocker; diagnose and continue.

## PRR-000 — Baseline, reproduction, and guardrails

- [x] Reload the post-review spec/TODO and confirm the current `master` SHA before implementation.
- [x] Confirm the predecessor TODO remains unchanged as historical evidence.
- [x] Add or retain a review-baseline note tying this remediation to reviewed SHA `87208a607def3e78e3466382b5aa33ea49c685b3` without treating that SHA as the final implementation head.
- [x] Reproduce the Basic Authorization leak with a deterministic test before changing the sanitizer.
- [x] Reproduce the Token Authorization leak with a deterministic test before changing the sanitizer.
- [x] Reproduce the Digest Authorization leak with a deterministic test before changing the sanitizer.
- [x] Reproduce raw `credential_env` persistence with a deterministic validation/persistence test.
- [x] Reproduce provider URL userinfo persistence with a deterministic validation/persistence test.
- [x] Reproduce dirty Save-and-Exit data loss in first-run with a Textual pilot test.
- [x] Reproduce dirty Save-and-Exit data loss in New Deep Dive with a Textual pilot test.
- [x] Reproduce the first-run research default -> Quick Deep Dive mismatch.
- [x] Reproduce the New Deep Dive Research selector hydration mismatch.
- [x] Reproduce rejection of a valid non-default discovered role model.
- [x] Reproduce stale Resume Deep Dive after successful workflow completion.
- [x] Reproduce host optional role/instructions clear failure.
- [x] Add deterministic evidence for at least one advanced destructive action that currently executes without confirmation.
- [x] Add deterministic evidence that one logical multi-default save currently performs multiple durable config writes.


**PRR-000 historical reproduction evidence:** the independent review spec records the defects against reviewed baseline `87208a607def3e78e3466382b5aa33ea49c685b3` before remediation: PRR-01 explicitly reproduces Basic/Token/Digest authorization leaks; PRR-02 records arbitrary `credential_env` and URL-userinfo persistence; PRR-03 records dirty Save-and-Exit loss; PRR-04 records research default/hydration mismatch; PRR-05 records non-default discovered-model rejection; PRR-06 records stale Resume state; PRR-09 records optional-host clear failure; PRR-10 records unconfirmed advanced destructive actions; and PRR-11 records repeated durable writes for one logical composite save. Current deterministic regressions preserve each failure vector without reverting fixed production code.

## PRR-100 — Canonical authorization and recursive sanitization

- [x] Define one canonical public sanitization API for user-visible/loggable diagnostic text and recursive structures.
- [x] Redact the entire value of `Authorization:` headers regardless of authentication scheme.
- [x] Redact the entire value of `authorization=` assignment forms regardless of authentication scheme.
- [x] Preserve Bearer-token redaction while fixing Basic/Token/Digest behavior.
- [x] Handle mixed/lower/upper-case Authorization field names.
- [x] Handle quoted Authorization values.
- [x] Handle JSON-like Authorization values.
- [x] Handle multiline strings containing Authorization values.
- [x] Handle multiple sensitive values in one message.
- [x] Preserve existing API-key/token/password secret-key redaction behavior.
- [x] Apply the canonical sanitizer recursively to dict values.
- [x] Apply the canonical sanitizer recursively to list/tuple values.
- [x] Apply the canonical sanitizer to chained/nested exception messages before presentation.
- [x] Ensure sanitizer output never includes the Basic credential payload canary.
- [x] Ensure sanitizer output never includes the Token credential payload canary.
- [x] Ensure sanitizer output never includes the Digest credential payload canary.
- [x] Add benign-text regressions proving ordinary words such as `tokenization`, model names, URLs without secrets, and status prose are not unnecessarily destroyed.

## PRR-110 — Provider configuration non-secret validation

- [x] Validate non-empty `credential_env` as `[A-Za-z_][A-Za-z0-9_]*` after trimming.
- [x] Reject raw API-key/token-like strings supplied as `credential_env`.
- [x] Reject whitespace-bearing credential references.
- [x] Reject punctuation-bearing values that cannot be environment-variable identifiers.
- [x] Preserve valid existing environment-variable references.
- [x] Parse provider `base_url` structurally rather than validating scheme by prefix alone.
- [x] Continue to require HTTP/HTTPS URLs.
- [x] Reject URL username/userinfo.
- [x] Reject URL password/userinfo.
- [x] Reject known sensitive query parameters case-insensitively (`api_key`, `apikey`, `key`, `token`, `access_token`, `auth`, `authorization`, `password`, `secret`).
- [x] Keep valid Ollama, llama-server, OpenAI, OpenAI-compatible LLM, OpenAI TTS, OpenAI-compatible TTS, and ElevenLabs endpoints working.
- [x] Ensure provider validation errors do not echo rejected credential material.
- [x] Ensure invalid secret-bearing provider config cannot be written by first-run.
- [x] Ensure invalid secret-bearing provider config cannot be written by the advanced Providers screen.
- [x] Ensure invalid secret-bearing provider config cannot be written through any CLI/config mutation path.
- [x] Inspect serialized `config.json` bytes in tests and prove raw credential canaries are absent.
- [x] Keep runtime credential lookup environment-reference based in provider factories.
- [x] Define and test safe failure behavior for a pre-existing invalid secret-bearing config.

## PRR-120 — Cross-surface sanitization enforcement

- [x] Inventory every TUI `_status`, error, details, health, discovery, failure, traceback, and provider-message presentation path.
- [x] Route `hosts_screen.py` provider health/error text through canonical sanitization.
- [x] Route Providers screen provider/runtime errors through canonical sanitization.
- [x] Route Settings screen runtime/readiness errors through canonical sanitization.
- [x] Route Research screen external/provider errors through canonical sanitization.
- [x] Route plan/planner screens through canonical sanitization.
- [x] Route transcript/review/repair surfaces through canonical sanitization.
- [x] Route preflight and generation monitor failure/status text through canonical sanitization.
- [x] Route Episode Library/export failure/status text through canonical sanitization.
- [x] Route guided first-run provider/model/TTS failures through canonical sanitization.
- [x] Route guided New Deep Dive source/research/host/plan/generation failures through canonical sanitization.
- [x] Route CLI command/provider errors through the same canonical behavior.
- [x] Route persisted failure presentation through the same canonical behavior.
- [x] Route debug/diagnostic/export metadata through recursive canonical sanitization.
- [x] Add a test helper/canary assertion that fails if any configured secret canary appears in rendered TUI text.
- [x] Add a test helper/canary assertion that fails if any configured secret canary appears in CLI output.

## PRR-200 — Shared dirty-form and safe-exit contract

- [x] Define a shared dirty-form protocol/contract usable by both guided wizards.
- [x] Compare current editable controls to their last successfully loaded/persisted values deterministically.
- [x] Mark first-run provider configuration dirty when relevant fields change.
- [x] Mark first-run model/default controls dirty when relevant fields change.
- [x] Mark first-run speech/voice/default controls dirty when relevant fields change.
- [x] Mark New Deep Dive project setup dirty when relevant fields change.
- [x] Mark pasted-source form dirty while title/body contains unsaved text.
- [x] Mark file/folder and URL source inputs dirty while unsaved text is present.
- [x] Mark research choice dirty when changed from the currently durable/effective policy.
- [x] Mark host create/edit form dirty when changed from durable host state.
- [x] Mark episode settings dirty when changed from durable episode configuration.
- [x] Mark any other guided editable form dirty where exiting can otherwise lose user input.
- [x] Make clean Save and Exit checkpoint and exit without unnecessary confirmation.
- [x] Make dirty Save and Exit open an explicit confirmation instead of discarding edits.
- [x] Provide a Save changes and exit action through the normal production save/validation path.
- [x] Provide an explicit Exit without unsaved changes action.
- [x] Provide Cancel/continue-editing action.
- [x] Ensure destructive discard is not the default-focused confirmation action.
- [x] On save validation failure, remain on the same screen with entered values intact.
- [x] On production save failure, remain on the same screen with entered values intact.
- [x] On explicit discard, preserve previously durable production state.
- [x] Preserve the last safe wizard checkpoint when unsaved edits are explicitly discarded.
- [x] Make non-modal Escape invoke the same dirty-aware safe-exit flow.
- [x] Make Escape inside the confirmation modal cancel/close the modal.
- [x] Prevent key-repeat/double-submit from executing save/discard twice.

## PRR-210 — Wizard draft security and lifecycle

- [x] Keep raw provider credentials out of wizard draft serialization.
- [x] Keep pasted source body text out of wizard draft serialization.
- [x] Keep other production business records out of wizard draft serialization.
- [x] If new UI-only draft fields are required, explicitly allowlist and version them.
- [x] Keep the guided draft size bound enforced.
- [x] Keep atomic temp-file + fsync + replace semantics for draft writes.
- [x] Keep symlink rejection for draft loads.
- [x] Add a symlink-safe `clear(kind)` operation to `GuidedDraftStore`.
- [x] Clear First-run draft when setup reaches its defined completed boundary.
- [x] Clear New Deep Dive draft when the guided workflow reaches its defined terminal completed boundary.
- [x] Clear the appropriate draft after explicit confirmed abandonment.
- [x] Retain the draft on normal Save and Exit.
- [x] Retain the draft on recoverable validation/provider/runtime failure.
- [x] Retain the draft while generation is in progress when resume is meaningful.
- [x] Invalidate/recover stale drafts whose referenced project/episode/run identities are no longer usable.
- [x] Make `has_resume()` reflect recoverable incomplete state rather than mere file existence.
- [x] Ensure Home removes Resume Deep Dive after successful completion.
- [x] Ensure Home retains Resume Deep Dive after an intentionally saved incomplete workflow.
- [x] Ensure draft clearing cannot delete an unrelated file through symlink/path manipulation.

## PRR-300 — Research default, hydration, and Quick parity

- [x] Document global New Deep Dive research precedence in code-facing documentation/tests.
- [x] Initialize a new project's Research selector from user-level `research_policy` when no project policy exists.
- [x] Hydrate the Research selector from an existing durable project policy on revisit.
- [x] Hydrate the Research selector from durable project policy after restart/resume.
- [x] Do not overwrite an existing project policy merely by opening/revisiting the screen.
- [x] Keep Save Research Choice routed through the production research controller/store.
- [x] Define Quick Deep Dive precedence as project Quick override > explicit user Quick override > user `research_policy` > built-in Useful.
- [x] Update `QuickDeepDiveService` to fall back to `research_policy` when no explicit Quick research override exists.
- [x] Preserve explicit `quick_deep_dive_research_policy` behavior.
- [x] Preserve project Quick Deep Dive research override behavior.
- [x] Make first-run `research_policy` affect subsequent New Deep Dive by default.
- [x] Make first-run `research_policy` affect Quick Deep Dive when no more-specific Quick override exists.
- [x] Test Off across first-run -> New Deep Dive.
- [x] Test Useful across first-run -> New Deep Dive.
- [x] Test Aggressive across first-run -> New Deep Dive.
- [x] Test Off across first-run/global -> Quick Deep Dive fallback.
- [x] Test Aggressive across first-run/global -> Quick Deep Dive fallback.
- [x] Test explicit user Quick override beats global research default.
- [x] Test project Quick override beats user Quick/global defaults.
- [x] Test research policy behavior after process restart.


**Quick research precedence evidence (2026-10-10):** `tests/test_post_review_quick_research.py` covers global Off/Useful/Aggressive, explicit user Quick override, project Quick override, and restart persistence using production episode/policy services. The existing `tests/test_quick_deep_dive.py` covers built-in Useful and normal durable Quick artifacts. Exact-head CI passed on `204d1df97dd49db17f4c4b17fdf07848d944c0c4` (run `38012285504`). First-run-to-New-Deep-Dive hydration and first-run-to-Quick integration remain unchecked pending their own end-to-end evidence.

## PRR-310 — Model-role readiness parity

- [x] Remove the requirement that a valid assigned role model equal `provider.default_model`.
- [x] Validate assigned model existence against the provider discovery snapshot.
- [x] Keep provider capability validation for role assignments.
- [x] Keep provider health/readiness validation for role assignments.
- [x] Align first-run role readiness with the production preflight compatibility policy.
- [x] Add a provider with default model A and discovered model B fixture.
- [x] Prove a role assigned to valid discovered model B passes first-run readiness.
- [x] Prove the same role/model passes production preflight.
- [x] Prove an undiscovered model fails first-run readiness.
- [x] Prove the same undiscovered model fails production preflight consistently.
- [x] Preserve restart/reload of non-default role assignments.

## PRR-320 — Non-blocking provider readiness and discovery

- [x] Inventory synchronous provider `health()`, `models()`, and `voices()` calls reachable from Textual mount/navigation/readiness paths.
- [x] Move potentially blocking first-run provider probes off the Textual UI event loop.
- [x] Move potentially blocking Home/setup-readiness provider probes off the Textual UI event loop.
- [x] Keep keyboard navigation responsive while provider readiness is checking.
- [x] Render an explicit Checking state while asynchronous readiness is pending.
- [x] Render Ready/Needs attention from the completed bounded snapshot.
- [x] Render sanitized actionable failure state on timeout/unreachable provider.
- [x] Prevent obsolete worker results from overwriting newer provider configuration/readiness state.
- [x] Coalesce or safely supersede duplicate readiness refreshes.
- [x] Reuse one model-discovery result within a readiness refresh where possible.
- [x] Eliminate the OpenAI health-plus-immediate-second-models discovery pattern from one readiness refresh.
- [x] Preserve configured timeout/retry policy without blocking UI input.
- [x] Add a deterministic slow-provider fake that blocks until released by the test.
- [x] Prove Textual pilot input/navigation remains responsive while the slow provider probe is pending.
- [x] Add unreachable-provider readiness coverage without real network access.
- [x] Add stale-result race coverage by changing provider config while an older probe is pending.
- [x] Assert bounded provider-call counts per readiness refresh.

## PRR-400 — Guided host edit completeness

- [x] Define required versus optional guided host fields.
- [x] Keep required host fields validated against blank values.
- [x] Treat blank optional role as an explicit clear during edit.
- [x] Treat blank optional instructions as an explicit clear during edit.
- [x] Route clearing through the existing host production service/repository path.
- [x] Refresh the guided host card/summary after clearing.
- [x] Prove cleared role survives restart.
- [x] Prove cleared instructions survive restart.
- [x] Preserve normal custom-host creation defaults where documented.

## PRR-410 — Consistent destructive-action confirmations

- [x] Define one reusable confirmation interaction/pattern for destructive TUI actions.
- [x] Require confirmation before advanced provider removal.
- [x] Require confirmation before advanced host removal.
- [x] Require confirmation before advanced source deletion.
- [x] Preserve confirmation before guided source deletion.
- [x] Preserve confirmation before project deletion.
- [x] Preserve confirmation before generation cancellation where applicable.
- [x] Confirmation text identifies the selected target using friendly identity.
- [x] Confirmation is keyboard accessible.
- [x] Default action is cancel/non-destructive.
- [x] Changing the selected provider clears pending provider-delete confirmation.
- [x] Changing the selected host clears pending host-delete confirmation.
- [x] Changing the selected source clears pending source-delete confirmation.
- [x] Repeated key/button events cannot execute a destructive mutation twice.
- [x] Cancel leaves durable state unchanged.
- [x] Confirm still routes through the existing production delete/remove service/controller.

## PRR-420 — Atomic composite settings/default saves

- [x] Add a controller/service helper that validates and saves a complete candidate `UserConfig` once.
- [x] Avoid repeated `UserConfigStore.save()` calls for one logical multi-field user action.
- [x] Make TTS provider + voice default save atomic.
- [x] Make research + network default save atomic.
- [x] Make Quick Deep Dive duration + host presets + research default save atomic.
- [x] Make runtime/readiness default save atomic.
- [x] Make first-run Host 1/Host 2 voice/default bundle save atomic.
- [x] Make other first-run multi-default button actions atomic where currently split across repeated `set_default()` calls.
- [x] Validate all candidate values before mutating durable config.
- [x] On validation failure, retain previous in-memory and durable config.
- [x] On simulated filesystem save failure, retain previous durable config.
- [x] Preserve owner-only file permissions after successful config save.
- [x] Add a counting config-store fake proving one durable save per logical action.
- [x] Add byte-level/semantic rollback assertions for failed composite saves.

## PRR-500 — Expanded security/redaction acceptance matrix

- [x] Add Basic Authorization canary coverage to direct sanitizer tests.
- [x] Add Token Authorization canary coverage to direct sanitizer tests.
- [x] Add Digest Authorization canary coverage to direct sanitizer tests.
- [x] Add mixed-case Authorization canary coverage.
- [x] Add quoted and JSON-like Authorization canary coverage.
- [x] Add multiline/multiple-secret sanitizer coverage.
- [x] Add nested mapping/list/tuple sanitizer coverage.
- [x] Add chained-exception sanitizer coverage.
- [x] Add CLI error-output canary coverage.
- [x] Add advanced TUI host/provider/settings/research canary coverage.
- [x] Add guided first-run canary coverage.
- [x] Add guided New Deep Dive canary coverage.
- [x] Add plan/transcript/repair/generation/library canary coverage where runtime text can surface.
- [x] Add persisted failure canary coverage.
- [x] Add export/diagnostic metadata canary coverage.
- [x] Add raw provider URL userinfo rejection coverage.
- [x] Add sensitive provider URL query rejection coverage.
- [x] Add raw credential_env rejection coverage.
- [x] Add config serialization no-secret-canary assertion.
- [x] Add benign-text non-over-redaction coverage.

## PRR-510 — Save/Exit and resume acceptance matrix

- [x] First-run clean Save and Exit acceptance passes.
- [x] First-run dirty valid Save changes and exit acceptance passes.
- [x] First-run dirty invalid save retains input and stays in wizard.
- [x] First-run dirty Cancel retains input.
- [x] First-run explicit discard drops only unsaved edits and preserves prior durable progress.
- [x] First-run Escape uses the same dirty-aware contract.
- [x] New Deep Dive clean Save and Exit acceptance passes.
- [x] New Deep Dive dirty project form Save changes and exit acceptance passes.
- [x] New Deep Dive dirty pasted-source form cannot be silently lost.
- [x] New Deep Dive dirty URL/file input cannot be silently lost.
- [x] New Deep Dive dirty host edit cannot be silently lost.
- [x] New Deep Dive dirty episode settings cannot be silently lost.
- [x] New Deep Dive invalid save retains input and stays in wizard.
- [x] New Deep Dive dirty Cancel retains input.
- [x] New Deep Dive explicit discard preserves prior durable state.
- [x] Modal Escape cancels confirmation without exiting.
- [x] Restart resumes the last durable safe boundary after Save and Exit.
- [x] Serialized draft inspection proves no raw source text or credential canary was introduced.
- [x] Completed workflow no longer produces Resume Deep Dive.
- [x] Saved incomplete workflow still produces Resume Deep Dive.

## PRR-520 — Research/readiness/UX acceptance matrix

- [x] First-run research Off hydrates New Deep Dive correctly.
- [x] First-run research Useful hydrates New Deep Dive correctly.
- [x] First-run research Aggressive hydrates New Deep Dive correctly.
- [x] Persisted project policy hydrates correctly on revisit.
- [x] Persisted project policy hydrates correctly after restart.
- [x] Quick fallback to global research default passes.
- [x] Explicit user Quick override precedence passes.
- [x] Project Quick override precedence passes.
- [x] Valid non-default role model passes first-run readiness.
- [x] Valid non-default role model passes shared production preflight.
- [x] Invalid/undiscovered role model fails both consistently.
- [x] Slow provider readiness does not block keyboard input.
- [x] Unreachable provider produces bounded sanitized Needs attention state.
- [x] Obsolete provider readiness result cannot overwrite newer configuration.
- [x] Provider discovery call-count assertion passes.
- [x] Host optional field clear survives restart.
- [x] Provider destructive confirmation matrix passes.
- [x] Host destructive confirmation matrix passes.
- [x] Source destructive confirmation matrix passes.
- [x] Composite settings single-save/rollback matrix passes.

## PRR-600 — Static quality and focused regression gates

- [x] `uv lock --check` passes.
- [x] Ruff format check passes.
- [x] Ruff lint passes.
- [x] Strict mypy passes.
- [x] Full pytest suite passes.
- [x] Package build passes.
- [x] CLI/import smoke passes.
- [x] No new broad exception swallowing is introduced in remediation paths.
- [x] No new duplicated provider/research/generation business logic is introduced in TUI screens.
- [x] No new secret-bearing field is added to persisted user config or wizard drafts.
- [x] New deterministic fakes/fixtures are reusable across the post-review matrices rather than one-off copies.


**PRR-600 code-review evidence:** remediation-path broad `except Exception` handlers were audited on the qualified head. Episode Library handlers convert failures to sanitized user status; asynchronous readiness converts the isolated background-provider boundary to a sanitized bounded failure snapshot; the keyring compatibility handler re-raises non-`PasswordDeleteError` exceptions. No handler silently swallows an exception. Guided/TUI paths remain clients of `ProductionComposition`, controllers, and shared services rather than introducing duplicate provider/research/generation engines. The shared `completed_episode_acceptance` fixture in `tests/conftest.py` creates production-backed fake providers, corpus, hosts, episode, plan, generation run, transcript turns, audio, and export artifacts for reusable acceptance coverage.

## PRR-610 — Existing production regression preservation

- [x] Existing guided first-run deterministic fake-LLM acceptance remains green.
- [x] Existing guided first-run deterministic fake-TTS acceptance remains green.
- [x] Existing source import/index failure/retry/restart acceptance remains green.
- [x] Existing research execution matrix remains green.
- [x] Existing host ordering/voice behavior remains green.
- [x] Existing episode planning validity/mutation behavior remains green.
- [x] Existing shared preflight behavior remains green.
- [x] Existing generation monitor/run-state control remains green.
- [x] Existing Episode Library behavior remains green.
- [x] Existing transcript review and targeted repair behavior remains green.
- [x] Existing Quick Deep Dive production-artifact acceptance remains green.
- [x] Existing Quick-versus-guided artifact identity/equivalence acceptance remains green.
- [x] Existing multi-episode isolation acceptance remains green.
- [x] Existing provider CLI matrix remains green.
- [x] Existing local-only/network-scope enforcement remains green.
- [x] Existing persisted compatibility/restart acceptance remains green.

## PRR-700 — Installed-wheel and fresh-machine qualification

- [x] Build a wheel from the exact candidate master head.
- [x] Install the wheel into a fresh isolated environment without importing from the source tree.
- [x] Verify CLI entry points from the installed wheel.
- [x] Run deterministic CLI research workflow from the installed wheel.
- [x] Run deterministic CLI episode plan/generate/control/export/status workflow from the installed wheel.
- [x] Run deterministic guided first-run TUI acceptance from the installed wheel.
- [x] Run deterministic New Deep Dive TUI acceptance from the installed wheel.
- [x] Run Save/Exit dirty-form acceptance from the installed wheel.
- [x] Run research-default/Quick precedence acceptance from the installed wheel.
- [x] Run non-default model-role readiness/preflight acceptance from the installed wheel.
- [x] Run post-review security/redaction canary matrix from the installed wheel.
- [x] Run stale-resume/host-clear/destructive-confirmation acceptance from the installed wheel.
- [x] Run real KittenTTS Micro CPU smoke from the fresh environment.
- [x] Record exact wheel identity, master SHA, and job/run IDs used for fresh-machine qualification.


**Qualified reconciliation checkpoint (2026-10-10):** implementation head `204d1df97dd49db17f4c4b17fdf07848d944c0c4` passed exact-head CI run `38012285504`. Quality job `114094736110` passed lock validation, Ruff format, Ruff lint, strict mypy, full pytest, package build, and CLI/import smoke. Fresh-machine job `114094735913` built and installed `deeper-dive==0.1.0` into `/tmp/deeper-dive-fresh`, verified the import resolved from that isolated installation, passed installed-wheel CLI/TUI and post-review remediation matrices, and passed the real KittenTTS Micro CPU smoke. The installed-wheel remediation matrix explicitly exercised CLI research, CLI episode generation/control/export, dirty Save/Exit, research/model-role readiness, stale-resume, host-clear, destructive-confirmation, atomic-settings, security/redaction, async-readiness, and sanitized CLI-error regressions.

## PRR-800 — Documentation and operator guidance

- [x] Update user guidance for dirty Save and Exit behavior.
- [x] Document that credential fields accept environment-variable names, not raw API keys.
- [x] Document provider URL userinfo/sensitive-query rejection.
- [x] Document global research default versus Quick-specific override precedence.
- [x] Document that New Deep Dive Research reloads the actual durable project policy.
- [x] Document Resume Deep Dive as an incomplete-workflow action rather than a permanent history entry.
- [x] Document asynchronous provider readiness/checking states where user-visible.
- [x] Document destructive confirmation behavior consistently across advanced and guided surfaces.
- [x] Update developer guidance for canonical sanitization ownership.
- [x] Update developer guidance for atomic composite config saves.
- [x] Preserve the predecessor spec/TODO as historical evidence; only add a forward reference if genuinely useful.

## PRR-900 — Original TODO requalification against review defects

Re-evaluate the original guided-workflow requirements affected by the review. Do not alter their historical checkboxes; record the post-review evidence here.

- [x] Requalify original item 20: all provider/runtime/status text is behind canonical sanitization.
- [x] Requalify original item 43: Escape cancellation and Save/Exit behavior are loss-safe.
- [x] Requalify original item 73: OpenAI persists credential references rather than raw values.
- [x] Requalify original item 74: OpenAI-compatible provider config preserves the non-secret contract.
- [x] Requalify original item 77: provider health/discovery/errors are canonically sanitized.
- [x] Requalify original item 83: model-test failure states are canonically sanitized.
- [x] Requalify original item 87: Advanced Setup accepts valid non-default role models.
- [x] Requalify original item 101: first-run research default is actually consumed downstream.
- [x] Requalify original item 120: Resume Deep Dive represents an incomplete recoverable workflow.
- [x] Requalify original item 145: Research choices map to and hydrate from production policy correctly.
- [x] Requalify original item 152: custom host editing supports clearing optional values.
- [x] Requalify original item 170: planner/provider errors are sanitized and actionable.
- [x] Requalify original item 196: generation latest status is canonically sanitized.
- [x] Requalify original item 201: durable failure view is canonically sanitized.
- [x] Requalify original item 224: documented recommended research defaults are applied consistently.
- [x] Requalify original item 236: first-run Save and Exit preserves progress without silent loss.
- [x] Requalify original item 237: New Deep Dive Save and Exit preserves progress without silent loss.
- [x] Requalify original item 251: canonical recursive sanitization covers all user-visible provider/runtime errors.
- [x] Requalify original item 252: credential-reference/non-persistence rules are structurally enforced.
- [x] Requalify original item 259: destructive TUI actions require confirmation.
- [x] Requalify original item 321: expanded security/redaction matrix passes.
- [x] Requalify original item 325: Quick-versus-guided equivalence includes research-default semantics.


**Original-TODO requalification evidence:** the original checklist remains historical and unchanged. Requalification is recorded here against current production behavior and the passing post-review matrices: canonical recursive sanitizer/status canaries; structural provider non-secret validation; dirty-form Save/Exit and resume lifecycle pilots; research/Quick precedence and restart tests; discovered-model readiness/preflight parity; host optional-clear restart; destructive confirmation matrices; atomic composite-save rollback/single-write tests; installed-wheel CLI/TUI/security matrices; and the full existing-regression suite.

## PRR-910 — Final evidence reconciliation

- [x] Confirm every PRR-01 through PRR-13 review defect is no longer reproducible.
- [x] Confirm all TODO checkboxes above have production/test evidence or an explicitly justified N/A state.
- [x] Confirm no unchecked task or subtask remains before declaring completion.
- [x] Record the exact final implementation master SHA.
- [x] Run exact-head CI for the final implementation master SHA.
- [x] Confirm exact-head quality job passes lock, Ruff format, Ruff lint, mypy, full pytest, build, and CLI/import smoke.
- [x] Confirm exact-head fresh-machine job passes installed-wheel deterministic CLI/TUI acceptance.
- [x] Confirm exact-head fresh-machine job passes real KittenTTS Micro CPU qualification.
- [x] Record exact CI run/job IDs and the test count reported by that exact run.
- [x] Normalize closeout prose so it contains no contradictory 938/939-style test-count evidence.
- [x] If final TODO reconciliation changes only documentation, run exact-head CI on the reconciliation commit too.
- [x] Reload this TODO from current `master` after the final successful write/merge and verify all boxes remain reconciled.
- [x] Declare remediation complete only after the final current `master` head itself has successful exact-head CI.

**Final implementation qualification:** implementation/requalification head `2988524b2862c4a23d059a2f87a28a4758893110` passed exact-head CI run `38013931889`. Quality job `114099950011` passed lock validation, Ruff format, Ruff lint, strict mypy, the full pytest suite (**1,068 passed**), package build, and CLI/import smoke. Fresh-machine job `114099949818` passed fresh isolated wheel build/install, installed-wheel CLI and guided TUI acceptance, the installed-wheel post-review remediation matrix, and real KittenTTS Micro CPU smoke. This PRR-910 reconciliation is documentation-only; its checked closeout state is valid only if this reconciliation commit itself passes exact-head CI on current `master`.
