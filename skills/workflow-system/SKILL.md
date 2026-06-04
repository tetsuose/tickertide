---
name: workflow-system
description: Route TickerTide PR/task workflow — task-start isolation, docs-only/branch routing, structure-gate triggers, verify/health diagnosis, acceptance comment generation, and the merge-boundary policy. Use when an agent needs the repo workflow policy, the right lane for a change, or a deterministic workflow helper command.
---

# Workflow System (TickerTide)

PR-driven repository workflow. Pairs with `$devtopology` (file contracts + gates).
Stable policy lives in `docs/workflow/WORKFLOW.md`; this skill is the operational recipe.

## Setup / Defaults

- Run from the repo root (the directory with `Makefile` + `devtopology.yaml`).
- Acceptance SoT = the latest PR acceptance comment + gate outputs. Not chat, not scratch notes.
- When implementation looks complete, run the closeout flow: local verify → self-fix until gates pass or a real blocker remains → commit → push → ready PR → acceptance comment → merge → `make task-close`. Do not stop at an open PR unless a real blocker remains or the user asked for a hold.

## Mandatory Pre-flight (enforced, not advisory)

- **One worktree = one merge intent.** Before starting, if the worktree already carries a different merge intent, `make task-open` a new one. `branch/PR` is the only merge boundary.
- **`make route` gates every task start.** Run it before implementation:
  - `STRUCTURE_TRIGGER=none` → do NOT run structure commands (start/mirror/atlas/writeback/enforce-fill).
  - `DOCS_ONLY=1` → all changes stay in `docs/` (excluding the ledger); mixing in implementation forces a worktree split.
  - Non-empty `WARNINGS` → address each before proceeding.
- **Visibility/availability issues require three-layer triage before `task-open`** (definition/repo → registration/host → active session). Only a missing repo definition justifies a repo task/PR; registration or session issues are fixed locally or by restart — do not escalate into product code changes.
- **Entry files are thin.** `CLAUDE.md` / `AGENTS.md` declare rules and navigation only; they never carry rolling state.

## First Reads

- `docs/workflow/WORKFLOW.md` — authority order, merge boundaries, decision gate, auto-merge.
- `docs/PRD.md` — product spec (the SoT for what to build).
- `skills/devtopology/SKILL.md` — when a change is structural or needs a contract gate.

## Task Routing

- New isolated task: `make task-open QUERY="..."`
- Start routing / docs-only / branch suggestion: `make route` (= `python3 scripts/task_router.py`).
  - Its `DOCS_ONLY` / `WORKFLOW_ONLY` / `STRUCTURE_TRIGGER` / `WARNINGS` determine the lane. Force a lane with `--structural` / `--planning` / `--gate`.
  - Follow its `NEXT_READS` and `NEXT_COMMANDS`.
- Structure work (drift, mirror, atlas, writeback, enforce-fill): use `$devtopology`.
- Generate an acceptance comment: `make accept GOAL="..."` (= `python3 scripts/render_acceptance_comment.py`).
- Close out a task: `make task-close`.

## Structure-Gate Triggers (only these three)

- `A` structural change → `engine/ gate/ scripts/ docs/runtime/ Makefile devtopology.yaml`, module roots.
- `B` planning task aligning spec/contracts → `docs/PRD.md`, `docs/BUILD-PLAN.md`, module READMEs.
- `C` gate / coverage / scope → `File-Contracts` coverage or `enforce-fill`.

Triggered command set:
```bash
make start QUERY="..."          # topology + drift
make verify                     # both gates must GATE_PASS
make writeback-preview          # before any apply
make writeback-apply WRITE=1    # sync ledger (explicit WRITE=1)
make enforce-fill MODULE=<m>    # restrict scope
```

## Gate Diagnosis

- `make verify` then `make health`; strict audit `make health-strict`.
- `structure_contract_coverage` fail → `make writeback-preview` → `make writeback-apply WRITE=1` → `make verify`.
- `changed_file_contract_semantics` fail → fill `purpose`/`invariants`/`verification` for the flagged path in `docs/runtime/File-Contracts.json` (no placeholders).
- Reports: `.index/health/verify-output-latest.log`, `.index/writeback/*`.

## Key Gotchas

- Do not treat `.index/*`, notes, or logs as acceptance SoT.
- Do not treat docs/contracts/plans as proof of runtime availability; probe first.
- Always `writeback-preview` before `writeback-apply`.
- Do not parallelize causally dependent steps (commit→push, edit→verify).
- Do not wrap a broken mechanism in another long-lived one; replace it.
- The FS is case-insensitive (`core.ignorecase=false` is set) — never introduce case-only path variants.

## Helper Scripts

- `scripts/task_router.py` — read-only lane router.
- `scripts/render_acceptance_comment.py` — acceptance comment renderer.
- `scripts/worktree.sh` — task isolation (via `make task-open/check/status/close`).
