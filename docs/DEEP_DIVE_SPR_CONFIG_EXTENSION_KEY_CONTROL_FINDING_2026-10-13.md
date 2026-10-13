# SPR-04/SPR-06 review finding: extension setting names

**Date:** 2026-10-13  
**Status:** Open; production repair and full qualification required.  
**Severity:** Moderate defense-in-depth / terminal-output integrity.

## Source-level finding

`src/deeper_dive/user_config.py::UserConfig.validate_defaults` checks terminal
control bytes in recognized values and certain identifiers, but does not check
the *keys* of `defaults`. Legacy extension values are intentionally free-form;
extension setting names are not necessarily safe to render in CLI/TUI output.
`SettingsController.set_defaults` and `ProviderController.save_provider`
reject control characters in keys before writing, but direct `UserConfig`
construction, loaded JSON, and mutations to an existing Pydantic config can
still carry a control-containing extension key through model validation.

The existing producer-boundary guards are tested by
`tests/test_second_post_review_default_key_controls.py`, using atomic
on-disk byte snapshots and a fresh store load. The same file contains a
strict, explained expected-failure reproducer for the unguarded direct-model
boundary. No real credentials are used.

## Required remediation

Validate every `UserConfig.defaults` mapping key for ASCII terminal control
characters *before* normalizing recognized values. Emit a fixed field-level
error without echoing the rejected key/value. Preserve existing printable
legacy extension keys and their free-form values. Add mutated-model,
load/restart, rollback, Settings and provider-composite acceptance evidence;
convert the expected-failure reproducer into a passing regression. Confirm
the final source and test head passes both quality and fresh-machine CI.

This report is not a completion claim for SPR-400, SPR-600 or SPR-900, and
does not change any checklist checkbox.
