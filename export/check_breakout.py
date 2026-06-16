"""base→breakout self-check: board.json breakout block traces to the engine (C9).

AC-M7 (PRD §14, 2026-06-16 spine pivot): the core engine is base→breakout (ignition
retired). board.py (export/board.py) ships each stock's brk_strength_pct / brk_strength /
the estimated changepoint brk_tau_date / the dimensionless features verbatim from
derived_daily, plus a recall-first `candidate` flag and base/τ/breakout 证据. This script
re-reads the exported board.json and proves the breakout block is internally consistent and
same-source, so a re-scoring / drift / gate bug fails loudly here instead of silently in
the Breakouts view:

  - coverage: every stock carries a breakout block with the 6 features;
  - ranges: brk_strength_pct∈[0,100], brk_strength>=0 (PRD §10.8);
  - candidate gate: `candidate` == (brk_strength_pct>=BRK_TOP_DECILE) EXACTLY — the recall-first
    top-decile gate, recomputed from the shipped number (NO persistence — ignition retired);
  - evidence trace: evidence.vol_mult == features.vsurge (brk_vsurge verbatim — the same-source
    identity guard, re-checked off the file);
  - non-empty: at least one candidate (else the Breakouts board would be empty — flagged, not
    fatal, since a quiet tape can have zero);
  - stock↔board same-source: a sample of per-name Stock bundles (export/stock_bundle.py) carry
    the SAME breakout block as board.json for that ticker — both assembled by board._breakout
    from the same derived_daily, so the Stock 诊断 and the Breakouts card never disagree (C9).

Runs on the exported board.json + stock bundles (see `make breakout-c9`). Exits non-zero on
any inconsistency so it can gate. Names/counts only — no secrets.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VSURGE_TOL = 1e-6   # evidence.vol_mult vs features.vsurge (both = brk_vsurge verbatim)
BRK_TOP_DECILE = 90  # PRD §10.8 (must match board.BRK_TOP_DECILE)

_FEATURE_KEYS = {"base_slope", "brk_slope", "drift_step", "fit_gain", "clearance", "vsurge"}
_EVIDENCE_KEYS = {"tau_date", "days_since_tau", "drift_step", "fit_gain", "clearance", "vol_mult", "ma50"}


def check(board: dict) -> tuple[bool, list[str], dict]:
    """Return (ok, problems, stats). Validates board.json's breakout block is same-source."""
    problems: list[str] = []
    stocks = board.get("stocks", [])
    top_decile = board.get("brk_top_decile")
    if top_decile is None:
        problems.append("board missing brk_top_decile (candidate gate undefined)")
        top_decile = BRK_TOP_DECILE

    n_brk = n_cand = vsurge_checked = 0
    for s in stocks:
        t = s.get("ticker")
        bk = s.get("breakout")
        if bk is None:
            problems.append(f"{t}: no breakout block (C9 coverage gap)")
            continue

        pct, strength = bk.get("brk_strength_pct"), bk.get("brk_strength")
        feats = bk.get("features") or {}
        if pct is not None:
            n_brk += 1
            if not (-1e-9 <= pct <= 100 + 1e-9):
                problems.append(f"{t}: brk_strength_pct={pct} out of [0,100]")
        if strength is not None and strength < -1e-9:
            problems.append(f"{t}: brk_strength={strength} < 0")
        if set(feats) != _FEATURE_KEYS:
            problems.append(f"{t}: breakout.features keys={sorted(feats)} != 6 expected")

        # candidate gate must EXACTLY equal the recall-first top-decile rule (PRD §10.8).
        want = pct is not None and pct >= top_decile
        if bool(bk.get("candidate")) != want:
            problems.append(
                f"{t}: candidate={bk.get('candidate')} but brk_strength_pct={pct} "
                f"(gate: pct>={top_decile} => {want})")
        if bk.get("candidate"):
            n_cand += 1

        # evidence.vol_mult must trace to the vsurge feature (brk_vsurge verbatim).
        ev = bk.get("evidence") or {}
        ev_v, feat_v = ev.get("vol_mult"), feats.get("vsurge")
        if ev_v is not None and feat_v is not None:
            vsurge_checked += 1
            if abs(ev_v - feat_v) > VSURGE_TOL:
                problems.append(f"{t}: evidence.vol_mult={ev_v} != features.vsurge={feat_v}")

    if n_cand == 0:
        problems.append("zero base→breakout candidates — Breakouts board would be empty")

    stats = {
        "stocks": len(stocks),
        "breakout_coverage": n_brk,
        "candidates": n_cand,
        "vsurge_checked": vsurge_checked,
        "top_decile": top_decile,
    }
    return (not problems), problems, stats


SAMPLE = 8  # stock bundles to cross-check against board (stock↔board same-source)


def check_stock_same_source(board: dict, stock_dir: Path) -> tuple[list[str], int]:
    """Stock↔board breakout C9: a sample of per-name bundles must carry the SAME breakout
    block as board.json (both built by board._breakout from one derived_daily)."""
    problems: list[str] = []
    idx = stock_dir / "index.json"
    if not idx.exists():
        return [f"stock/index.json missing under {stock_dir} — run `make export`"], 0
    bteam = {s.get("ticker"): s.get("breakout") for s in board.get("stocks", [])}
    tickers = json.loads(idx.read_text()).get("tickers", [])
    sample = [t for t in tickers if t in bteam][:SAMPLE]
    checked = 0
    for t in sample:
        bp = stock_dir / f"{t}.json"
        if not bp.exists():
            problems.append(f"{t}: stock bundle missing for index ticker")
            continue
        sbk = (json.loads(bp.read_text()) or {}).get("breakout")
        if sbk != bteam[t]:
            problems.append(f"{t}: stock bundle breakout != board breakout (cross-surface drift)")
        else:
            checked += 1
    return problems, checked


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide base→breakout C9 self-check (board.json + stock bundles).")
    ap.add_argument("--board", default=str(ROOT / "web" / "public" / "data" / "board.json"))
    ap.add_argument("--stock-dir", default=str(ROOT / "web" / "public" / "data" / "stock"))
    args = ap.parse_args(argv)

    board = json.loads(Path(args.board).read_text())
    ok, problems, stats = check(board)
    xs_problems, stock_checked = check_stock_same_source(board, Path(args.stock_dir))
    problems += xs_problems

    print(f"[breakout-c9] stocks={stats['stocks']}  breakout_coverage={stats['breakout_coverage']}  "
          f"candidates={stats['candidates']}  vsurge_checked={stats['vsurge_checked']}  "
          f"stock_xcheck={stock_checked}")
    if not problems:
        print("[breakout-c9] GATE_PASS board.json breakout block same-source (candidate gate + "
              "vsurge trace + stock↔board identical)")
        return 0
    print(f"[breakout-c9] GATE_FAIL {len(problems)} problem(s):", file=sys.stderr)
    for p in problems[:20]:
        print(f"    {p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
