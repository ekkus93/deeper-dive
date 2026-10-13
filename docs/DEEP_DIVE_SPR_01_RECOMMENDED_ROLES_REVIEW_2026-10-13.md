# SPR-01 — Recommended model-role action dirty-state review

Review date: 2026-10-13. Baseline: `7b3bca143869915c470d91496f16b465b1d00da5`.

## Finding (unresolved)

`GuidedFirstRunWizard.action_recommended_roles()` in
`src/deeper_dive/guided_first_run.py` directly calls
`_persist_roles({role: identity for role in _REQUIRED_SETUP_ROLES})`.
The action does not check `_current_form_dirty()` or invoke the shared
`_request_dirty_transition(...)` Save/Discard/Cancel guard before replacing
the four editable role inputs and advancing their durable baseline via
`_remember_current_form()`. This can silently overwrite unsaved role
assignments. Treat as an actionable potential data-loss defect pending a
deterministic Textual reproduction.

## Proposed acceptance

When model-role controls contain unsaved edits, pressing Recommended Roles
must preserve the current inputs and persisted configuration until the user
explicitly chooses Save, Discard, or Cancel. Cancel keeps all edited values
and leaves durable configuration unchanged. Explicit discard may apply the
recommendations; explicit save must use the production SettingsController
transaction. Confirm focus defaults to Cancel, Escape cancels, duplicate
events cannot apply twice, and clean forms remain frictionless. Cover
these transitions using a fake provider and real GuidedDeeperDiveApp pilot.

No SPR-01 completion checkbox should be marked from this review alone.
