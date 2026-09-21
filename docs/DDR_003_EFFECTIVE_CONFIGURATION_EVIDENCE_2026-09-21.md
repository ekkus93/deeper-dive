# DDR-003 effective configuration precedence evidence

**Date:** 2026-09-21  
**Scope:** Evidence for `docs/DEEP_DIVE_V1_INTEGRATION_REMEDIATION_TODO_2026-09-19.md` DDR-003.

## Implemented precedence path

`src/deeper_dive/model_roles.py` currently defines the production model-role assignment path used by planning and preflight surfaces:

- `ModelRoleAssignments.resolve` resolves assignments with episode > project > user precedence.
- `effective_model_role_assignments` parses user defaults, project defaults, and episode overrides into scoped assignments.
- `project_model_defaults_from_instructions` reads project defaults only from an explicit JSON `model_defaults` mapping.
- `preflight_model_roles` consumes the resolved assignments and validates provider/model availability against the configured LLM provider registry.

## Regression evidence already present

`tests/test_model_roles.py` contains direct regression coverage for:

- episode assignments overriding project and user assignments,
- project assignments overriding user assignments,
- parser-level precedence across user defaults, project defaults, and episode overrides,
- actionable validation errors for malformed assignments,
- full role coverage for all documented generation roles,
- preflight consuming the resolved assignments and reporting missing providers/models.

## Remaining DDR-003 gap

This evidence supports the first two unchecked DDR-003 precedence items. The item "Make preflight and generation consume the same resolved assignments" should remain open until the generation pipeline's provider/model resolution is wired to the same `ModelRoleAssignments` path that preflight uses and is covered by a production-path integration test.

## Reconciliation rule

Do not close DDR-003 as a whole until the generation/preflight shared-resolution path is implemented, exact-head CI passes, merged-master CI passes, and the authoritative TODO is reconciled from current `master`.
