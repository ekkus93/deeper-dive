# Deeper Dive TUI Guided Workflow Post-Review Remediation Spec

**Created:** 2026-10-09  
**Status:** Proposed remediation contract  
**Reviewed baseline:** `87208a607def3e78e3466382b5aa33ea49c685b3`  
**Companion checklist:** `docs/DEEP_DIVE_TUI_GUIDED_WORKFLOW_POST_REVIEW_REMEDIATION_TODO_2026-10-09.md`  
**Predecessor:** `docs/DEEP_DIVE_TUI_GUIDED_WORKFLOW_TODO_2026-10-08.md`  
**Original guided-workflow authority:** `docs/DEEP_DIVE_TUI_GUIDED_WORKFLOW_SPEC_2026-10-08.md`

This specification defines the post-review remediation required after an independent source audit of the completed 2026-10-08 guided-workflow checklist. The original checklist remains historical evidence and must not be rewritten to hide defects discovered after qualification. This document and its companion TODO are the authoritative contract for correcting those defects.

The review found that the implementation is broadly sound and that the original CI gates were substantial, but several edge cases violated the normative guided-workflow contract despite 270/270 original TODO boxes being checked. The most important defects are credential-redaction gaps, secret-persistence gaps, and Save-and-Exit behavior that can discard unsaved form edits without confirmation.

## 1. Goals

The remediation must:

1. Restore the original guided-workflow security guarantees across TUI, CLI, diagnostics, persistence, logs, exports, and nested exception text.
2. Make it structurally difficult to persist raw credentials in provider configuration.
3. Make Save and Exit and Escape loss-safe for dirty forms without storing secrets in wizard checkpoints.
4. Make first-run defaults behave consistently in New Deep Dive and Quick Deep Dive.
5. Accept valid role assignments to non-default discovered models.
6. Prevent stale Resume Deep Dive state after a guided workflow is complete or deliberately abandoned.
7. Ensure provider readiness/discovery does not synchronously block the Textual UI event loop.
8. Make host editing semantically complete, including clearing existing optional fields.
9. Apply a consistent confirmation contract to destructive TUI actions.
10. Make logically atomic multi-setting saves actually atomic.
11. Expand acceptance/security tests so the defects found by review cannot regress behind a superficially green CI run.
12. Reconcile documentation and final evidence only after exact-head qualification on `master`.

## 2. Non-goals

This remediation does not:

- replace the guided workflow or redesign the overall TUI information architecture;
- create a second provider, research, episode, generation, repair, or export implementation;
- persist API keys or other raw credentials in wizard draft files;
- weaken local-only/network-scope policy;
- remove expert settings or the existing Quick Deep Dive override controls;
- require a schema migration unless implementation proves one is necessary;
- rewrite the completed 2026-10-08 TODO as if the review defects had never existed;
- add network-dependent tests to the deterministic unit/acceptance suite when a production-boundary fake can test the contract.

## 3. Review findings being remediated

### PRR-01 — Authorization redaction is incomplete

The canonical sanitizers in `diagnostics.py` and `secrets.py` correctly handle common Bearer cases but can leave payload text visible for other schemes. Reproduced examples include Basic, Token, and Digest authorization values.

Required outcome: an `Authorization` value is treated as sensitive as a whole, independent of scheme, casing, separator form, or whether it appears in plain text, JSON-like text, mappings, nested diagnostic structures, chained exceptions, CLI output, or TUI-visible status.

### PRR-02 — Raw credentials can be persisted through provider configuration

`ProviderConfig.credential_env` currently accepts arbitrary strings, and provider `base_url` accepts URL userinfo. A pasted API key can therefore be serialized in a field intended to contain only a credential reference, and a username/password can be serialized in a URL.

Required outcome: configuration validation structurally enforces the non-secret contract before persistence.

### PRR-03 — Save and Exit can lose unsaved form input

The shared wizard shell saves navigation context and durable IDs, but it does not know whether the current screen has dirty form state. Escape routes directly to Save and Exit. Unsaved provider/project/source/episode/default edits can therefore be discarded without confirmation.

Required outcome: leaving a dirty guided step must never silently lose edits. Safe exit must preserve already-durable state and either save current valid edits through production services or require explicit confirmation before discarding them.

### PRR-04 — First-run research default is not consistently consumed

First-run stores `research_policy`, Quick Deep Dive reads `quick_deep_dive_research_policy`, and the New Deep Dive research selector starts visually at `useful` instead of hydrating from durable policy/default state.

Required outcome: global research defaults, Quick-specific overrides, and project/episode overrides have one documented precedence model and every surface renders the effective value correctly.

### PRR-05 — First-run readiness rejects valid non-default model assignments

First-run readiness requires an assigned role model to equal a provider's configured `default_model`, while production preflight accepts any assigned discovered model.

Required outcome: first-run readiness and production preflight agree on role/model validity.

### PRR-06 — Completed workflows can leave stale resume state

The guided draft store has no explicit clear operation, and Home treats any loadable New Deep Dive draft as resumable.

Required outcome: Resume Deep Dive represents an incomplete recoverable workflow, not merely the existence of an old draft file.

### PRR-07 — Some user-visible status/error paths bypass canonical sanitization

Several advanced TUI screens can render provider health or exception/status strings without passing through the canonical sanitizer.

Required outcome: all user-visible provider/runtime/error text uses one canonical sanitization boundary.

### PRR-08 — Provider readiness can block the Textual UI

First-run/Home readiness performs synchronous runtime probes. Some provider `health()` implementations themselves discover models, after which readiness may discover models again. An unreachable endpoint can therefore block the UI for provider timeout/retry durations.

Required outcome: remote or potentially blocking provider probes run off the Textual UI event loop, use bounded timeouts, avoid unnecessary duplicate discovery, and expose explicit busy/stale/error states.

### PRR-09 — Guided host editing cannot clear optional text

The guided host editor ignores empty role/instructions values during update, preventing the user from clearing previously persisted content.

Required outcome: blank optional fields intentionally clear the corresponding durable values while required fields remain validated.

### PRR-10 — Destructive confirmations are inconsistent

Guided source deletion and generation cancellation confirm, but some advanced provider/host/source removals execute immediately.

Required outcome: destructive TUI actions use a consistent, keyboard-accessible confirmation contract.

### PRR-11 — Composite first-run/default saves are not atomic

Several logical saves call `set_default()` repeatedly, causing multiple file writes. A mid-save failure can leave a partially applied logical configuration.

Required outcome: one user-level save operation produces either the complete intended config update or no config update.

### PRR-12 — Qualification coverage missed the defects

The existing suite includes strong guided acceptance and fresh-machine gates, but its security canaries emphasize Bearer/key shapes and its Save/Exit tests start from already-persisted state.

Required outcome: tests exercise the failure shapes found by review, not only the happy-path implementation structure.

### PRR-13 — Final evidence prose is internally inconsistent

The completed TODO contains nearby references to both 938 and 939 tests for final evidence.

Required outcome: post-remediation closeout uses one exact-head source of truth and does not embed contradictory test counts.

## 4. Security and sanitization contract

### 4.1 Canonical sanitizer ownership

There must be one canonical public sanitization API for user-visible/loggable diagnostic text and recursive structures. Callers must not duplicate ad hoc regular expressions per screen.

The implementation may retain internal helpers, but all of these surfaces must converge on the same behavior:

- TUI status and error text;
- CLI errors and delegated CLI output;
- diagnostics/debug payloads;
- provider health/discovery messages;
- persisted failure messages that can originate from provider/runtime exceptions;
- log records and exception formatting;
- export/report metadata that includes diagnostic structures.

### 4.2 Authorization handling

Authorization redaction must be scheme-independent. At minimum, the following must produce no credential payload in the sanitized result:

- `Authorization: Bearer abc`;
- `Authorization: Basic dXNlcjpwYXNz`;
- `Authorization: Token secret-token`;
- `Authorization: Digest ...`;
- lower/mixed-case header names;
- `authorization=<value>` assignment forms;
- quoted/JSON-like values;
- nested mappings/lists/tuples;
- multiline exception messages;
- multiple secrets in one string.

The sanitized form may preserve the field name and a fixed marker such as `[REDACTED]`, but it must not retain the auth scheme's credential payload.

### 4.3 Other secret shapes

Existing API-key/token/password redaction must continue to work. The expanded implementation must not regress Bearer handling while fixing Basic/Token/Digest. Tests must cover common key names, URL query credentials, nested structures, exception chains, and mixed case.

### 4.4 Sanitization before presentation

Every TUI screen that displays exception, provider, runtime, preflight, research, repair, generation, transcript, plan, host, source, settings, or library status derived from external/runtime text must sanitize at a shared presentation boundary before rendering.

A screen-specific `_status()` helper may remain, but it must not be a path around canonical sanitization.

## 5. Provider configuration non-secret contract

### 5.1 Credential references

`credential_env` is an environment-variable identifier, not a credential value. Non-empty values must match:

`[A-Za-z_][A-Za-z0-9_]*`

Whitespace is trimmed before validation. Raw token-like values, spaces, punctuation-bearing secret strings, and other non-identifiers are rejected before save.

### 5.2 Provider URLs

Provider URLs must:

- use `http` or `https`;
- contain a valid host where required by the adapter;
- reject URL userinfo (`username`, `password`, or `user:pass@host` forms);
- reject known sensitive query parameters such as `api_key`, `apikey`, `key`, `token`, `access_token`, `auth`, `authorization`, `password`, and `secret`, case-insensitively;
- never echo rejected credential material in validation text.

Adapter-specific local URLs and paths that are currently valid must remain valid.

### 5.3 Persistence and compatibility

A successfully saved `config.json` must contain credential references only. Tests must inspect serialized bytes to prove raw canaries are absent.

If a pre-existing config violates the strengthened non-secret schema, loading must fail safely with an actionable sanitized message. Remediation must not silently copy the invalid raw value into a new file or diagnostic record.

Provider factory behavior remains environment-reference based: runtime credentials are resolved from the process environment only when constructing/using a provider.

## 6. Loss-safe Save and Exit contract

### 6.1 Dirty-state ownership

Each guided step containing editable controls must be able to report whether its visible form differs from the last successfully persisted or intentionally loaded state. Dirty-state comparison must be deterministic and testable.

### 6.2 Exit behavior

When Save and Exit or non-modal Escape is invoked:

1. If the current step is clean, save the normal wizard checkpoint and exit.
2. If the step is dirty, do not silently discard it.
3. Present a keyboard-accessible confirmation with explicit choices equivalent to:
   - Save changes and exit;
   - Exit without unsaved changes;
   - Cancel and continue editing.
4. Default focus must not be on destructive discard.
5. Saving current edits must use the same production service/controller/validation path as the normal step-specific Save/Continue action.
6. If save/validation fails, remain on the current step with field contents intact and show a sanitized actionable error.
7. If the user explicitly chooses to discard, preserve all previously durable state and the last safe wizard checkpoint.

### 6.3 Sensitive fields

Wizard draft files must continue to exclude raw credentials and source/body text. The remediation should prefer confirmation/save semantics over persisting sensitive unsaved forms. If any new draft field is introduced, it must be explicitly allowlisted, size-bounded, versioned, non-secret, and covered by serialization tests.

### 6.4 Modal Escape

Escape while a confirmation/help modal is open cancels/closes the modal. Escape outside a modal follows the same dirty-state-aware safe-exit path as Save and Exit.

## 7. Research default and policy semantics

### 7.1 Canonical precedence

For normal New Deep Dive research selection, the effective initial value is:

1. existing durable project research policy, when present;
2. user-level `research_policy`;
3. built-in `Useful`.

When revisiting/resuming the Research step, the selector must show the actual durable project policy, not a hard-coded default.

For Quick Deep Dive, effective research mode is:

1. project Quick Deep Dive override, when explicitly present;
2. user-level `quick_deep_dive_research_policy`, when explicitly present;
3. user-level `research_policy`;
4. built-in `Useful`.

An unset Quick-specific override must not mask the global default merely because the Settings UI displays a suggested value.

### 7.2 First-run behavior

The first-run research choice establishes the user-level `research_policy`. It must affect subsequent New Deep Dive initialization and Quick Deep Dive when no more-specific override exists.

### 7.3 Compatibility

Existing explicit Quick-specific overrides retain precedence. Existing project and episode research policies remain authoritative for their scopes. No migration should rewrite an explicit user choice to a different policy.

## 8. Model-role readiness parity

A model-role assignment is first-run-ready when:

- the assigned provider exists and has LLM capability;
- the provider runtime is healthy under the same readiness snapshot;
- the assigned model identifier is non-empty;
- that model is available/discovered for the provider, subject to the same compatibility rules used by production preflight.

The assigned model does not need to equal `provider.default_model`.

First-run readiness, Settings role configuration, CLI preflight, and generation preflight must not disagree on whether the same provider/model assignment is valid.

## 9. Guided draft lifecycle and Resume semantics

`GuidedDraftStore` must gain an explicit, safe clear operation for a wizard kind.

A New Deep Dive draft is resumable only when it represents an incomplete recoverable workflow. The application must clear or invalidate the draft when:

- the guided workflow reaches its defined terminal completion boundary;
- the user explicitly abandons the workflow through a confirmed action;
- referenced durable project/episode state makes continuation meaningless and recovery cannot produce a valid incomplete step.

Normal application shutdown, Save and Exit, generation in progress, or recoverable validation failure must retain resumability.

Clearing must be symlink-safe and must not delete unrelated files.

Home must derive the Resume action from recoverable incomplete state, not file existence alone.

## 10. Non-blocking provider readiness

### 10.1 UI thread rule

Potentially blocking provider network operations (`health`, model discovery, voice discovery, equivalent remote probes) must not execute synchronously on the Textual UI event loop during Home/first-run mount, navigation, or refresh.

### 10.2 Worker/snapshot behavior

Readiness may use Textual workers or another existing asynchronous boundary. A refresh must expose explicit states such as checking, ready, needs attention, and stale/failed without freezing keyboard navigation.

Within one readiness refresh, provider discovery must be reused rather than redundantly repeated where possible. The implementation must specifically avoid the current OpenAI pattern where readiness can cause `models()` through `health()` and then immediately call `models()` again.

### 10.3 Timeouts and races

Provider probes remain bounded by configured/runtime timeout policy. Late results from an obsolete refresh must not overwrite newer configuration/readiness state. Duplicate refresh actions must be coalesced or safely superseded.

Deterministic tests must simulate slow/unreachable providers without real network access and prove the TUI remains responsive.

## 11. Host edit semantics

Guided host editing must distinguish:

- required fields that cannot be blank;
- optional fields where blank means clear the existing durable value.

Saving an empty optional role or instructions field must persist the cleared value through the existing host service/repository path. Create behavior may still use defaults where documented, but editing an existing host must respect explicit clearing.

Restart/reload tests must prove the cleared value remains cleared.

## 12. Destructive-action confirmation contract

All user-triggered destructive TUI actions must require an explicit confirmation step, including at minimum:

- provider removal;
- host removal;
- source deletion in both guided and advanced source surfaces;
- project deletion;
- generation cancellation where destructive/terminal;
- any new equivalent delete/remove action introduced by the remediation.

Confirmation must:

- identify the target in user-friendly text;
- be keyboard accessible;
- default to cancel/non-destructive behavior;
- clear pending confirmation if selection/target changes;
- not execute twice from key-repeat or duplicate events;
- preserve the existing production delete/remove service as the actual mutation boundary.

## 13. Atomic composite configuration saves

A logical save that updates multiple related defaults must result in one durable `UserConfigStore.save()` operation after complete validation.

This applies at minimum to:

- TTS provider + voice defaults;
- research + network defaults;
- Quick Deep Dive duration + host presets + research policy;
- runtime/readiness defaults;
- first-run voice/default bundles;
- any first-run action that currently performs repeated `set_default()` calls for one button press.

All candidate values must be normalized and validated before mutating durable config. On validation or filesystem failure, the previous config must remain unchanged.

The implementation should add a controller-level batch/transaction helper rather than reimplementing copy/save logic in each screen.

## 14. Regression and qualification requirements

### 14.1 Sanitization/security matrix

Add deterministic tests covering:

- Bearer, Basic, Token, Digest and mixed-case Authorization forms;
- colon, equals, quoted, JSON-like and multiline forms;
- nested dict/list/tuple diagnostics;
- chained exceptions;
- CLI output;
- every relevant TUI status/error presentation family;
- persisted failure payloads;
- export/report metadata;
- provider URL userinfo and sensitive query rejection;
- invalid `credential_env` values;
- serialized config absence of raw canaries;
- no over-redaction of representative benign text.

### 14.2 Save/Exit matrix

For both first-run and New Deep Dive, test:

- clean Save and Exit;
- dirty valid field + Save changes and exit;
- dirty invalid field + failed save retains form;
- dirty field + Cancel retains form;
- dirty field + explicit discard loses only unsaved edits;
- Escape follows the same behavior;
- modal Escape cancels modal;
- restart resumes previously durable progress;
- draft contains no raw source body or credential value.

### 14.3 Research/default matrix

Test Off, Useful, and Aggressive across:

- first-run default -> new project Research screen;
- first-run/global default -> Quick Deep Dive fallback;
- explicit Quick user override;
- project Quick override;
- persisted project research policy revisit/resume;
- restart and installed-wheel execution.

### 14.4 Provider/readiness matrix

Test:

- non-default discovered model assignment accepted;
- unavailable model rejected consistently by first-run and preflight;
- slow provider probe does not block TUI pilot input;
- obsolete probe result cannot overwrite newer config;
- one readiness refresh does not perform redundant discovery beyond the documented retry policy;
- sanitized probe failures remain actionable.

### 14.5 Lifecycle/destructive/atomic matrix

Test:

- draft clear on completed/abandoned guided workflow;
- resume retained on recoverable incomplete workflow;
- host role/instructions clear and survive restart;
- provider/host/source destructive confirmations and cancel paths;
- target-change cancellation of pending destructive action;
- composite settings produce one durable save;
- simulated save failure leaves previous config byte-for-byte unchanged where practical.

### 14.6 Existing regression preservation

The full pre-existing unit/integration/TUI/CLI suite must remain green. In particular, do not regress:

- installed-wheel CLI entry points;
- deterministic production fixture workflows;
- Quick/guided artifact identity;
- multi-episode isolation;
- generation run control;
- targeted repair;
- provider routing;
- local-only/network policy;
- real KittenTTS CPU qualification;
- package build and dependency lock reproducibility.

## 15. Documentation requirements

Update user/developer documentation where behavior changed, including:

- Save and Exit/dirty-form semantics;
- credential reference format and invalid examples without publishing real-looking secrets;
- provider URL restrictions;
- research default/Quick override precedence;
- Resume Deep Dive lifecycle;
- asynchronous readiness/checking states;
- destructive confirmation behavior.

The original 2026-10-08 TODO and spec remain intact except for an optional small forward-reference note if useful. Do not change historical checkboxes to rewrite history.

## 16. Completion and evidence policy

A remediation checkbox is complete only when all of the following are true where applicable:

1. Production code implements the behavior through shared service/controller boundaries.
2. Focused regression tests exercise the defect and its negative cases.
3. Relevant deterministic acceptance matrices pass.
4. Changes are present on `master`.
5. Exact-head CI for that `master` commit is successful before TODO reconciliation marks the item complete.
6. Reconciliation-only commits receive their own exact-head CI qualification.

Final closeout must record one unambiguous exact master SHA, exact CI run ID(s), test result counts as reported by those runs, installed-wheel/fresh-machine result, KittenTTS result, and any explicitly N/A migration gate. Do not embed contradictory historical test counts in the final completion statement.

## 17. Exit criteria

This post-review remediation is complete only when:

- every checkbox in the companion TODO is reconciled;
- no PRR-01 through PRR-13 defect remains reproducible;
- security canaries do not appear in sanitized output or persisted config;
- unsaved guided-form edits cannot be lost without explicit confirmation;
- research/default precedence is consistent across first-run, New Deep Dive, and Quick Deep Dive;
- valid non-default model assignments pass readiness/preflight parity;
- stale guided drafts do not produce false Resume actions;
- provider readiness does not block the TUI event loop;
- advanced destructive actions confirm;
- composite setting saves are atomic;
- the full existing suite plus the new post-review matrices passes from an installed wheel/fresh environment;
- final exact-head CI on `master` is green and the TODO contains internally consistent evidence.
