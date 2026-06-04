# AGENTS.md — TickerTide

> Cross-agent entry (Codex / Cursor / Copilot / Gemini CLI, [agents.md](https://agents.md) standard).
> Claude Code reads `CLAUDE.md`. Full policy: `docs/workflow/WORKFLOW.md`. Spec: `docs/PRD.md`.

## What this is

个人自用、盘后(EOD)、美股专属的 momentum + valuation 监控工具。
脊柱：一个 per-stock composite 引擎 → 五个 lens → 两个尺度 → 零常驻 backend。仅美股，不对外分发。

## Before starting work

```bash
make route                      # docs-only / branch / structure-trigger routing (mandatory read)
make task-open QUERY="<task>"    # isolated worktree + branch — one worktree = one merge intent
make start QUERY="<task>"        # load topology + detect drift
```

If `GATE_FAIL gate=structure_contract_coverage` appears: `make writeback-apply WRITE=1`.

## While working

- **New files:** `make writeback-apply WRITE=1` to register them, then fill contracts in `docs/runtime/File-Contracts.json`.
- **Changed files:** update the contract (`purpose` / `invariants` / `verification`) if the role changed. No placeholders (`TODO`/`TBD`).
- **Scope:** if assigned `make enforce-fill MODULE=<name>`, only touch files in that module.
- **Stay in spine:** five lenses share one per-stock engine; never fork five pipelines (see `docs/PRD.md` §4).

## Before committing

```bash
make verify     # both gates must GATE_PASS; GATE_FAIL is a hard stop
```

## Closeout

```bash
make accept GOAL="<goal>"        # render acceptance comment (single source of truth)
# open PR, then: gh pr merge <n> --merge --delete-branch
make task-close                  # merged or drop — do not stop at open PR without a real blocker
```

## Contract format

Every file has an entry in `docs/runtime/File-Contracts.json`:

```json
{
  "path": "compute/composite.py",
  "kind": "code",
  "module": "compute",
  "stage": "planned",
  "contract": {
    "purpose": "What this file does (one sentence)",
    "invariants": "What must remain true (constraints, not implementation)",
    "verification": "How to confirm correctness"
  }
}
```

Stages: `scaffolded` > `baseline` > `planned` > `implemented` > `verified` > `done` > `deprecated`.

## Rules

- `engine/index.py` is Python stdlib only — never add pip dependencies.
- `GATE_FAIL` is a hard stop. No placeholder contracts in changed files.
- One task, one worktree. `branch/PR` is the only merge boundary.
- No secrets / endpoints / passwords in repo, PR, or logs (see `docs/runtime/Credentials-Management.md`).
- Lowercase paths only; the FS is case-insensitive and `core.ignorecase=false` is set.
