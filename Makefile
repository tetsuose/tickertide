SHELL := /bin/bash
export PYTHONDONTWRITEBYTECODE := 1

.PHONY: help \
        start mirror atlas context verify health health-strict \
        writeback-preview writeback-apply enforce-fill gate-report \
        task-open task-check task-status task-close route accept \
        ingest compute export serve pipeline

ENGINE ?= engine/index.py
QUERY ?=
LOG ?= .index/health/verify-output-latest.log
MODULE ?=
STAGES ?= scaffolded,baseline,planned,implemented,verified,done
TASK_KIND ?= feat
BASE ?= origin/main
WORKTREE_ROOT ?= ../.worktrees
GOAL ?=

help:
	@echo ""
	@echo "  TickerTide — US equity momentum monitor + built-in agent workflow"
	@echo ""
	@echo "  Workflow Routing (read this first on a new task)"
	@echo "    make route                    Print docs-only / branch / structure-trigger routing"
	@echo "    make task-open QUERY='...'     Create isolated worktree + branch"
	@echo "    make task-status              Print branch/worktree state"
	@echo "    make task-check               Fail if worktree is dirty"
	@echo "    make task-close               Check PR status + next action"
	@echo "    make accept GOAL='...'         Render the acceptance comment for this task"
	@echo ""
	@echo "  Structure Awareness (devtopology)"
	@echo "    make start QUERY='...'         Generate atlas-pack + detect drift"
	@echo "    make mirror                   File-level inventory (JSON)"
	@echo "    make atlas                    Module/kind/stage aggregation (JSON)"
	@echo "    make context QUERY='...'       LLM-readable context (Markdown)"
	@echo ""
	@echo "  Contract Enforcement (devtopology)"
	@echo "    make verify                   Run structure + semantic gates"
	@echo "    make health                   Full health summary"
	@echo "    make health-strict            Health + non-zero exit on failure"
	@echo "    make gate-report LOG=...       Parse GATE_PASS/FAIL from log"
	@echo "    make writeback-preview        Preview missing/stale contracts"
	@echo "    make writeback-apply WRITE=1   Sync File-Contracts.json"
	@echo "    make enforce-fill MODULE=...   Restrict changes to one module"
	@echo ""
	@echo "  Data Pipeline (placeholders until M0 — see docs/PRD.md §13)"
	@echo "    make ingest                   Stooq + Nasdaq screener + EDGAR pull"
	@echo "    make compute                  DuckDB: derived_daily + composite + valuation"
	@echo "    make export                   Snapshot -> Parquet/JSON shards"
	@echo "    make serve                    Local preview of the static client"
	@echo "    make pipeline                 ingest -> compute -> export (nightly cron body)"
	@echo ""

# --- Workflow Routing ---

route:
	@python3 scripts/task_router.py

accept:
	@python3 scripts/render_acceptance_comment.py --goal "$(GOAL)"

# --- Structure Awareness ---

start:
	@python3 $(ENGINE) start --query "$(QUERY)"

mirror:
	@python3 $(ENGINE) mirror

atlas:
	@python3 $(ENGINE) atlas

context:
	@python3 $(ENGINE) context --query "$(QUERY)"

# --- Contract Enforcement ---

verify:
	@mkdir -p .index/health
	@set -o pipefail; python3 $(ENGINE) verify | tee .index/health/verify-output-latest.log

health:
	@mkdir -p .index/health
	@set -o pipefail; python3 $(ENGINE) health | tee .index/health/health-output-latest.log

health-strict:
	@mkdir -p .index/health
	@set -o pipefail; python3 $(ENGINE) health --strict | tee .index/health/health-output-latest.log

gate-report:
	@python3 $(ENGINE) gate-report --log "$(LOG)"

writeback-preview:
	@python3 $(ENGINE) writeback-preview

writeback-apply:
	@WRITE=$(WRITE) python3 $(ENGINE) writeback-apply

enforce-fill:
	@WRITE=$(WRITE) python3 $(ENGINE) enforce-fill --module "$(MODULE)" --allowed-stages "$(STAGES)"

# --- Task Isolation ---

task-open:
	@DEVTOPOLOGY_BASE="$(BASE)" DEVTOPOLOGY_WORKTREE_ROOT="$(WORKTREE_ROOT)" \
		bash scripts/worktree.sh open --query "$(QUERY)" --kind "$(TASK_KIND)" --base "$(BASE)" --root "$(WORKTREE_ROOT)"

task-check:
	@bash scripts/worktree.sh check

task-status:
	@DEVTOPOLOGY_BASE="$(BASE)" bash scripts/worktree.sh status --base "$(BASE)"

task-close:
	@DEVTOPOLOGY_BASE="$(BASE)" bash scripts/worktree.sh close --base "$(BASE)"

# --- Data Pipeline (placeholders) ---
# These print their intended command and exit 0 until the corresponding milestone
# lands real code. Replace the echo with the runner when implementing M0+.

ingest:
	@echo "[ingest] not yet implemented (M0). Will run: python3 ingest/run.py  — see docs/PRD.md §13, ingest/README.md"

compute:
	@echo "[compute] not yet implemented (M0). Will run: python3 compute/run.py — see docs/PRD.md §13, compute/README.md"

export:
	@echo "[export] not yet implemented (M2). Will run: python3 export/run.py  — see docs/PRD.md §13, export/README.md"

serve:
	@echo "[serve] not yet implemented (M2). Will serve web/ statically       — see docs/PRD.md §13, web/README.md"

pipeline: ingest compute export
	@echo "[pipeline] nightly body = ingest -> compute -> export (GitHub Actions cron, post-US-close)"
