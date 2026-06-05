#!/usr/bin/env python3
"""Route a TickerTide task into docs-only / branch / structure-trigger lanes.

Read-only: never mutates repo state. Output is mandatory routing for the agent.
Adapted from the vpn-ops workflow-system task_router; paths are TickerTide-native
and there is no dependency on an external detect_docs_only.sh.

Lanes:
  DOCS_ONLY=1        every change is product/reference docs -> docs branch
  WORKFLOW_ONLY=1    every change is workflow/guardrail/topology plumbing
  STRUCTURE_TRIGGER  A (structural) / B (planning) / C (gate) -> run devtopology
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[1]

# Pure documentation: product spec + reference docs. The structure ledger is
# explicitly NOT docs-only (it is a gate artifact -> structure trigger).
DOCS_ONLY_PREFIXES = ("docs/",)
DOCS_ONLY_EXCLUDE = {"docs/runtime/File-Contracts.json"}

# Workflow / guardrail / repo-routing plumbing.
WORKFLOW_ROUTING_PREFIXES = (
    "engine/",
    "gate/",
    "scripts/",
    "skills/",
    ".github/",
    "docs/workflow/",
    "docs/agent-state/",
)
WORKFLOW_ROUTING_EXACT = {
    "Makefile",
    "devtopology.yaml",
    ".gitignore",
    ".gitattributes",
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "docs/runtime/File-Contracts.json",
}

# Trigger A — structural change (topology, engine, tooling, module roots).
STRUCTURAL_PREFIXES = ("engine/", "gate/", "scripts/", "docs/runtime/")
STRUCTURAL_EXACT = {"Makefile", "devtopology.yaml"}

# Trigger B — planning task that aligns spec/plan/contracts.
PLANNING_EXACT = {
    "docs/PRD.md",
    "docs/BUILD-PLAN.md",
    "docs/workflow/WORKFLOW.md",
}
PLANNING_SUFFIXES = ("/README.md",)  # module plan docs

# Product implementation modules (BUILD-PLAN architecture).
PRODUCT_MODULES = ("ingest", "compute", "export", "web", "themes")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route a TickerTide task without mutating repo state.")
    parser.add_argument("--paths", action="append", default=[],
                        help="Explicit path(s), comma-separated. Default: current git diff + untracked.")
    parser.add_argument("--structural", action="store_true", help="Force structure trigger A.")
    parser.add_argument("--planning", action="store_true", help="Force structure trigger B.")
    parser.add_argument("--gate", action="store_true", help="Force structure trigger C (gate/enforce-fill/writeback).")
    return parser.parse_args()


def normalize(path: str) -> str:
    p = path.strip()
    while p.startswith("./"):
        p = p[2:]
    return p


def is_runtime_artifact(path: str) -> bool:
    p = normalize(path)
    return "__pycache__/" in p or p.endswith(".pyc") or p.startswith(".index/")


def collect_git_paths() -> list[str]:
    cmd = (
        "{ git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; "
        "git ls-files --others --exclude-standard 2>/dev/null; } | awk 'NF' | sort -u"
    )
    proc = subprocess.run(["bash", "-lc", cmd], cwd=REPO_ROOT, capture_output=True, text=True)
    return [normalize(l) for l in proc.stdout.splitlines() if l.strip() and not is_runtime_artifact(l.strip())]


def split_paths(values: list[str]) -> list[str]:
    out: list[str] = []
    for item in values:
        for part in item.split(","):
            part = part.strip()
            if part and not is_runtime_artifact(part):
                out.append(normalize(part))
    return out


def is_docs_path(p: str) -> bool:
    return p not in DOCS_ONLY_EXCLUDE and any(p.startswith(x) for x in DOCS_ONLY_PREFIXES)


def is_workflow_path(p: str) -> bool:
    return p in WORKFLOW_ROUTING_EXACT or any(p.startswith(x) for x in WORKFLOW_ROUTING_PREFIXES)


def looks_structural(p: str) -> bool:
    return p in STRUCTURAL_EXACT or any(p.startswith(x) for x in STRUCTURAL_PREFIXES)


def looks_planning(p: str) -> bool:
    return p in PLANNING_EXACT or any(p.endswith(s) for s in PLANNING_SUFFIXES)


def product_module_of(p: str) -> str | None:
    head = p.split("/", 1)[0]
    return head if head in PRODUCT_MODULES else None


def current_branch() -> str:
    proc = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                          cwd=REPO_ROOT, capture_output=True, text=True)
    b = proc.stdout.strip()
    return b if b and b != "HEAD" else "main"


def suggest_branch(paths: list[str], docs_only: bool, workflow_only: bool) -> str:
    stamp = datetime.now().strftime("%Y%m%d")
    if docs_only:
        return f"docs/{stamp}-docs-update"
    if workflow_only:
        return f"chore/workflow-{stamp}-routing-guardrails"
    # Shared convention with scripts/worktree.sh + WORKFLOW.md §2:
    # <prefix>/<date>-<descriptor>, date-first for every lane.
    modules = sorted({m for m in (product_module_of(p) for p in paths) if m})
    if modules:
        return f"feat/{stamp}-{'-'.join(modules)}"
    return current_branch()


def determine_triggers(args: argparse.Namespace, paths: list[str]) -> list[str]:
    triggers: list[str] = []
    if args.structural or any(looks_structural(p) for p in paths):
        triggers.append("A")
    if args.planning or any(looks_planning(p) for p in paths):
        triggers.append("B")
    if args.gate:
        triggers.append("C")
    return triggers


def build_reads(docs_only: bool, triggers: list[str]) -> list[str]:
    reads = ["docs/workflow/WORKFLOW.md", "skills/workflow-system/SKILL.md"]
    if triggers:
        reads.append("skills/devtopology/SKILL.md")
    if "B" in triggers:
        reads.append("docs/PRD.md")
    return reads


def build_commands(docs_only: bool, triggers: list[str], has_paths: bool, module: str | None) -> list[str]:
    cmds: list[str] = []
    if not has_paths:
        cmds.append('make task-open QUERY="..."')
    if triggers:
        cmds.append('make start QUERY="..."')
        cmds.append("make verify")
    if "A" in triggers or "C" in triggers:
        cmds.append("make writeback-preview")
        cmds.append("make writeback-apply WRITE=1")
    if "C" in triggers and module:
        cmds.append(f"make enforce-fill MODULE={module}")
    elif "C" in triggers:
        cmds.append("make enforce-fill MODULE=<module>")
    cmds.append('make accept GOAL="..."')
    cmds.append("make task-close")
    return cmds


def main() -> int:
    args = parse_args()
    explicit = split_paths(args.paths)
    paths = explicit if explicit else collect_git_paths()
    branch = current_branch()

    docs_only = bool(paths) and all(is_docs_path(p) for p in paths)
    workflow_only = bool(paths) and all(is_workflow_path(p) for p in paths)
    triggers = determine_triggers(args, paths)
    modules = sorted({m for m in (product_module_of(p) for p in paths) if m})
    suggested = suggest_branch(paths, docs_only, workflow_only)

    warnings: list[str] = []
    if not paths:
        warnings.append('No changed files detected; for a new task start with `make task-open QUERY="..."`.')
    if docs_only and triggers:
        warnings.append("Docs-only routing and structure triggers both active; confirm the task is not mixing concerns.")
    if len(modules) > 1:
        warnings.append(f"Change set spans multiple product modules {modules}; if these are separate merge intents, split into one worktree each.")
    mixes_workflow = paths and any(is_workflow_path(p) for p in paths) and any(not is_workflow_path(p) for p in paths)
    if mixes_workflow:
        warnings.append("Change set mixes workflow/topology plumbing with product files; if unintentional, split with a new task worktree.")
    if branch in ("main", "master") and paths:
        warnings.append(f"On protected branch '{branch}'; open a dedicated worktree before implementing: make task-open QUERY=\"...\" (suggested: {suggested}).")

    module = modules[0] if len(modules) == 1 else None
    reads = build_reads(docs_only, triggers)
    commands = build_commands(docs_only, triggers, bool(paths), module)

    print(f"DOCS_ONLY={1 if docs_only else 0}")
    print(f"WORKFLOW_ONLY={1 if workflow_only else 0}")
    print(f"CURRENT_BRANCH={branch}")
    print(f"SUGGESTED_BRANCH={suggested}")
    print(f"PRODUCT_MODULES={json.dumps(modules, ensure_ascii=True)}")
    print(f"STRUCTURE_TRIGGER={'+'.join(triggers) if triggers else 'none'}")
    print(f"NEXT_READS={json.dumps(reads, ensure_ascii=True)}")
    print(f"NEXT_COMMANDS={json.dumps(commands, ensure_ascii=True)}")
    print(f"WARNINGS={json.dumps(warnings, ensure_ascii=True)}")
    print("BLOCKERS=[]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
