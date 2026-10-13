# User configuration defaults — V1 semantic contract

**Scope:** Deeper Dive second post-review SPR-04 / SPR-06 (2026-10-12).
**Authority:** `src/deeper_dive/user_config.py`, `src/deeper_dive/provider_tui.py`,
`src/deeper_dive/settings_screen.py`, `src/deeper_dive/network_scope.py`,
`src/deeper_dive/model_roles.py`, `src/deeper_dive/research_policy.py`,
`src/deeper_dive/hosts.py`, and the second post-review remediation spec.

This documents **what V1 actually validates and consumes**. It does not assert
that every caller, migration, or compatibility regression matrix has passed.
The authoritative remediation TODO determines completion status.

## Durable file and write contract

`UserConfig` has `schema_version=1`, a map of non-secret `providers`,
and a map of string `defaults`. Secrets are referenced by environment-variable
names (`credential_env`), not saved credential values. `UserConfigStore`
validates the entire candidate on each save (including mutable Pydantic
instances), uses a same-directory unique temporary file and atomic replace,
and rejects a stale revision rather than silently clobbering a concurrent
writer. Failed validation must preserve the previous file bytes. Config
directory ownership/trust is a deployment precondition.

`SettingsController.set_defaults()` rejects terminal-control bytes before trimming keys and values; **blank input
removes** a key in a composite Settings save. Direct V1 deserialization is more
permissive: some recognized keys allow the empty string, which means
unspecified, inherited, or configured elsewhere. Do not conflate an unset
default with a required empty provider/role identifier.

## Semantic default-key schema

| Keys | Accepted values and normalization | Consumer/constraints |
| --- | --- | --- |
| `research_policy`, `quick_deep_dive_research_policy` | `off`, `conservative`, `useful`, `aggressive` from `ResearchMode`; strip and lowercase; blank optional | Project/episode policy and Quick selection. Do not invent extra aliases. |
| `quick_deep_dive_duration_minutes` | Positive integer represented as text, at most `((2**63)-1)//60`; whitespace trimmed; blank optional | Quick episode duration, later stored as signed 64-bit seconds. Do not round or silently clamp. |
| `quick_deep_dive_host_presets` | Exactly two comma-delimited members of `preset_names()` when nonblank; trim each element | Current presets: `curious_explainer`, `skeptic`, `synthesizer`, `domain_expert`, `practitioner`, `historian`, `moderator`, `custom`. The schema does not require distinct presets. |
| `local_only` | `1`, `true`, `yes`, `on`; `0`, `false`, `no`, `off`; lowercase; blank optional | `ProviderNetworkPolicy.local_only()` treats only the first four as true. |
| `network_policy` | `local-only`, `configured-providers`, `allow-remote`, `remote-allowed`; lowercase and replace underscore/space with hyphen | Network policy preference. Both remote-allowing spellings are accepted legacy alternatives. |
| `diagnostic_logging` | `off`, `normal`, `verbose`; lowercase; blank optional | Runtime diagnostics preference. |
| `speech_setup` | `configured`, `deferred`; lowercase; blank optional | First-run speech readiness and deferred-TTS path. |
| `ffmpeg_executable`, `kitten_model_dir` | Optional trimmed filesystem path or executable; reject NUL, CR and LF | Runtime/readiness paths. These are not checked for existence at config-save time; that is a separate readiness/preflight concern. |
| `local_provider_ids` | Comma-delimited trimmed nonblank provider IDs | The provider controller checks referential integrity on normal Settings/provider writes; explicit `network_scope` still overrides legacy local-ID hints. |
| `tts_provider` | Optional trimmed TTS provider ID; no ASCII controls | Provider controller checks the referenced provider exists and supports TTS when defaults are changed through it. |
| `tts_voice`, `tts_voice_host_1`, `tts_voice_host_2` | Optional trimmed voice IDs; no ASCII controls | If the referenced TTS provider declares voices, the provider controller checks voice membership. Otherwise discovery occurs later. |
| `corpus_analysis`, `research_planning`, `source_analysis`, `episode_planning`, `directing`, `host_generation`, `verification` | Optional `provider:model` (each side nonempty, outer whitespace trimmed; ASCII terminal controls rejected before trimming); all model role keys correspond to `ModelRole` | `ProviderController.validate_default_references()` checks a configured provider exists and is an LLM. Episode/project overrides follow production precedence. |

The defaults mapping deliberately permits **unknown legacy extension keys** and
does not rewrite their values. Do not reject them casually in a new migration.
There is no implied guarantee that every unknown key will have a consumer.

## Provider entry validation

Each `providers[provider_id]` contains a `ProviderConfig`:

- `provider_type`: nonempty adapter name. The **factory**, not bare
  Pydantic field typing, checks that a concrete supported LLM/TTS adapter can
  be constructed; ambiguous historical generic types need explicit migration.
- `base_url`: optional HTTP(S) URL with parseable host/port, no userinfo,
  raw fragment (including an empty `#`), or sensitive query keys (including
  encoded spellings). Benign query parameters and IPv6 are permitted.
- `credential_env`: optional trimmed environment-variable identifier,
  `[A-Za-z_][A-Za-z0-9_]*`; never a literal API key.
- `default_model`: optional provider-specific model ID, resolved by adapter.
- `voices`: tuple of provider voice identifiers; reject ASCII control
  characters, preserve printable names.
- `response_format`: case-folded supported audio format.
- `timeout_seconds`: finite positive timeout at most 600 seconds.
- `network_scope`: optional `local` or `remote`; absent means adapter
  inference, with explicit scope taking precedence.

The controller validates composite provider+defaults candidates before building
adapters, saving bytes and publishing runtime registries. Direct store callers
must also pass complete V1 model validation. Provider/runtime construction can
still fail for reasons independent of schema validity (unavailable binaries,
missing environment credential references or unreachable services).

## Legacy and recovery policy

Older persisted model-role values containing a **bare model name** (no colon)
are accepted only when that exact value was loaded from the existing file and
tracked as legacy by `UserConfigStore`. New bare-model assignments are
rejected. Saving an unchanged legacy config does not silently reinterpret the
role; migration to `provider:model` needs an explicit provider choice.

Valid historic extra default keys are retained verbatim. Unrecognized
`schema_version`, structurally invalid JSON, or a known-key value violating
current validation returns `UserConfigError`; it must not be silently
overwritten or partially migrated. The user must repair the settings file or
restore a valid backup before continuing. Error surfaces must report safe
field names rather than echo credentials, raw URLs or arbitrary mapping keys.

## Qualification requirements (still separately tracked)

Use the shared deterministic acceptance fixture and exact-head CI to exercise
valid, invalid, blank and historical values; provider and voice references;
Settings/first-run/provider/CLI composite save paths; independent writers;
failing store writes; reload after restart; Quick consumption; and
stringified/nested credential canaries in CLI, TUI and exported diagnostics.
Existing unit tests do not by themselves close SPR-04/06 or final SPR-910.
