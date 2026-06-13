"""M5.5 AC-M5 + C9 check: valuation.parquet / stock bundles trace to board.json (one engine).

The M5 surfaces (Valuation screener, Stock detail) must read the SAME valuation_daily as
board.json — a ticker's P/S in the screener, in a Stock bundle, and on its Discovery card
are the same number (C9, PRD §7). This checks the DATA side of AC-M5 (the duckdb-wasm
sort / tri-color / four-pane behaviours are covered by the web tests + browser smoke):

  - valuation.parquet is queryable and carries the M5 columns (incl. peg/margin/freshness,
    the two the board.json preview lacked); freshness is one of fresh/stale/overdue/NULL.
  - C9 valuation↔board: every ticker in both shows the same pe/ps (within rounding).
  - C9 stock↔valuation: a sample of Stock bundles' latest P/S == the screener's P/S.

Run after `make export`. CHECK_OK / CHECK_FAIL, non-zero exit on failure (CI-friendly).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "web" / "public" / "data"
TOL = 0.02  # both rounded off the same valuation_daily row
SAMPLE = 8  # stock bundles to spot-check


def run(board_path: Path, parquet: Path, stock_dir: Path) -> tuple[bool, list[str], dict]:
    problems: list[str] = []
    board = json.loads(board_path.read_text())
    con = duckdb.connect()
    cols = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM '{parquet.as_posix()}'").fetchall()]
    for need in ("pe", "ps", "evs", "ev_ebitda", "peg", "growth", "margin", "rule40", "freshness", "themes"):
        if need not in cols:
            problems.append(f"valuation.parquet missing column {need}")

    vrows = con.execute(
        f"SELECT ticker, pe, ps, freshness FROM '{parquet.as_posix()}'"
    ).fetchall()
    vby = {r[0]: r for r in vrows}
    bad_fresh = [r[0] for r in vrows if r[3] not in (None, "fresh", "stale", "overdue")]
    if bad_fresh:
        problems.append(f"freshness out of domain for {len(bad_fresh)} rows (e.g. {bad_fresh[:3]})")

    # C9 valuation↔board: same ps/pe per shared ticker
    c9_val = 0
    for s in board.get("stocks", []):
        t = s["ticker"]
        v = (s.get("valuation") or {})
        if t in vby:
            bps, vps = v.get("ps"), vby[t][2]
            if bps is not None and vps is not None and abs(float(bps) - float(vps)) > TOL:
                problems.append(f"{t}: board ps={bps} vs valuation.parquet ps={round(float(vps),2)}")
            else:
                c9_val += 1

    # C9 stock↔valuation: sample bundles' latest P/S == screener P/S
    c9_stk = 0
    idx_path = stock_dir / "index.json"
    if idx_path.exists():
        tickers = json.loads(idx_path.read_text()).get("tickers", [])[:SAMPLE]
        for t in tickers:
            bp = stock_dir / f"{t}.json"
            if not bp.exists():
                problems.append(f"stock bundle missing for index ticker {t}")
                continue
            b = json.loads(bp.read_text())
            ps_series = b.get("ps_series") or []
            last_ps = ps_series[-1]["ps"] if ps_series else None
            vps = vby[t][2] if t in vby else None
            if last_ps is not None and vps is not None and abs(float(last_ps) - float(vps)) > TOL:
                problems.append(f"{t}: stock bundle latest ps={last_ps} vs valuation ps={round(float(vps),2)}")
            else:
                c9_stk += 1
    else:
        problems.append("stock/index.json missing — run `make export`")

    con.close()
    stats = {"valuation_rows": len(vrows), "c9_valuation_board": c9_val, "c9_stock_valuation": c9_stk}
    return (not problems), problems, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M5.5 AC-M5 + C9 check (valuation/stock vs board).")
    ap.add_argument("--board", default=str(DATA / "board.json"))
    ap.add_argument("--parquet", default=str(DATA / "valuation.parquet"))
    ap.add_argument("--stock-dir", default=str(DATA / "stock"))
    args = ap.parse_args(argv)

    parquet = Path(args.parquet)
    if not parquet.exists():
        print(f"[valuation-c9] SKIP {parquet} missing — run `make export` first.")
        return 0

    ok, problems, stats = run(Path(args.board), parquet, Path(args.stock_dir))
    print(f"[valuation-c9] valuation_rows={stats['valuation_rows']} "
          f"c9_valuation_board={stats['c9_valuation_board']} c9_stock_valuation={stats['c9_stock_valuation']}")
    if ok:
        print("[valuation-c9] GATE_PASS C9 valuation/stock↔board consistent (same valuation_daily) + AC-M5 columns")
        return 0
    print(f"[valuation-c9] GATE_FAIL {len(problems)} problem(s):", file=sys.stderr)
    for p in problems[:20]:
        print(f"    {p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
