"""steady-riser self-check: board.json riser block traces to the screen (C9).

AC-M7 (PRD §14, 2026-07-02 spine pivot II): the core screen is steady-riser (base→breakout
retired §10.9). board.py (export/board.py) ships each stock's riser metrics (net5/net10/net20,
up10, ddw10, ker10), the cross-sectional net10_pct, the STORED candidate flag and streak_days
verbatim from derived_daily. This script re-reads the exported board.json and proves the riser
block is internally consistent and same-source, so a re-scoring / drift / gate bug fails
loudly here instead of silently in the Risers view:

  - coverage: every stock carries a riser block with the full metric set;
  - ranges: net10_pct∈[0,100], up10∈[0,1], ker10∈[0,1], ddw10<=0 (PRD §10.8);
  - candidate ⇒ gate: every candidate satisfies up10>=0.6 AND net10>0 (the gate evidence is
    visible in the shipped numbers). The flag itself is the STORED single truth — this check
    deliberately does NOT re-derive the top-N (that would be a second implementation of the
    gate, the exact drift class #92-#94 removed); it proves the flag is never inconsistent
    with its own shipped evidence;
  - top-N: # candidates <= riser_top_n (the board can never carry more than the list size);
  - streak: candidate==False ⇒ streak_days==0, candidate==True ⇒ streak_days>=1;
  - non-empty: at least one candidate (else the Risers board would be empty — flagged as a
    problem so a broken gate fails loudly; a genuinely empty gated set has never occurred);
  - stock↔board same-source: a sample of per-name Stock bundles (export/stock_bundle.py) carry
    the SAME riser block as board.json for that ticker — both assembled by board._riser from
    the same derived_daily, so the Stock 诊断 and the Risers card never disagree (C9).

Runs on the exported board.json + stock bundles (see `make riser-c9`). Exits non-zero on
any inconsistency so it can gate. Names/counts only — no secrets.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UP_MIN = 0.6   # PRD §10.8.2 gate (must match compute/riser.UP_MIN)

_RISER_KEYS = {"net5", "net10", "net20", "up10", "ddw10", "ker10",
               "net10_pct", "candidate", "streak_days"}


def check(board: dict) -> tuple[bool, list[str], dict]:
    """Return (ok, problems, stats). Validates board.json's riser block is same-source."""
    problems: list[str] = []
    stocks = board.get("stocks", [])
    top_n = board.get("riser_top_n")
    if top_n is None:
        problems.append("board missing riser_top_n (list size undefined)")

    n_ris = n_cand = 0
    for s in stocks:
        t = s.get("ticker")
        rk = s.get("riser")
        if rk is None:
            problems.append(f"{t}: no riser block (C9 coverage gap)")
            continue
        if set(rk) != _RISER_KEYS:
            problems.append(f"{t}: riser keys={sorted(rk)} != expected")
            continue

        pct, net10, up10 = rk.get("net10_pct"), rk.get("net10"), rk.get("up10")
        ddw10, ker10 = rk.get("ddw10"), rk.get("ker10")
        if net10 is not None:
            n_ris += 1
        if pct is not None and not (-1e-9 <= pct <= 100 + 1e-9):
            problems.append(f"{t}: net10_pct={pct} out of [0,100]")
        if up10 is not None and not (-1e-9 <= up10 <= 1 + 1e-9):
            problems.append(f"{t}: up10={up10} out of [0,1]")
        if ker10 is not None and not (-1e-9 <= ker10 <= 1 + 1e-9):
            problems.append(f"{t}: ker10={ker10} out of [0,1]")
        if ddw10 is not None and ddw10 > 1e-9:
            problems.append(f"{t}: ddw10={ddw10} > 0 (a drawdown must be <=0)")

        # candidate ⇒ its own shipped gate evidence (flag stays the stored single truth).
        streak = rk.get("streak_days")
        if rk.get("candidate"):
            n_cand += 1
            if up10 is None or net10 is None or up10 < UP_MIN - 1e-9 or net10 <= 0:
                problems.append(
                    f"{t}: candidate but gate evidence fails (up10={up10}, net10={net10})")
            if not streak or streak < 1:
                problems.append(f"{t}: candidate with streak_days={streak} (must be >=1)")
        elif streak not in (0, None):
            problems.append(f"{t}: non-candidate with streak_days={streak} (must be 0)")

    if top_n is not None and n_cand > top_n:
        problems.append(f"candidates={n_cand} > riser_top_n={top_n} (list overflow)")
    if n_cand == 0:
        problems.append("zero riser candidates — the Risers board would be empty")

    stats = {
        "stocks": len(stocks),
        "riser_coverage": n_ris,
        "candidates": n_cand,
        "top_n": top_n,
    }
    return (not problems), problems, stats


SAMPLE = 8  # stock bundles to cross-check against board (stock↔board same-source)


def check_stock_same_source(board: dict, stock_dir: Path) -> tuple[list[str], int]:
    """Stock↔board riser C9: a sample of per-name bundles must carry the SAME riser block
    as board.json (both built by board._riser from one derived_daily)."""
    problems: list[str] = []
    idx = stock_dir / "index.json"
    if not idx.exists():
        return [f"stock/index.json missing under {stock_dir} — run `make export`"], 0
    bteam = {s.get("ticker"): s.get("riser") for s in board.get("stocks", [])}
    tickers = json.loads(idx.read_text()).get("tickers", [])
    sample = [t for t in tickers if t in bteam][:SAMPLE]
    checked = 0
    for t in sample:
        bp = stock_dir / f"{t}.json"
        if not bp.exists():
            problems.append(f"{t}: stock bundle missing for index ticker")
            continue
        srk = (json.loads(bp.read_text()) or {}).get("riser")
        if srk != bteam[t]:
            problems.append(f"{t}: stock bundle riser != board riser (cross-surface drift)")
        else:
            checked += 1
    return problems, checked


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide steady-riser C9 self-check (board.json + stock bundles).")
    ap.add_argument("--board", default=str(ROOT / "web" / "public" / "data" / "board.json"))
    ap.add_argument("--stock-dir", default=str(ROOT / "web" / "public" / "data" / "stock"))
    args = ap.parse_args(argv)

    board = json.loads(Path(args.board).read_text())
    ok, problems, stats = check(board)
    xs_problems, stock_checked = check_stock_same_source(board, Path(args.stock_dir))
    problems += xs_problems

    print(f"[riser-c9] stocks={stats['stocks']}  riser_coverage={stats['riser_coverage']}  "
          f"candidates={stats['candidates']}(top-{stats['top_n']})  stock_xcheck={stock_checked}")
    if not problems:
        print("[riser-c9] GATE_PASS board.json riser block same-source (stored candidate flag "
              "consistent with its gate evidence + stock↔board identical)")
        return 0
    print(f"[riser-c9] GATE_FAIL {len(problems)} problem(s):", file=sys.stderr)
    for p in problems[:20]:
        print(f"    {p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
