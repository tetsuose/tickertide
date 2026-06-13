SHELL := /bin/bash
export PYTHONDONTWRITEBYTECODE := 1

.PHONY: help \
        start mirror atlas context verify health health-strict \
        writeback-preview writeback-apply enforce-fill gate-report \
        task-open task-check task-status task-close route accept \
        ingest fundamentals themes theme-extract compute export ocean-c9 rotation-c9 theme-c9 valuation-c9 serve pipeline check check-theme check-land \
        fixture fixture-pipeline \
        web-install web-build web-test web-dev

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
	@echo "  Data Pipeline (M0-M4 live — see docs/PRD.md §13)"
	@echo "    make ingest                   Nasdaq universe + price bars (yfinance)"
	@echo "    make fundamentals             SEC EDGAR companyfacts -> fundamentals_q"
	@echo "    make themes                   theme_membership: seed bootstrap + land approved files (M4.5)"
	@echo "    make theme-extract TICKER=X   M4.5 operator step: EDGAR 10-K -> LLM candidates (claude CLI)"
	@echo "    make compute                  DuckDB: composite + valuation + theme index + RS-Ratio (sector/theme)"
	@echo "    make check                    AC-M0 + AC-M4 acceptance checks on the DB"
	@echo "    make pipeline                 ingest -> fundamentals -> themes -> compute -> check"
	@echo "    make export                   board + ocean + rotation(+theme) + manifest -> web/public/data"
	@echo "    make ocean-c9                 AC-M2 C9: ocean.json positions == board/Stock numbers"
	@echo "    make theme-c9                 AC-M4 C9: rotation.theme.json league == board PIT theme chips"
	@echo ""
	@echo "  Web Client (M1/M2 — Vite + React + TS; run web-install once)"
	@echo "    make web-install              Install web/ npm deps"
	@echo "    make web-test                 vitest: C9 parity + AC-M1/M2 render gate"
	@echo "    make web-build                export -> npm build -> web/dist (static artifact)"
	@echo "    make web-dev                  export -> npm dev (local live preview)"
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
# M0-M1 live: ingest/fundamentals/compute/check + export (board.json). Product code
# uses requirements.txt deps (duckdb/yfinance/pandas/numpy) in a venv + web/ uses npm;
# the workflow engine (engine/index.py) stays stdlib-only.
# Pass runner flags via PIPELINE_ARGS, e.g. make ingest PIPELINE_ARGS="--limit 500".

PIPELINE_ARGS ?=

ingest:
	@python3 ingest/run.py $(PIPELINE_ARGS)
	@python3 ingest/sector_etf.py

fundamentals:
	@python3 ingest/edgar.py $(PIPELINE_ARGS)

# M4.1 seed bootstrap + M4.5 approved landing (both idempotent). The nightly DB is
# rebuilt from scratch, so membership must be re-landed every pipeline run: seed clears
# + reseeds the coarse baseline, then land.py replays the human-approved files
# (themes/approved/*.json, committed — git is the durable store). PIT resolution prefers
# the approved row where its as_of is later. Extraction itself (themes/extract.py,
# claude CLI on plan quota + human review) is an OPERATOR step, never run in CI:
#   make theme-extract TICKER=NVDA   then   python3 themes/review.py --ticker NVDA ...
themes:
	@python3 themes/seed.py
	@python3 themes/land.py

theme-extract:
	@test -n "$(TICKER)" || (echo "usage: make theme-extract TICKER=NVDA" && exit 1)
	@python3 themes/run.py --ticker $(TICKER)

# AC for M4.5: land + point-in-time precedence (approved wins forward, seed intact
# backward) over themes/approved/*.json. Self-contained (temp DB), runs offline in CI.
check-land:
	@python3 themes/check_land.py

compute:
	@python3 compute/run.py
	@python3 compute/valuation.py
	@python3 compute/theme_index.py
	@python3 compute/rotation.py
	@python3 compute/rotation.py --bucket-type theme

check: check-theme
	@python3 compute/check.py

# AC-M4 (PRD §14): PIT membership shape + C3 no-retro + C4 cap-bound weights.
# Skips cleanly (exit 0) when theme_membership is empty — `make compute` on a bare DB
# must not hard-fail before `make themes` ran.
check-theme:
	@python3 compute/check_theme.py

export:
	@python3 export/board.py $(PIPELINE_ARGS)
	@python3 export/ocean.py
	@python3 export/rotation.py
	@python3 export/rotation.py --bucket-type theme
	@python3 export/valuation_parquet.py
	@python3 export/stock_bundle.py
	@python3 export/manifest.py
	@echo "[export] board + ocean + rotation(+theme) + valuation.parquet + stock bundles + manifest -> web/public/data/ (M5.1/M5.3)."

# C9 cross-surface check (AC-M2): ocean.json positions trace to board/Stock numbers.
ocean-c9:
	@python3 export/check_ocean.py

# C9 cross-surface check (AC-M3): rotation.json league traces to board.json members.
rotation-c9:
	@python3 export/check_rotation.py

# C9 cross-surface check (AC-M4): theme league PIT members trace to board theme chips.
theme-c9:
	@python3 export/check_rotation.py --rotation web/public/data/rotation.theme.json

# C9 cross-surface check (AC-M5): valuation.parquet + stock bundles trace to board.json.
valuation-c9:
	@python3 export/check_valuation.py

serve: web-dev

pipeline: ingest fundamentals themes compute check
	@echo "[pipeline] end-to-end complete: ingest -> fundamentals -> themes -> compute -> check (nightly cron body)"

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

# --- Web Client (M1) ---
# Vite + React + TS static client. `export` (board.json) is the runtime data; the
# build bundles it from public/data into web/dist. web/node_modules + web/dist are
# gitignored. Run `make web-install` once, then web-test / web-build / web-dev.

web-install:
	@cd web && npm install

web-test:
	@cd web && npm test

web-build: export
	@cd web && npm run build
	@echo "[web-build] static client -> web/dist (board.json bundled from public/data)."

web-dev: export
	@cd web && npm run dev
