# Env Registry (Names-Only) — Example Template

Copy this file to `docs/runtime/Env-Registry.md` and fill in real rows. The original `.example.md` stays in git as the template.

## Metadata

- Last Reviewed (UTC): YYYY-MM-DD
- Policy: names-only keys and file paths. Do not record secret values.
- Purpose: one lookup table for "which env key lives where and who consumes it".

## Source-of-Truth Rule

- The credential and secret file lifecycle, including mirror and incoming-env handling, is defined in `docs/runtime/Credentials-Management.md`.
- Each env key's authoritative owner is the `source_file` in that key's row below, interpreted through the credential planes in `Credentials-Management.md`.
- Secret values are managed outside git and validated via a project-specific precheck script (e.g. `scripts/check-env.sh --profile <profile>`).
- Dual-backend keys are flagged in the `notes` column and point to their rotation runbook.

## How to use this template

1. Group rows by **consumer surface**, not by alphabetical key. A grouping like "auth keys", "payment runtime keys", "mail provider keys" makes ownership obvious at a glance.
2. One row per key. If a key has two valid source files (e.g. canonical vs. legacy override), use two rows and mark the legacy row clearly.
3. Refuse to add a row whose `source_file` cannot be expressed as one plane from `Credentials-Management.md`. That is a signal the ownership is unclear.
4. Refuse to add a row that has no `verify_gate`. A key with no verification is a key that will silently drift.

## Example group — replace with your real surfaces

### `<Consumer Surface Name>` (e.g. "API authentication keys")

| env_key | source_file | runtime_injection | primary_consumers | verify_gate |
|---|---|---|---|---|
| `<KEY_NAME_ONE>` | `<plane>:<path>` | `<systemd EnvironmentFile / compose env_file / secrets-manager fetch / ...>` | `<process or container that reads this key>` | `<command or test that confirms this key is set correctly in production>` |
| `<KEY_NAME_TWO>` | `<plane>:<path>` | `<...>` | `<...>` | `<...>` |

### `<Another Consumer Surface>`

| env_key | source_file | runtime_injection | primary_consumers | verify_gate |
|---|---|---|---|---|
| `<KEY_NAME_THREE>` | `<plane>:<path>` | `<...>` | `<...>` | `<...>` |

## Retired keys

Keys that have been removed from the runtime should be listed here so production prechecks can reject them if they reappear in an env file. Do not delete this section; it is the audit trail.

| env_key | retired_at | reason | rejected_by |
|---|---|---|---|
| `<RETIRED_KEY_NAME>` | YYYY-MM-DD | `<one-line reason>` | `<precheck profile or test that rejects this key>` |

## Operational Checks

List the verify commands your project actually uses. Examples:

- Local precheck (safe to run when an env file is present):
  `bash scripts/check-env.sh --profile <profile-name> --env-file <path> --if-present`
- Production precheck (current runtime baseline):
  `bash scripts/check-env.sh --profile <production-profile> --env-file <runtime-path>`
- Verify pipeline entry:
  `make verify` (wire the env precheck in before structure/runtime gates)
