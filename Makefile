SHELL := /bin/bash
export PYTHONDONTWRITEBYTECODE := 1

.PHONY: help \
        start mirror atlas context verify health health-strict \
        writeback-preview writeback-apply enforce-fill gate-report \
        task-open task-check task-status task-close route accept \
        ingest fundamentals compute export serve pipeline check \
        fixture fixture-pipeline

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
	@echo "  Data Pipeline (M0 live; export/serve are M2 placeholders — see docs/PRD.md §13)"
	@echo "    make ingest                   Nasdaq universe + price bars (yfinance)"
	@echo "    make fundamentals             SEC EDGAR companyfacts -> fundamentals_q"
	@echo "    make compute                  DuckDB: derived_daily (composite) + valuation_daily"
	@echo "    make check                    AC-M0 acceptance check on the DB"
	@echo "    make pipeline                 ingest -> fundamentals -> compute -> check (M0 end-to-end)"
	@echo "    make export                   [M2] Snapshot -> Parquet/JSON shards"
	@echo "    make serve                    [M2] Local preview of the static client"
	@echo ""
	@echo "  Offline Verification (no network — for web/export/CI; see compute/fixture.py)"
	@echo "    make fixture                  Build a synthetic data/tickertide.duckdb (deterministic)"
	@echo "    make fixture-pipeline         fixture -> compute -> valuation (offline; then export/check)"
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

# --- Data Pipeline ---
# M0 is live: ingest/fundamentals/compute/check run real code. export/serve are M2
# placeholders. Product code uses requirements.txt deps (duckdb/yfinance/pandas/numpy)
# in a venv; the workflow engine (engine/index.py) stays stdlib-only.
# Pass runner flags via PIPELINE_ARGS, e.g. make ingest PIPELINE_ARGS="--limit 500".

PIPELINE_ARGS ?=

ingest:
	@python3 ingest/run.py $(PIPELINE_ARGS)

fundamentals:
	@python3 ingest/edgar.py $(PIPELINE_ARGS)

compute:
	@python3 compute/run.py
	@python3 compute/valuation.py

check:
	@python3 compute/check.py

export:
	@echo "[export] M2 — will run: python3 export/run.py (Parquet/JSON shards). See docs/PRD.md §13, export/README.md."

serve:
	@echo "[serve] M2 — will serve web/ statically. See docs/PRD.md §13, web/README.md."

pipeline: ingest fundamentals compute check
	@echo "[pipeline] M0 end-to-end complete: ingest -> fundamentals -> compute -> check (nightly cron body)"

# --- Offline Verification Fixture ---
# Synthetic, deterministic DuckDB for verifying compute/export/web WITHOUT network
# (real ingest needs api.nasdaq.com + Yahoo/yfinance, often unreachable in CI/sandbox).
# Product code: uses requirements.txt deps (duckdb/numpy/pandas) in a venv; the
# devtopology engine stays stdlib-only. Tune via FIXTURE_ARGS, e.g.
#   make fixture FIXTURE_ARGS="--tickers 50 --days 400 --seed 7"

FIXTURE_ARGS ?=

fixture:
	@python3 compute/fixture.py $(FIXTURE_ARGS)

fixture-pipeline: fixture compute
	@echo "[fixture-pipeline] synthetic DB -> derived_daily + valuation_daily ready (offline). Next: python3 export/board.py; make check"
