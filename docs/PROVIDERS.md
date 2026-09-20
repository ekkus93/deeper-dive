# Deeper Dive provider setup

This document explains how provider configuration is expected to work for Deeper Dive. It covers LLM providers, TTS providers, KittenTTS Micro, and credential-storage behavior.

Provider setup is intentionally explicit. Deeper Dive should not contact a provider, send source text, download a model, or use cloud credentials merely because the package is imported.

## General provider model

Providers are configured outside project databases in user configuration. Projects and exported artifacts store non-secret provider identities, model names, routing decisions, and sanitized diagnostics, but they must not store raw API keys or credential values.

The Providers screen and provider CLI expose the same concepts:

```bash
uv run deeper-dive --json provider list
uv run deeper-dive --json provider health fake
uv run deeper-dive --json provider models fake
uv run deeper-dive --json provider voices fake-tts
uv run deeper-dive --json provider kitten-status
uv run deeper-dive --json provider kitten-benchmark
```

Generation preflight is the final safety gate. Review preflight before generation to see which stages route content to which providers and whether each route is local or remote.

## OpenAI LLM setup

Use OpenAI LLM support when you want cloud language-model generation.

Typical setup steps:

1. Configure a provider entry with provider type `openai`.
2. Set the default model for roles that should use OpenAI.
3. Provide credentials through the supported secret/environment mechanism rather than storing them in project files.
4. Run provider health/model discovery.
5. Run generation preflight and confirm that remote routing is expected before generation.

Operational notes:

- Cloud LLM stages may receive source excerpts, retrieval context, generated conversation state, and verification prompts.
- Preflight should warn when private source text may be sent to a remote provider.
- Do not use OpenAI for a local-only project unless local-only enforcement has been explicitly relaxed.

## Ollama setup

Use Ollama when you want a local LLM served by an Ollama runtime.

Typical setup steps:

1. Install and start Ollama locally.
2. Pull the model you want to use with Ollama.
3. Configure a provider entry with provider type `ollama` and a base URL such as `http://localhost:11434`.
4. Assign Deeper Dive model roles to `provider:model` values matching your Ollama model names.
5. Run provider health/model discovery.
6. Run preflight and confirm the Ollama route is shown as local.

Operational notes:

- Keep the Ollama daemon running before generation.
- Model context length and structured-output support depend on the model/runtime.
- Ollama is treated as a local route when configured with localhost/loopback style endpoints.

## llama-server setup

Use llama-server when you want a local or self-hosted llama.cpp-compatible model server.

Typical setup steps:

1. Start llama-server with the selected model and context/settings.
2. Configure a provider entry with provider type `llama-server` or `llama_server`.
3. Use a local base URL such as `http://localhost:<port>` for local-only use.
4. Assign Deeper Dive model roles to the configured provider/model.
5. Run provider health/model discovery.
6. Confirm routing in preflight.

Operational notes:

- Deeper Dive should treat an unavailable local server as a recoverable provider/configuration error.
- Keep endpoint URLs explicit; do not hide remote services behind a local-looking name unless that is actually the route.
- Structured-output behavior may vary by server version and model.

## KittenTTS Micro setup

KittenTTS Micro is the built-in local CPU speech option. It is optional and model/runtime setup is explicit.

Typical setup steps:

1. Install the optional KittenTTS runtime dependency supported by your environment.
2. Use `provider kitten-status` to inspect model state.
3. Use the TUI/provider workflow or `provider kitten-benchmark` to check readiness and estimate local speech performance.
4. Assign Kitten voices to hosts.
5. Run preflight and confirm Kitten routes are local.

Operational notes:

- The base package must not bundle model weights.
- Model installation/download lifecycle should be explicit and recover safely from partial downloads.
- KittenTTS runs locally and is suitable for local-only speech when available.

## OpenAI TTS setup

Use OpenAI TTS when you want cloud speech generation through OpenAI's speech API.

Typical setup steps:

1. Configure a TTS provider entry for OpenAI TTS.
2. Configure model and voice choices supported by your account/API version.
3. Provide credentials through the supported secret/environment mechanism.
4. Discover voices where available or configure known voices explicitly.
5. Assign provider/voice pairs to hosts.
6. Run preflight and confirm that generated host speech text will be routed to the OpenAI TTS provider.

Operational notes:

- TTS providers receive generated host speech text, not raw source documents unless a future feature explicitly changes that route.
- Cloud TTS failures should surface actionable errors while preserving sanitized diagnostics.

## OpenAI-compatible TTS setup

Use the OpenAI-compatible TTS adapter for local or third-party services that expose a compatible speech API.

Typical setup steps:

1. Configure the provider with a base URL.
2. Configure model, voice, response format, and timeout settings.
3. Provide credentials or custom headers only through the supported secret/environment mechanism.
4. Run health/voice discovery if the service supports it.
5. Assign voices to hosts and review preflight routing.

Operational notes:

- Compatibility deviations are expected; failures should be recoverable configuration/provider errors.
- Local compatible endpoints can be used for local-only workflows when they are actually local.

## ElevenLabs setup

Use ElevenLabs when you want cloud speech generation through ElevenLabs voices/models.

Typical setup steps:

1. Configure an ElevenLabs TTS provider.
2. Provide the API key through the supported secret/environment mechanism.
3. Discover voices and select one voice per host.
4. Configure model/settings as needed.
5. Run preflight and confirm remote TTS routing is expected.

Operational notes:

- ElevenLabs receives generated host speech text for synthesis.
- Rate-limit, authentication, and timeout failures should be shown as actionable provider/TTS errors.

## Credential storage behavior

Credential handling follows these rules:

- Non-secret provider settings belong in user configuration, outside per-project databases.
- API keys, tokens, passwords, and authorization headers must not be serialized into project config, exported metadata, run diagnostics, or diagnostic bundles.
- Secret-like unknown fields are rejected from normal user configuration.
- Diagnostic/export paths use redaction before user-visible or persisted output.
- On POSIX platforms, saved non-secret user configuration is restricted to owner-only permissions where supported.
- Environment-variable credential references are preferred for automation and CI.

## Local-only checklist

Before running a local-only generation:

1. Configure only local LLM/TTS providers such as Ollama, llama-server, and KittenTTS.
2. Assign every required model role to local providers.
3. Assign every host to a local TTS voice.
4. Run preflight.
5. Confirm every provider route is marked local.
6. Resolve any remote-route blocker before generation.

## Troubleshooting

- If model discovery fails, check the endpoint, model name, credentials, and runtime health.
- If voice discovery fails, confirm the provider is a TTS provider and that credentials or local runtime are available.
- If KittenTTS status is not installed, install the optional runtime/model before assigning Kitten voices.
- If preflight warns about remote source text routing, review whether that provider should be used for this project.
- If diagnostics are needed, export sanitized diagnostics rather than copying raw provider traces containing headers or secrets.
