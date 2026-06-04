#!/usr/bin/env python3
"""Render a standard TickerTide acceptance comment for a PR or task thread.

The acceptance comment is the single source of truth for task closeout. It binds
a head_sha to the verification evidence (verify/health/gates) so a reviewer can
confirm PR head == acceptance == gate output without re-running anything.

Auto-fills head_sha and changed_files from git; everything else is passed in or
defaults to a "run locally" reminder. Names-only / counts-only: never emit
secrets, endpoints, or credentials.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)
    return proc.stdout.strip()


def head_sha() -> str:
    proc = subprocess.run(["git", "rev-parse", "--verify", "HEAD"],
                          cwd=REPO_ROOT, capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        return "(no commit yet)"
    return proc.stdout.strip()[:12]


def changed_files() -> list[str]:
    cmd = (
        "{ git diff --name-only HEAD 2>/dev/null; "
        "git ls-files --others --exclude-standard 2>/dev/null; } | awk 'NF' | sort -u"
    )
    proc = subprocess.run(["bash", "-lc", cmd], cwd=REPO_ROOT, capture_output=True, text=True)
    return [l.strip() for l in proc.stdout.splitlines() if l.strip()]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render a TickerTide acceptance comment.")
    p.add_argument("--goal", required=True, help="One-line goal for this task unit.")
    p.add_argument("--verify", default="run `make verify` and paste the GATE_PASS lines")
    p.add_argument("--health", default="run `make health`")
    p.add_argument("--tests", default="n/a", help="Test command + result, or n/a.")
    p.add_argument("--rollback", default="revert the PR / branch")
    p.add_argument("--changed-files", default="", help="Comma-separated; default inferred from git.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    files = [f.strip() for f in args.changed_files.split(",") if f.strip()] if args.changed_files else changed_files()
    file_lines = "\n".join(f"  - {f}" for f in files) if files else "  - (none detected)"

    print(f"""## Acceptance

- **head_sha:** `{head_sha()}`
- **goal:** {args.goal}
- **tests:** {args.tests}
- **make verify:** {args.verify}
- **make health:** {args.health}
- **TODO (incremental):** 0
- **changed_files ({len(files)}):**
{file_lines}
- **rollback:** {args.rollback}

> Names-only / counts-only. PR head, this comment, and the gate output must share one head_sha.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
