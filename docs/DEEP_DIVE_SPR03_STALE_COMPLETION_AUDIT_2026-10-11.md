# SPR-03 stale readiness completion audit (2026-10-11)

At master 6d44a1ff5f4d20a5495eaef2f5bf25d41b7ca832, `FirstRunReadinessCoordinator.request()` calls the disk-backed fingerprint function before checking whether the coordinator is closed. Likewise `_complete()` invokes the fingerprint function before verifying whether its generation was superseded, timed out or closed. These are avoidable I/O calls on the Textual event loop after work has become ineligible to publish.

Proposed regression: use a fingerprint callable that raises if accessed after close or for a stale completion; verify neither request nor completion reads it and that no stale callback publishes. Proposed implementation: check closed state before fingerprinting in `request()`, and check closed/generation/checking before fingerprinting in `_complete()`; retain the existing second locked check to handle races. This audit is not implementation or qualification evidence. SPR-03 remains open.
