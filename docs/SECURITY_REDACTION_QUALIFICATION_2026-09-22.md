# Security and redaction qualification evidence

Created: 2026-09-22

This note records the current deterministic evidence for the R9/R11 security cluster. It is evidence for later TODO reconciliation; it does not by itself mark any remediation checkbox complete.

## Canonical boundary

`deeper_dive.diagnostics.redact` is the recursive canonical redaction primitive. Provider-facing exception handling uses `sanitize_provider_error`, while CLI and TUI error adapters use the same sanitization path before rendering untrusted exception details.

## Covered secret forms

The deterministic diagnostics suites cover authorization-header credentials, API-key assignment forms, token assignment forms, environment-style assignments, credential-bearing URLs, nested mappings/sequences, provider-SDK-style exception representations, and debug/repr fields. The assertions require original sensitive values to be absent while retaining useful non-sensitive context.

## Persistence and diagnostics

Pipeline failure regression tests inject provider failures containing recognizable sensitive values and assert that durable run failure fields contain only sanitized text. Nested exception causes are also covered. Diagnostic log and diagnostic-bundle tests assert that recursive fields are redacted and that source excerpts remain excluded unless explicitly opted in.

## CLI and TUI surfaces

CLI regression coverage forces command-handler failures and verifies stderr never contains the original sensitive value. TUI/user-error regression coverage verifies actionable diagnostics and status text are sanitized before presentation. Delegated CLI handling also replaces unsafe inner stderr with a safe outer error.

## Qualification mapping

The existing deterministic suites collectively provide evidence for DDR-080, DDR-081, DDR-082, and DDR-107. Final reconciliation should require an exact-head CI pass containing these suites and should retain the stronger rule that no original sensitive value may appear in persistence, diagnostics, logs, CLI output, TUI-visible errors, or debug/repr diagnostic fields.
