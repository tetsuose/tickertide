"""M2.5 C9 cross-surface check: ocean.json positions trace to Stock/Discovery numbers.

AC-M2 (PRD §14): "Ocean 点位与 Stock 数字一致 (C9)". Ocean (export/ocean.py) and the
Discovery board (export/board.py) are two independent exporters reading the SAME
DuckDB. This script proves they agree on the latest snapshot, so an Ocean point is
traceable to the very numbers the Discovery card / Stock view show:

  - same as_of date (both export the latest derived_daily snapshot);
  - rs: ocean.pts[-1].rs == board.components.rs × 100  (both = derived_daily.rs_pct;
    board ships the component c_rs = rs_pct/100);
  - ps: ocean.pts[-1].ps == board.valuation.ps         (both = valuation_daily.ps at
    the latest date — the P/S the hover tip and the card show).

Run on the SAME DB's two exports (see `make ocean-c9`). Exits non-zero on any
mismatch so it can gate. Names/counts only — no secrets.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RS_TOL = 0.1   # both rounded to 1 decimal off the same rs_pct
PS_TOL = 0.01  # both rounded to 2 decimals off the same valuation_daily.ps


def _latest_rs(stock: dict):
    pts = stock.get("pts") or []
    return pts[-1] if pts and pts[-1] is not None else None


def check(board: dict, ocean: dict) -> tuple[bool, list[str], dict]:
    """Return (ok, problems, stats). Compares the two exports' latest snapshot."""
    problems: list[str] = []

    if board.get("as_of_date") != ocean.get("as_of_date"):
        problems.append(f"as_of mismatch: board={board.get('as_of_date')} ocean={ocean.get('as_of_date')}")

    b_by = {s["ticker"]: s for s in board.get("stocks", [])}
    shared = [s for s in ocean.get("stocks", []) if s["ticker"] in b_by]

    rs_checked = ps_checked = 0
    for o in shared:
        t = o["ticker"]
        b = b_by[t]
        pt = _latest_rs(o)
        if pt is None:
            problems.append(f"{t}: ocean latest pt is null")
            continue
        # rs: ocean.rs (rs_pct) vs board.components.rs*100 (c_rs*100 = rs_pct).
        b_rs = (b.get("components") or {}).get("rs")
        if b_rs is not None and pt.get("rs") is not None:
            rs_checked += 1
            if abs(pt["rs"] - b_rs * 100) > RS_TOL:
                problems.append(f"{t}: rs ocean={pt['rs']} vs board c_rs*100={b_rs * 100:.1f}")
        # ps: ocean.ps vs board.valuation.ps (both = valuation_daily.ps at latest).
        b_ps = (b.get("valuation") or {}).get("ps")
        if b_ps is not None and pt.get("ps") is not None:
            ps_checked += 1
            if abs(pt["ps"] - b_ps) > PS_TOL:
                problems.append(f"{t}: ps ocean={pt['ps']} vs board={b_ps}")

    stats = {
        "board_stocks": len(b_by),
        "ocean_stocks": len(ocean.get("stocks", [])),
        "shared": len(shared),
        "rs_checked": rs_checked,
        "ps_checked": ps_checked,
    }
    return (not problems), problems, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M2.5 C9 cross-surface check (ocean vs board).")
    ap.add_argument("--board", default=str(ROOT / "web" / "public" / "data" / "board.json"))
    ap.add_argument("--ocean", default=str(ROOT / "web" / "public" / "data" / "ocean.json"))
    args = ap.parse_args(argv)

    board = json.loads(Path(args.board).read_text())
    ocean = json.loads(Path(args.ocean).read_text())
    ok, problems, stats = check(board, ocean)

    print(f"[ocean-c9] as_of board={board.get('as_of_date')} ocean={ocean.get('as_of_date')}  "
          f"shared={stats['shared']}  rs_checked={stats['rs_checked']}  ps_checked={stats['ps_checked']}")
    if ok:
        print(f"[ocean-c9] GATE_PASS C9 ocean↔board consistent (rs=rs_pct, ps=valuation_daily.ps)")
        return 0
    print(f"[ocean-c9] GATE_FAIL {len(problems)} mismatch(es):", file=sys.stderr)
    for p in problems[:20]:
        print(f"    {p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
