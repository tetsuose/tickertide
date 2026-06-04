# DevTopology skill

Structure-aware gates for AI coding agents. This skill enforces file contracts, drift detection, and scope constraints.

## Workflow

### Before starting work

Run `make start QUERY="<your task>"` to load repo topology and detect drift. If `GATE_FAIL gate=structure_contract_coverage` appears, run `make writeback-apply WRITE=1` first.

### While working

1. **Stay in scope.** If a module is assigned via `make enforce-fill MODULE=<name>`, only modify files in that module.
2. **Update contracts.** When you create or substantially change a file, update its contract in `docs/runtime/File-Contracts.json`:
   - `purpose` — what the file does (one sentence)
   - `invariants` — what must remain true (constraints, not implementation)
   - `verification` — how to confirm correctness
3. **Advance stages.** Move files through `scaffolded` > `baseline` > `planned` > `implemented` > `verified` > `done` as work progresses. Never skip more than one stage.
4. **New files.** After creating files, run `make writeback-apply WRITE=1` to register them in the ledger. Then fill their contracts.

### Before committing

Run `make verify`. Both gates must pass:

- `GATE_PASS gate=structure_contract_coverage` — every file has a ledger entry, no stale entries
- `GATE_PASS gate=changed_file_contract_semantics` — every changed file has non-placeholder contracts

If a gate fails, fix the issue before committing. Do not skip gates.

### Task isolation

For parallel tasks, use worktrees:

```bash
make task-open QUERY="add auth endpoint"   # creates branch + worktree
# ... do work in the worktree ...
make task-check                             # fail if dirty
make task-close                             # check PR status, suggest next action
```

## Key files

| File | Role |
|------|------|
| `devtopology.yaml` | Project config — exclusions, protected branches, gate settings |
| `docs/runtime/File-Contracts.json` | The ledger — tracked in git, one entry per file |
| `docs/runtime/Credentials-Management.md` | Credential plane model + lifecycle (parallel system, advisory) |
| `docs/runtime/Env-Registry.example.md` | Names-only env registry template |
| `docs/runtime/Secrets-Inventory.example.yaml` | Operational asset + credential inventory template |
| `engine/index.py` | Core engine — mirror, atlas, contracts, gates, writeback |
| `scripts/worktree.sh` | Task isolation via git worktrees |

## Credentials (parallel system)

File contracts cover source files. Runtime credentials get a separate discipline:

- Every runtime secret belongs to exactly **one credential plane** (operator-control / runtime-sot / mirror / incoming-staging / consumer-specific / out-of-band-backend). Planes have hard boundaries — a key in one plane must not appear in another.
- The **names-only registry** at `docs/runtime/Env-Registry.md` records `env_key | source_file | runtime_injection | primary_consumers | verify_gate`. Never put values in this file.
- The **inventory** at `secrets-inventory.yaml` (gitignored) holds the real asset and credential checklist with rotation timestamps. Only the `.example.yaml` template lives in git.
- When applying new or rotated values: use the incoming-staging workflow (8 steps) in `Credentials-Management.md`. Never edit a runtime-sot file from the local mirror.
- When the same logical secret lives in two stores, rotation must be **atomic** across both. Mark such keys clearly in the registry.

DevTopology does not gate this today. Treat it as discipline plus templates.

## Gate output format

All gates emit structured lines. Parse them, don't regex logs:

```
GATE_PASS gate=<name> <key>=<value> ...
GATE_FAIL gate=<name> <key>=<value> ... fix="<remediation>"
```

## Rules

- Never commit with `GATE_FAIL` in verify output
- Never leave placeholder contracts (`TODO`, `TBD`, `...`) in changed files
- Never add external Python dependencies to `engine/index.py`
- Always run `make writeback-apply WRITE=1` after adding or removing files
- Contracts describe *what* and *why*, not *how* — no implementation details in contracts
