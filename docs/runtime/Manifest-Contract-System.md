# Manifest Contract System

This document describes the contract system used by DevTopology to track file purpose, invariants, and verification across a repository.

## Core concept

Every file in the repository has a **contract entry** in `File-Contracts.json`. A contract answers three questions:

1. **Purpose** — What does this file do?
2. **Invariants** — What must remain true about this file?
3. **Verification** — How do you confirm this file is correct?

Contracts are not documentation. They are machine-enforced constraints. Gates check that contracts exist and are filled in before changes can pass.

## Ledger structure

`docs/runtime/File-Contracts.json` is the single source of truth:

```json
{
  "version": 1,
  "updated_at": "2026-04-07T...",
  "policy": {
    "stage_values": ["scaffolded", "baseline", "planned", "implemented", "verified", "done", "deprecated"],
    "replan_rule": "When repo structure changes, run `make writeback-apply WRITE=1` before continuing."
  },
  "entries": [ ... ],
  "retired_entries": [ ... ],
  "last_structure_digest": "sha256..."
}
```

### Entry format

```json
{
  "path": "engine/index.py",
  "kind": "code",
  "module": "engine",
  "stage": "implemented",
  "contract": {
    "purpose": "Core engine implementing the mirror/atlas/contracts/writeback/gates pipeline",
    "invariants": "Zero external dependencies; all gate output uses GATE_PASS/GATE_FAIL format",
    "verification": "make start, make verify, and make writeback-apply all complete without error"
  },
  "notes": ""
}
```

### Fields

| Field | Source | Description |
|-------|--------|-------------|
| `path` | Auto-detected | Relative path from repo root |
| `kind` | Auto-detected | `code`, `config`, `doc`, `script`, `test`, `asset` |
| `module` | Auto-detected | First directory component (`.` for root files) |
| `stage` | Manual | Maturity level (see below) |
| `contract.purpose` | Manual | One sentence: what the file does |
| `contract.invariants` | Manual | Constraints that must hold — not implementation details |
| `contract.verification` | Manual | How to verify correctness |
| `notes` | Manual | Free-form, optional |

## Stages

Stages track file maturity. They progress in order:

| Stage | Meaning |
|-------|---------|
| `scaffolded` | File exists but has no content (0 lines) |
| `baseline` | File has content but no contract filled in |
| `planned` | Contract written, implementation not started |
| `implemented` | Working code, contracts filled |
| `verified` | Tests or manual verification confirm correctness |
| `done` | Stable, no further changes expected |
| `deprecated` | Scheduled for removal |

Rules:
- New files with 0 lines start at `scaffolded`. Files with content start at `baseline`.
- `writeback-apply` auto-assigns initial stages. All subsequent stage changes are manual.
- Do not skip more than one stage at a time.

## Drift detection

**Drift** occurs when the actual files in the repo don't match the ledger:

- **Missing entries** — A file exists in git but has no entry in the ledger.
- **Stale entries** — An entry exists in the ledger but the file no longer exists.

`make writeback-preview` shows drift without changing anything. `make writeback-apply WRITE=1` fixes it:
- Missing files get new entries with default (placeholder) contracts.
- Stale entries move to `retired_entries`.

### Structure digest

The ledger stores a `last_structure_digest` — a sha256 hash of all tracked file paths and their sizes. When the digest changes, the structure has changed and contracts may need updating.

## Gates

Three gates enforce the contract system:

### 1. structure_contract_coverage

Checks that every file has a ledger entry and no entries are stale.

```
GATE_PASS gate=structure_contract_coverage files=9
GATE_FAIL gate=structure_contract_coverage missing=2 stale=1 fix="make writeback-apply WRITE=1"
```

**Fix:** Run `make writeback-apply WRITE=1`.

### 2. changed_file_contract_semantics

Checks that every changed file (git diff + staged + untracked) has non-placeholder contract values for `purpose`, `invariants`, and `verification`.

```
GATE_PASS gate=changed_file_contract_semantics changed=5 validated=4
GATE_FAIL gate=changed_file_contract_semantics changed=5 violations=2 fix="Fill purpose/invariants/verification"
```

Placeholder values that trigger failure: `TODO`, `TBD`, `...`, `FIXME`, `PLACEHOLDER`, and any value starting with `TODO:` or `TBD:`.

**Fix:** Edit the contract in `File-Contracts.json` for each violating file.

### 3. fill_queue_scope

Checks that changed files belong to a declared module and allowed stages. Used to prevent an agent from touching files outside its assigned scope.

```
GATE_PASS gate=fill_queue_scope changed=3 allowed=3 module=api
GATE_FAIL gate=fill_queue_scope changed=3 violations=1 fix="Constrain edits to allowed module/stages."
```

**Fix:** Only modify files in the assigned module and stage range.

## Configuration

All settings live in `devtopology.yaml`:

```yaml
# Which files are exempt from scope enforcement
fill_exempt:
  - "docs/runtime/File-Contracts.json"

# Which stages allow modifications via enforce-fill
fill_allowed_stages:
  - planned
  - implemented
  - verified
  - done
```

## Lifecycle

1. **Bootstrap** — Run `make writeback-apply WRITE=1` to create entries for all existing files.
2. **Fill contracts** — Replace placeholder `TODO` values with real purpose/invariants/verification.
3. **Work** — Create/modify files. Run `make writeback-apply WRITE=1` after structural changes.
4. **Verify** — Run `make verify` before committing. Both gates must pass.
5. **Maintain** — As files evolve, update contracts and advance stages.
