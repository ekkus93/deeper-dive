# Deeper Dive TUI Guided Workflow Post-Review Remediation TODO

**Created:** 2026-10-09  
**Status:** Open — post-review remediation required  
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

- [ ] Reload the post-review spec/TODO and confirm the current `master` SHA before implementation.
- [ ] Confirm the predecessor TODO remains unchanged as historical evidence.
- [ ] Add or retain a review-baseline note tying this remediation to reviewed SHA `87208a607def3e78e3466382b5aa33ea49c685b3` without treating that SHA as the final implementation head.
- [ ] Reproduce the Basic Authorization leak with a deterministic test before changing the sanitizer.
- [ ] Reproduce the Token Authorization leak with a deterministic test before changing the sanitizer.
- [ ] Reproduce the Digest Authorization leak with a deterministic test before changing the sanitizer.
- [ ] Reproduce raw `credential_env` persistence with a deterministic validation/persistence test.
- [ ] Reproduce provider URL userinfo persistence with a deterministic validation/persistence test.
- [ ] Reproduce dirty Save-and-Exit data loss in first-run with a Textual pilot test.
- [ ] Reproduce dirty Save-and-Exit data loss in New Deep Dive with a Textual pilot test.
- [ ] Reproduce the first-run research default -> Quick Deep Dive mismatch.
- [ ] Reproduce the New Deep Dive Research selector hydration mismatch.
- [ ] Reproduce rejection of a valid non-default discovered role model.
- [ ] Reproduce stale Resume Deep Dive after successful workflow completion.
- [ ] Reproduce host optional role/instructions clear failure.
- [ ] Add deterministic evidence for at least one advanced destructive action that currently executes without confirmation.
- [ ] Add deterministic evidence that one logical multi-default save currently performs multiple durable config writes.

## PRR-100 — Canonical authorization and recursive sanitization

- [ ] Define one canonical public sanitization API for user-visible/loggable diagnostic text and recursive structures.
- [ ] Redact the entire value of `Authorization:` headers regardless of authentication scheme.
- [ ] Redact the entire value of `authorization=` assignment forms regardless of authentication scheme.
- [ ] Preserve Bearer-token redaction while fixing Basic/Token/Digest behavior.
- [ ] Handle mixed/lower/upper-case Authorization field names.
- [ ] Handle quoted Authorization values.
- [ ] Handle JSON-like Authorization values.
- [ ] Handle multiline strings containing Authorization values.
- [ ] Handle multiple sensitive values in one message.
- [ ] Preserve existing API-key/token/password secret-key redaction behavior.
- [ ] Apply the canonical sanitizer recursively to dict values.
- [ ] Apply the canonical sanitizer recursively to list/tuple values.
- [ ] Apply the canonical sanitizer to chained/nested exception messages before presentation.
- [ ] Ensure sanitizer output never includes the Basic credential payload canary.
- [ ] Ensure sanitizer output never includes the Token credential payload canary.
- [ ] Ensure sanitizer output never includes the Digest credential payload canary.
- [ ] Add benign-text regressions proving ordinary words such as `tokenization`, model names, URLs without secrets, and status prose are not unnecessarily destroyed.

## PRR-110 — Provider configuration non-secret validation

- [ ] Validate non-empty `credential_env` as `[A-Za-z_][A-Za-z0-9_]*` after trimming.
- [ ] Reject raw API-key/token-like strings supplied as `credential_env`.
- [ ] Reject whitespace-bearing credential references.
- [ ] Reject punctuation-bearing values that cannot be environment-variable identifiers.
- [ ] Preserve valid existing environment-variable references.
- [ ] Parse provider `base_url` structurally rather than validating scheme by prefix alone.
- [ ] Continue to require HTTP/HTTPS URLs.
- [ ] Reject URL username/userinfo.
- [ ] Reject URL password/userinfo.
- [ ] Reject known sensitive query parameters case-insensitively (`api_key`, `apikey`, `key`, `token`, `access_token`, `auth`, `authorization`, `password`, `secret`).
- [ ] Keep valid Ollama, llama-server, OpenAI, OpenAI-compatible LLM, OpenAI TTS, OpenAI-compatible TTS, and ElevenLabs endpoints working.
- [ ] Ensure provider validation errors do not echo rejected credential material.
- [ ] Ensure invalid secret-bearing provider config cannot be written by first-run.
- [ ] Ensure invalid secret-bearing provider config cannot be written by the advanced Providers screen.
- [ ] Ensure invalid secret-bearing provider config cannot be written through any CLI/config mutation path.
- [ ] Inspect serialized `config.json` bytes in tests and prove raw credential canaries are absent.
- [ ] Keep runtime credential lookup environment-reference based in provider factories.
- [ ] Define and test safe failure behavior for a pre-existing invalid secret-bearing config.

## PRR-120 — Cross-surface sanitization enforcement

- [ ] Inventory every TUI `_status`, error, details, health, discovery, failure, traceback, and provider-message presentation path.
- [ ] Route `hosts_screen.py` provider health/error text through canonical sanitization.
- [ ] Route Providers screen provider/runtime errors through canonical sanitization.
- [ ] Route Settings screen runtime/readiness errors through canonical sanitization.
- [ ] Route Research screen external/provider errors through canonical sanitization.
- [ ] Route plan/planner screens through canonical sanitization.
- [ ] Route transcript/review/repair surfaces through canonical sanitization.
- [ ] Route preflight and generation monitor failure/status text through canonical sanitization.
- [ ] Route Episode Library/export failure/status text through canonical sanitization.
- [ ] Route guided first-run provider/model/TTS failures through canonical sanitization.
- [ ] Route guided New Deep Dive source/research/host/plan/generation failures through canonical sanitization.
- [ ] Route CLI command/provider errors through the same canonical behavior.
- [ ] Route persisted failure presentation through the same canonical behavior.
- [ ] Route debug/diagnostic/export metadata through recursive canonical sanitization.
- [ ] Add a test helper/canary assertion that fails if any configured secret canary appears in rendered TUI text.
- [ ] Add a test helper/canary assertion that fails if any configured secret canary appears in CLI output.

## PRR-200 — Shared dirty-form and safe-exit contract

- [ ] Define a shared dirty-form protocol/contract usable by both guided wizards.
- [ ] Compare current editable controls to their last successfully loaded/persisted values deterministically.
- [ ] Mark first-run provider configuration dirty when relevant fields change.
- [ ] Mark first-run model/default controls dirty when relevant fields change.
- [ ] Mark first-run speech/voice/default controls dirty when relevant fields change.
- [ ] Mark New Deep Dive project setup dirty when relevant fields change.
- [ ] Mark pasted-source form dirty while title/body contains unsaved text.
- [ ] Mark file/folder and URL source inputs dirty while unsaved text is present.
- [ ] Mark research choice dirty when changed from the currently durable/effective policy.
- [ ] Mark host create/edit form dirty when changed from durable host state.
- [ ] Mark episode settings dirty when changed from durable episode configuration.
- [ ] Mark any other guided editable form dirty where exiting can otherwise lose user input.
- [ ] Make clean Save and Exit checkpoint and exit without unnecessary confirmation.
- [ ] Make dirty Save and Exit open an explicit confirmation instead of discarding edits.
- [ ] Provide a Save changes and exit action through the normal production save/validation path.
- [ ] Provide an explicit Exit without unsaved changes action.
- [ ] Provide Cancel/continue-editing action.
- [ ] Ensure destructive discard is not the default-focused confirmation action.
- [ ] On save validation failure, remain on the same screen with entered values intact.
- [ ] On production save failure, remain on the same screen with entered values intact.
- [ ] On explicit discard, preserve previously durable production state.
- [ ] Preserve the last safe wizard checkpoint when unsaved edits are explicitly discarded.
- [ ] Make non-modal Escape invoke the same dirty-aware safe-exit flow.
- [ ] Make Escape inside the confirmation modal cancel/close the modal.
- [ ] Prevent key-repeat/double-submit from executing save/discard twice.

## PRR-210 — Wizard draft security and lifecycle

- [ ] Keep raw provider credentials out of wizard draft serialization.
- [ ] Keep pasted source body text out of wizard draft serialization.
- [ ] Keep other production business records out of wizard draft serialization.
- [ ] If new UI-only draft fields are required, explicitly allowlist and version them.
- [ ] Keep the guided draft size bound enforced.
- [ ] Keep atomic temp-file + fsync + replace semantics for draft writes.
- [ ] Keep symlink rejection for draft loads.
- [ ] Add a symlink-safe `clear(kind)` operation to `GuidedDraftStore`.
- [ ] Clear First-run draft when setup reaches its defined completed boundary.
- [ ] Clear New Deep Dive draft when the guided workflow reaches its defined terminal completed boundary.
- [ ] Clear the appropriate draft after explicit confirmed abandonment.
- [ ] Retain the draft on normal Save and Exit.
- [ ] Retain the draft on recoverable validation/provider/runtime failure.
- [ ] Retain the draft while generation is in progress when resume is meaningful.
- [ ] Invalidate/recover stale drafts whose referenced project/episode/run identities are no longer usable.
- [ ] Make `has_resume()` reflect recoverable incomplete state rather than mere file existence.
- [ ] Ensure Home removes Resume Deep Dive after successful completion.
- [ ] Ensure Home retains Resume Deep Dive after an intentionally saved incomplete workflow.
- [ ] Ensure draft clearing cannot delete an unrelated file through symlink/path manipulation.

## PRR-300 — Research default, hydration, and Quick parity

- [ ] Document global New Deep Dive research precedence in code-facing documentation/tests.
- [ ] Initialize a new project's Research selector from user-level `research_policy` when no project policy exists.
- [ ] Hydrate the Research selector from an existing durable project policy on revisit.
- [ ] Hydrate the Research selector from durable project policy after restart/resume.
- [ ] Do not overwrite an existing project policy merely by opening/revisiting the screen.
- [ ] Keep Save Research Choice routed through the production research controller/store.
- [ ] Define Quick Deep Dive precedence as project Quick override > explicit user Quick override > user `research_policy` > built-in Useful.
- [ ] Update `QuickDeepDiveService` to fall back to `research_policy` when no explicit Quick research override exists.
- [ ] Preserve explicit `quick_deep_dive_research_policy` behavior.
- [ ] Preserve project Quick Deep Dive research override behavior.
- [ ] Make first-run `research_policy` affect subsequent New Deep Dive by default.
- [ ] Make first-run `research_policy` affect Quick Deep Dive when no more-specific Quick override exists.
- [ ] Test Off across first-run -> New Deep Dive.
- [ ] Test Useful across first-run -> New Deep Dive.
- [ ] Test Aggressive across first-run -> New Deep Dive.
- [ ] Test Off across first-run/global -> Quick Deep Dive fallback.
- [ ] Test Aggressive across first-run/global -> Quick Deep Dive fallback.
- [ ] Test explicit user Quick override beats global research default.
- [ ] Test project Quick override beats user Quick/global defaults.
- [ ] Test research policy behavior after process restart.

## PRR-310 — Model-role readiness parity

- [ ] Remove the requirement that a valid assigned role model equal `provider.default_model`.
- [ ] Validate assigned model existence against the provider discovery snapshot.
- [ ] Keep provider capability validation for role assignments.
- [ ] Keep provider health/readiness validation for role assignments.
- [ ] Align first-run role readiness with the production preflight compatibility policy.
- [ ] Add a provider with default model A and discovered model B fixture.
- [ ] Prove a role assigned to valid discovered model B passes first-run readiness.
- [ ] Prove the same role/model passes production preflight.
- [ ] Prove an undiscovered model fails first-run readiness.
- [ ] Prove the same undiscovered model fails production preflight consistently.
- [ ] Preserve restart/reload of non-default role assignments.

## PRR-320 — Non-blocking provider readiness and discovery

- [ ] Inventory synchronous provider `health()`, `models()`, and `voices()` calls reachable from Textual mount/navigation/readiness paths.
- [ ] Move potentially blocking first-run provider probes off the Textual UI event loop.
- [ ] Move potentially blocking Home/setup-readiness provider probes off the Textual UI event loop.
- [ ] Keep keyboard navigation responsive while provider readiness is checking.
- [ ] Render an explicit Checking state while asynchronous readiness is pending.
- [ ] Render Ready/Needs attention from the completed bounded snapshot.
- [ ] Render sanitized actionable failure state on timeout/unreachable provider.
- [ ] Prevent obsolete worker results from overwriting newer provider configuration/readiness state.
- [ ] Coalesce or safely supersede duplicate readiness refreshes.
- [ ] Reuse one model-discovery result within a readiness refresh where possible.
- [ ] Eliminate the OpenAI health-plus-immediate-second-models discovery pattern from one readiness refresh.
- [ ] Preserve configured timeout/retry policy without blocking UI input.
- [ ] Add a deterministic slow-provider fake that blocks until released by the test.
- [ ] Prove Textual pilot input/navigation remains responsive while the slow provider probe is pending.
- [ ] Add unreachable-provider readiness coverage without real network access.
- [ ] Add stale-result race coverage by changing provider config while an older probe is pending.
- [ ] Assert bounded provider-call counts per readiness refresh.

## PRR-400 — Guided host edit completeness

- [ ] Define required versus optional guided host fields.
- [ ] Keep required host fields validated against blank values.
- [ ] Treat blank optional role as an explicit clear during edit.
- [ ] Treat blank optional instructions as an explicit clear during edit.
- [ ] Route clearing through the existing host production service/repository path.
- [ ] Refresh the guided host card/summary after clearing.
- [ ] Prove cleared role survives restart.
- [ ] Prove cleared instructions survive restart.
- [ ] Preserve normal custom-host creation defaults where documented.

## PRR-410 — Consistent destructive-action confirmations

- [ ] Define one reusable confirmation interaction/pattern for destructive TUI actions.
- [ ] Require confirmation before advanced provider removal.
- [ ] Require confirmation before advanced host removal.
- [ ] Require confirmation before advanced source deletion.
- [ ] Preserve confirmation before guided source deletion.
- [ ] Preserve confirmation before project deletion.
- [ ] Preserve confirmation before generation cancellation where applicable.
- [ ] Confirmation text identifies the selected target using friendly identity.
- [ ] Confirmation is keyboard accessible.
- [ ] Default action is cancel/non-destructive.
- [ ] Changing the selected provider clears pending provider-delete confirmation.
- [ ] Changing the selected host clears pending host-delete confirmation.
- [ ] Changing the selected source clears pending source-delete confirmation.
- [ ] Repeated key/button events cannot execute a destructive mutation twice.
- [ ] Cancel leaves durable state unchanged.
- [ ] Confirm still routes through the existing production delete/remove service/controller.

## PRR-420 — Atomic composite settings/default saves

- [ ] Add a controller/service helper that validates and saves a complete candidate `UserConfig` once.
- [ ] Avoid repeated `UserConfigStore.save()` calls for one logical multi-field user action.
- [ ] Make TTS provider + voice default save atomic.
- [ ] Make research + network default save atomic.
- [ ] Make Quick Deep Dive duration + host presets + research default save atomic.
- [ ] Make runtime/readiness default save atomic.
- [ ] Make first-run Host 1/Host 2 voice/default bundle save atomic.
- [ ] Make other first-run multi-default button actions atomic where currently split across repeated `set_default()` calls.
- [ ] Validate all candidate values before mutating durable config.
- [ ] On validation failure, retain previous in-memory and durable config.
- [ ] On simulated filesystem save failure, retain previous durable config.
- [ ] Preserve owner-only file permissions after successful config save.
- [ ] Add a counting config-store fake proving one durable save per logical action.
- [ ] Add byte-level/semantic rollback assertions for failed composite saves.

## PRR-500 — Expanded security/redaction acceptance matrix

- [ ] Add Basic Authorization canary coverage to direct sanitizer tests.
- [ ] Add Token Authorization canary coverage to direct sanitizer tests.
- [ ] Add Digest Authorization canary coverage to direct sanitizer tests.
- [ ] Add mixed-case Authorization canary coverage.
- [ ] Add quoted and JSON-like Authorization canary coverage.
- [ ] Add multiline/multiple-secret sanitizer coverage.
- [ ] Add nested mapping/list/tuple sanitizer coverage.
- [ ] Add chained-exception sanitizer coverage.
- [ ] Add CLI error-output canary coverage.
- [ ] Add advanced TUI host/provider/settings/research canary coverage.
- [ ] Add guided first-run canary coverage.
- [ ] Add guided New Deep Dive canary coverage.
- [ ] Add plan/transcript/repair/generation/library canary coverage where runtime text can surface.
- [ ] Add persisted failure canary coverage.
- [ ] Add export/diagnostic metadata canary coverage.
- [ ] Add raw provider URL userinfo rejection coverage.
- [ ] Add sensitive provider URL query rejection coverage.
- [ ] Add raw credential_env rejection coverage.
- [ ] Add config serialization no-secret-canary assertion.
- [ ] Add benign-text non-over-redaction coverage.

## PRR-510 — Save/Exit and resume acceptance matrix

- [ ] First-run clean Save and Exit acceptance passes.
- [ ] First-run dirty valid Save changes and exit acceptance passes.
- [ ] First-run dirty invalid save retains input and stays in wizard.
- [ ] First-run dirty Cancel retains input.
- [ ] First-run explicit discard drops only unsaved edits and preserves prior durable progress.
- [ ] First-run Escape uses the same dirty-aware contract.
- [ ] New Deep Dive clean Save and Exit acceptance passes.
- [ ] New Deep Dive dirty project form Save changes and exit acceptance passes.
- [ ] New Deep Dive dirty pasted-source form cannot be silently lost.
- [ ] New Deep Dive dirty URL/file input cannot be silently lost.
- [ ] New Deep Dive dirty host edit cannot be silently lost.
- [ ] New Deep Dive dirty episode settings cannot be silently lost.
- [ ] New Deep Dive invalid save retains input and stays in wizard.
- [ ] New Deep Dive dirty Cancel retains input.
- [ ] New Deep Dive explicit discard preserves prior durable state.
- [ ] Modal Escape cancels confirmation without exiting.
- [ ] Restart resumes the last durable safe boundary after Save and Exit.
- [ ] Serialized draft inspection proves no raw source text or credential canary was introduced.
- [ ] Completed workflow no longer produces Resume Deep Dive.
- [ ] Saved incomplete workflow still produces Resume Deep Dive.

## PRR-520 — Research/readiness/UX acceptance matrix

- [ ] First-run research Off hydrates New Deep Dive correctly.
- [ ] First-run research Useful hydrates New Deep Dive correctly.
- [ ] First-run research Aggressive hydrates New Deep Dive correctly.
- [ ] Persisted project policy hydrates correctly on revisit.
- [ ] Persisted project policy hydrates correctly after restart.
- [ ] Quick fallback to global research default passes.
- [ ] Explicit user Quick override precedence passes.
- [ ] Project Quick override precedence passes.
- [ ] Valid non-default role model passes first-run readiness.
- [ ] Valid non-default role model passes shared production preflight.
- [ ] Invalid/undiscovered role model fails both consistently.
- [ ] Slow provider readiness does not block keyboard input.
- [ ] Unreachable provider produces bounded sanitized Needs attention state.
- [ ] Obsolete provider readiness result cannot overwrite newer configuration.
- [ ] Provider discovery call-count assertion passes.
- [ ] Host optional field clear survives restart.
- [ ] Provider destructive confirmation matrix passes.
- [ ] Host destructive confirmation matrix passes.
- [ ] Source destructive confirmation matrix passes.
- [ ] Composite settings single-save/rollback matrix passes.

## PRR-600 — Static quality and focused regression gates

- [ ] `uv lock --check` passes.
- [ ] Ruff format check passes.
- [ ] Ruff lint passes.
- [ ] Strict mypy passes.
- [ ] Full pytest suite passes.
- [ ] Package build passes.
- [ ] CLI/import smoke passes.
- [ ] No new broad exception swallowing is introduced in remediation paths.
- [ ] No new duplicated provider/research/generation business logic is introduced in TUI screens.
- [ ] No new secret-bearing field is added to persisted user config or wizard drafts.
- [ ] New deterministic fakes/fixtures are reusable across the post-review matrices rather than one-off copies.

## PRR-610 — Existing production regression preservation

- [ ] Existing guided first-run deterministic fake-LLM acceptance remains green.
- [ ] Existing guided first-run deterministic fake-TTS acceptance remains green.
- [ ] Existing source import/index failure/retry/restart acceptance remains green.
- [ ] Existing research execution matrix remains green.
- [ ] Existing host ordering/voice behavior remains green.
- [ ] Existing episode planning validity/mutation behavior remains green.
- [ ] Existing shared preflight behavior remains green.
- [ ] Existing generation monitor/run-state control remains green.
- [ ] Existing Episode Library behavior remains green.
- [ ] Existing transcript review and targeted repair behavior remains green.
- [ ] Existing Quick Deep Dive production-artifact acceptance remains green.
- [ ] Existing Quick-versus-guided artifact identity/equivalence acceptance remains green.
- [ ] Existing multi-episode isolation acceptance remains green.
- [ ] Existing provider CLI matrix remains green.
- [ ] Existing local-only/network-scope enforcement remains green.
- [ ] Existing persisted compatibility/restart acceptance remains green.

## PRR-700 — Installed-wheel and fresh-machine qualification

- [ ] Build a wheel from the exact candidate master head.
- [ ] Install the wheel into a fresh isolated environment without importing from the source tree.
- [ ] Verify CLI entry points from the installed wheel.
- [ ] Run deterministic CLI research workflow from the installed wheel.
- [ ] Run deterministic CLI episode plan/generate/control/export/status workflow from the installed wheel.
- [ ] Run deterministic guided first-run TUI acceptance from the installed wheel.
- [ ] Run deterministic New Deep Dive TUI acceptance from the installed wheel.
- [ ] Run Save/Exit dirty-form acceptance from the installed wheel.
- [ ] Run research-default/Quick precedence acceptance from the installed wheel.
- [ ] Run non-default model-role readiness/preflight acceptance from the installed wheel.
- [ ] Run post-review security/redaction canary matrix from the installed wheel.
- [ ] Run stale-resume/host-clear/destructive-confirmation acceptance from the installed wheel.
- [ ] Run real KittenTTS Micro CPU smoke from the fresh environment.
- [ ] Record exact wheel identity, master SHA, and job/run IDs used for fresh-machine qualification.

## PRR-800 — Documentation and operator guidance

- [ ] Update user guidance for dirty Save and Exit behavior.
- [ ] Document that credential fields accept environment-variable names, not raw API keys.
- [ ] Document provider URL userinfo/sensitive-query rejection.
- [ ] Document global research default versus Quick-specific override precedence.
- [ ] Document that New Deep Dive Research reloads the actual durable project policy.
- [ ] Document Resume Deep Dive as an incomplete-workflow action rather than a permanent history entry.
- [ ] Document asynchronous provider readiness/checking states where user-visible.
- [ ] Document destructive confirmation behavior consistently across advanced and guided surfaces.
- [ ] Update developer guidance for canonical sanitization ownership.
- [ ] Update developer guidance for atomic composite config saves.
- [ ] Preserve the predecessor spec/TODO as historical evidence; only add a forward reference if genuinely useful.

## PRR-900 — Original TODO requalification against review defects

Re-evaluate the original guided-workflow requirements affected by the review. Do not alter their historical checkboxes; record the post-review evidence here.

- [ ] Requalify original item 20: all provider/runtime/status text is behind canonical sanitization.
- [ ] Requalify original item 43: Escape cancellation and Save/Exit behavior are loss-safe.
- [ ] Requalify original item 73: OpenAI persists credential references rather than raw values.
- [ ] Requalify original item 74: OpenAI-compatible provider config preserves the non-secret contract.
- [ ] Requalify original item 77: provider health/discovery/errors are canonically sanitized.
- [ ] Requalify original item 83: model-test failure states are canonically sanitized.
- [ ] Requalify original item 87: Advanced Setup accepts valid non-default role models.
- [ ] Requalify original item 101: first-run research default is actually consumed downstream.
- [ ] Requalify original item 120: Resume Deep Dive represents an incomplete recoverable workflow.
- [ ] Requalify original item 145: Research choices map to and hydrate from production policy correctly.
- [ ] Requalify original item 152: custom host editing supports clearing optional values.
- [ ] Requalify original item 170: planner/provider errors are sanitized and actionable.
- [ ] Requalify original item 196: generation latest status is canonically sanitized.
- [ ] Requalify original item 201: durable failure view is canonically sanitized.
- [ ] Requalify original item 224: documented recommended research defaults are applied consistently.
- [ ] Requalify original item 236: first-run Save and Exit preserves progress without silent loss.
- [ ] Requalify original item 237: New Deep Dive Save and Exit preserves progress without silent loss.
- [ ] Requalify original item 251: canonical recursive sanitization covers all user-visible provider/runtime errors.
- [ ] Requalify original item 252: credential-reference/non-persistence rules are structurally enforced.
- [ ] Requalify original item 259: destructive TUI actions require confirmation.
- [ ] Requalify original item 321: expanded security/redaction matrix passes.
- [ ] Requalify original item 325: Quick-versus-guided equivalence includes research-default semantics.

## PRR-910 — Final evidence reconciliation

- [ ] Confirm every PRR-01 through PRR-13 review defect is no longer reproducible.
- [ ] Confirm all TODO checkboxes above have production/test evidence or an explicitly justified N/A state.
- [ ] Confirm no unchecked task or subtask remains before declaring completion.
- [ ] Record the exact final implementation master SHA.
- [ ] Run exact-head CI for the final implementation master SHA.
- [ ] Confirm exact-head quality job passes lock, Ruff format, Ruff lint, mypy, full pytest, build, and CLI/import smoke.
- [ ] Confirm exact-head fresh-machine job passes installed-wheel deterministic CLI/TUI acceptance.
- [ ] Confirm exact-head fresh-machine job passes real KittenTTS Micro CPU qualification.
- [ ] Record exact CI run/job IDs and the test count reported by that exact run.
- [ ] Normalize closeout prose so it contains no contradictory 938/939-style test-count evidence.
- [ ] If final TODO reconciliation changes only documentation, run exact-head CI on the reconciliation commit too.
- [ ] Reload this TODO from current `master` after the final successful write/merge and verify all boxes remain reconciled.
- [ ] Declare remediation complete only after the final current `master` head itself has successful exact-head CI.
