# Privacy and security behavior

This guide explains what data can leave the machine, how provider routing is disclosed, how secrets are handled, how supplemental web research works, what local-only configuration means, and what diagnostic exports contain.

It is documentation for the current design and implementation boundaries. It is not a claim that every future provider adapter or feature is automatically safe; new network, provider, parser, subprocess, or diagnostic code must preserve these boundaries and add tests where appropriate.

## What data can leave the machine

Deeper Dive is local-friendly, not automatically air-gapped. Data can leave the machine only through configured or explicit network/provider paths:

- LLM provider calls can receive source excerpts, retrieved evidence, episode focus/audience instructions, host configuration, conversation context, generated plans, generated turns, and claim-verification prompts.
- TTS provider calls can receive generated host speech text and voice/model selections.
- Supplemental web research can issue HTTP/HTTPS requests for candidate pages when research is enabled.
- Explicit user URL import fetches a URL the user directly provides.
- Optional model or runtime installation flows, such as Kitten model installation, can download artifacts from user-selected URLs.

Project databases, source files, transcripts, generated audio, cache/index files, and exports are stored in the project workspace unless a user explicitly exports or copies them elsewhere.

## Provider routing

Provider routing should be visible before expensive generation begins. Preflight reports include route records for LLM roles and TTS synthesis. Each route identifies:

- the generation stage or role;
- the provider ID;
- the model when applicable;
- whether the provider is considered local;
- what category of content can be sent.

Remote routes are not inherently forbidden, but they must be explicit and reviewable. When private source text may be sent to a remote LLM provider, preflight should warn the user before generation. Local-only mode should turn remote provider routes into blockers.

Provider locality is configuration-dependent. Local runtimes such as Ollama, llama-server, KittenTTS, fake providers, or loopback endpoints can be treated as local. A provider hosted elsewhere, even if API-compatible with a local protocol, should not be marked local unless the configuration actually points to a local endpoint.

## Secret handling

Provider credentials and API keys should not be stored in project databases, normal provider configuration records, exports, or diagnostic bundles by default. Normal user configuration stores non-secret provider metadata such as provider type, base URL, default model, and timeout.

Secrets should be supplied through the supported secret or environment mechanism for the provider adapter. If a provider adapter needs a credential, it should read the credential at call time and avoid persisting it in project state.

Logs and diagnostics must redact recognizable secret-like values. User-facing errors should be actionable and concise; low-level diagnostics should be sanitized and kept behind explicit diagnostic/reporting surfaces.

## Supplemental web research behavior

Supplemental research is optional and gap-driven. The application should first identify a concrete research gap, such as outdated material, missing corroboration, a missing cited work, or an audience-context need. Automated research should not issue arbitrary broad network requests without a recorded reason.

Automated research must use the research-safe fetch boundary. That boundary:

- accepts only HTTP/HTTPS URLs;
- rejects any DNS answer set containing non-global addresses;
- validates each redirect target before following it;
- keeps redirect count finite;
- keeps request timeout finite;
- keeps response body size finite;
- accepts only expected text content types;
- distinguishes automated supplemental research from explicit user URL imports.

The network hardening audit is in `docs/NETWORK_HARDENING_AUDIT_2026-09-19.md`. It documents the residual DNS answer-to-socket time-of-check/time-of-use limitation of the standard-library transport; do not represent that limitation as solved unless the transport changes.

## Explicit URL imports

`source add --url` and equivalent user actions import URLs chosen directly by the user. These are treated as user-supplied sources, not automated supplemental research. Code must not route automatically discovered research candidates through the explicit-user URL path to bypass SSRF controls.

## Local-only configuration

Local-only mode is intended to let a user prevent source text and generated context from leaving the local machine through configured providers. In local-only mode:

- local provider routes are allowed;
- remote provider routes should block generation during preflight;
- cloud provider configuration may be skipped;
- supplemental web research should be disabled or explicitly treated as not local;
- explicit user URL imports remain user-directed network actions and should still be reviewed by the user.

Local-only mode depends on correct provider classification. Treat loopback/local runtimes as local only when the configuration actually identifies them as local.

## Diagnostic export contents

Diagnostic bundles should help debug runs without leaking sensitive material by default. The safe default is to include:

- run IDs and project/episode IDs;
- stage names and run state;
- sanitized provider diagnostics;
- failure codes and actionable messages;
- environment/tool availability information such as FFmpeg detection;
- configuration shape without credentials;
- source counts, IDs, and metadata needed for support.

Diagnostic bundles should exclude raw source contents by default. If source excerpts are ever included, that must be an explicit opt-in action, and the bundle should clearly indicate that excerpts are included.

Diagnostic export behavior is covered by tests that inject recognizable secret-like values and verify they do not appear in exported diagnostics.

## Filesystem and subprocess boundaries

Workspace paths should remain under project-owned directories. Project-relative paths must reject traversal and absolute-path escape attempts. User-derived readable path components should be sanitized; durable objects should use generated IDs.

External process execution, including FFmpeg and local playback, should use argv-only subprocess calls with `shell=False`. User-controlled paths must be passed as separate argv elements and never interpolated into a shell string.

The filesystem/process hardening audit is in `docs/FILESYSTEM_PROCESS_HARDENING_AUDIT_2026-09-19.md`.

## User review checklist

Before generating or exporting sensitive material, review:

- whether preflight shows any remote provider route;
- whether local-only mode is enabled when required;
- whether supplemental web research is enabled;
- whether explicit URL imports are expected;
- whether provider credentials are supplied outside normal project/config storage;
- whether diagnostic exports exclude source excerpts unless deliberately opted in.

Deeper Dive is designed to make these choices visible. Human review remains part of safe operation.
