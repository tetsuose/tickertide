# Credentials Management

This document describes the credential and env-file discipline that complements the file-contracts system. Where `Manifest-Contract-System.md` answers "what is each file for", this document answers "where does each runtime secret live and who is allowed to change it".

The model is intentionally generic. It does not assume a specific cloud, secret store, runtime, or service. It assumes only that your project has more than one consumer of more than one secret, and that consumers do not all live in the same place.

## Core concept

Every runtime credential and every env file belongs to exactly one **credential plane**. A plane is a `(path, source_of_truth, consumer, mutation_rule)` tuple. Planes have **hard boundaries**: a key that belongs to plane A must not appear in plane B's file. This prevents the common failure modes:

- an operator-control file silently turning into a runtime secret store
- a local mirror being edited as if it were the live source
- a staging/incoming file being treated as a long-lived cache
- the same logical secret existing in two unrelated stores with no atomic rotation

A names-only **registry** records which key lives in which plane. A separate **inventory** records the operational assets (domains, hosts, accounts) and their credentials, stored outside of git.

## The plane model

Define your planes once. Each plane row answers four questions:

| Plane | Path | Source Of Truth | Consumer | Mutation Rule |
|---|---|---|---|---|
| `operator-control` | a local file an operator uses to reach and command remote systems | local operator config | local operator tooling | contains only how the operator reaches and controls servers; no runtime secrets |
| `runtime-sot` | the live file the service reads at boot | the deployed environment itself | one runtime process or container | edited only through an explicit operator window on the live target |
| `runtime-mirror` | a local read-only copy of `runtime-sot` | mirror only | disaster recovery, audit, redacted drift | pulled from the live target; never hand-edited as authority |
| `incoming-staging` | a temporary file for new or rotated values | none | the apply-then-classify workflow | must be deleted after apply |
| `consumer-specific` | a file scoped to one runtime consumer | that consumer's config | only that consumer | no keys belonging to a different consumer |
| `out-of-band-backend` | a secret store that one consumer must read directly (because it cannot mount a shared file) | that backend | that consumer | rotated atomically with the in-band copy |

These names are conventions, not magic strings. The point is that every credential file in your repo or on your hosts can be tagged with exactly one plane label and a mutation rule. Rename them to fit your project.

### Hard boundaries (the part that earns its keep)

- The operator-control plane is not a runtime env file. It must not contain runtime database, payment, mail, auth, or per-node secrets.
- The runtime source-of-truth lives where the runtime reads it, not in the repo. The repo holds only the mirror and the example.
- The runtime mirror is for disaster recovery and offline diff evidence. Restoring it back means writing to the live target through the explicit operator window, then re-pulling the mirror.
- The incoming-staging file is input only. It is not a cache, not a mirror, and not a long-lived source of truth. Delete it after apply.
- The registry records key names, owners, consumers, and verification commands. It must not contain values, endpoints, tokens, passwords, or raw secret excerpts.

## The registry (names-only)

Maintain one names-only table in `docs/runtime/Env-Registry.md`. Each row has five columns:

| `env_key` | `source_file` | `runtime_injection` | `primary_consumers` | `verify_gate` |

- `env_key` — the literal env variable name.
- `source_file` — the one file that owns this key, expressed in plane terms (e.g. `runtime-sot:/etc/<service>.env` or `consumer-specific:<app>/.env`).
- `runtime_injection` — how the key reaches the consumer process (systemd `EnvironmentFile`, compose `env_file`, secrets-manager fetch, etc.).
- `primary_consumers` — which processes read this key. Be specific.
- `verify_gate` — the command that confirms the key is correctly set in production (a profile-based env checker, an integration test, a health endpoint, etc.).

Never put values in this file. Never put endpoints, region identifiers, or anything that can leak topology. If a row is hard to write because the key has unclear ownership, that is the registry doing its job: stop and fix the ownership before applying the key.

See `Env-Registry.example.md` for the empty template.

## The inventory (assets + credentials, out of git)

Maintain a separate `secrets-inventory.yaml` for the **operational asset checklist**: domains, host pools, contact addresses, third-party accounts, per-node credentials, rotation timestamps. This file holds real values and **must not be committed**. The example template `Secrets-Inventory.example.yaml` is the only thing that lives in git.

Inventory and registry are different artifacts:

- Registry answers "where does key X live in the running system".
- Inventory answers "what are all the assets and credentials this project owns, and when did each one last rotate".

The inventory is for the operator and the auditor. The registry is for the runtime and the code.

## Lifecycle: adding a new key

Before adding a key:

1. Pick one owner plane.
2. Identify the consumer process.
3. Add a names-only row to `Env-Registry.md`.
4. Add or update the relevant example file (committed, no real values).
5. Add a verification command (a profile in your env-check script, an integration test, or a health probe).
6. If the key is secret or provider-owned, apply it through the incoming-staging workflow below.

Stop if the key has unclear ownership. Fix the registry row first.

## Lifecycle: applying a new or rotated value (incoming workflow)

Use the incoming-staging plane only for new or rotated values from an operator, password manager, or provider console. The workflow has eight steps and they are not optional:

1. Write new values to the incoming-staging file.
2. Classify every key into exactly one plane using the registry.
3. Reject keys that do not match the staging file's declared scope (a key for a different plane is not allowed through).
4. Apply accepted keys to the live target (the runtime source-of-truth file, the consumer-specific file, or the out-of-band backend).
5. Validate the target with the owning verify command.
6. Restart or refresh only the consumers that need it.
7. Pull back the runtime mirror.
8. Delete the incoming-staging file.

If any key has unclear ownership at step 2, stop and fix the registry before applying.

## Lifecycle: rotation

Define rotation by **class**, not by individual key. Each class has a cadence, a set of immediate triggers, an execution workflow, and a rollback policy.

| Class example | Cadence baseline | Immediate triggers |
|---|---|---|
| Admin/console keys | 30-90 days | role change, suspected leak |
| Webhook verification keys | 90 days | provider incident, signature failures |
| Auth-provider keys | 90 days or provider-mandated cycle | provider rotation, audience change |
| Per-host credentials | event-driven + periodic review | host replacement, suspected leak |
| Mail/notification provider keys | 90 days | sender-domain alert, provider incident |

Execution workflow per rotation:

1. **Precheck.** Confirm no active incident unless this is emergency rotation. Open a rotation ticket `rotation-<class>-<YYYYMMDD-HHMM>`.
2. **Deploy.** Update the secret source with the new value. Never print the value. Apply bounded reload/restart in the order the runbook specifies. Keep a rollback target prepared before reload.
3. **Postcheck.** Validate the old credential is rejected and the new credential is accepted. Validate the user journeys that depend on this credential. Observe error-rate and latency for 15 minutes against the alert baseline.
4. **Record.** Update names-only metadata in the inventory: owner, issue time, next due date, reason. Save evidence under a per-rotation timestamped path. Record evidence links in the ticket.

Rollback policy:

- If compromise is suspected, do not restore the old credential. Rotate forward again.
- If compromise is not suspected and service impact is immediate, restore the previous known-good reference, recover service, and schedule an immediate follow-up rotation.

### Atomic dual-backend rotation

If the same logical secret must live in two unrelated stores (typically because one consumer cannot mount the shared file — a serverless function, a third-party platform, a different security boundary), the two stores must rotate atomically. The runbook for that key states explicitly:

- which two backends hold the value
- which one is canonical (panel-authoritative vs runtime-authoritative)
- the exact order of update operations
- how the lagging consumer is forced to refresh (force-recreate the container, touch a no-op env var on the function, etc.)

Mark such keys clearly in the registry with a `dual-backend` note pointing to the rotation runbook.

## Security guardrails

- Never print secret values in terminal output, logs, repo docs, issue trackers, PR descriptions, or CI records.
- Store only names-only metadata and evidence pointers.
- Runtime probes log status codes and counters only, never the secret-bearing payload.
- File mode for any file containing real secret values is `0600`.
- `revoked: true` lines stay in the inventory for audit history; do not delete revoked rows.
- The example templates (`Env-Registry.example.md`, `Secrets-Inventory.example.yaml`) are the only credential-shaped files in git. Real registry and real inventory live under a gitignored path or outside the repo entirely.

## Where this fits in DevTopology

This system is parallel to the file-contracts system, not built on top of it:

- File contracts answer "is every source file accounted for and described".
- Credential planes answer "is every runtime secret in the right place and rotatable".

Both are about catching drift early. Neither is sufficient on its own.

DevTopology does not ship a credential-registry gate today. Projects that want one can add a bash or stdlib-Python check that scans the registry file for the substring `=` (a value leaked into a names-only doc) and scans for high-entropy tokens in committed files. See `docs/runtime/Manifest-Contract-System.md` for the gate output format to follow if you add one.
