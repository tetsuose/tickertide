"""M3.5 C9 cross-surface check: rotation.json league traces to board.json members.

AC-M3 (PRD §14): the Rotation league's member aggregates must agree with the Discovery
board — both read the SAME DuckDB (derived_daily / valuation_daily). Rotation
(export/rotation.py) aggregates per sector; the board (export/board.py) is per stock.
This proves a sector's league row is traceable to the very member cards Discovery shows
(C9 — "聚合量取自 universe 成员", ROADMAP M3 risk table):

  - same as_of date (both export the latest snapshot);
  - members[] ⊆ board tickers (the client filters board.json by scope=sector for cards);
  - member_count == # board stocks in that sector;
  - composite_median == median(board stocks' composite in that sector).

Run on the SAME DB's two exports (see `make rotation-c9`). Exits non-zero on any
mismatch so it can gate. Names/counts only — no secrets. NOTE: this holds when board and
rotation see the same member set; board.py's --min-bars filter (default 60) can prune a
thin-history stock the rotation aggregate still counts — align them before relying on
this against real (vs fixture) data.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MED_TOL = 0.01  # both rounded off the same derived_daily.composite


def check(board: dict, rotation: dict) -> tuple[bool, list[str], dict]:
    """Return (ok, problems, stats). Compares the two exports' latest snapshot."""
    problems: list[str] = []
    if board.get("as_of_date") != rotation.get("as_of_date"):
        problems.append(f"as_of mismatch: board={board.get('as_of_date')} rotation={rotation.get('as_of_date')}")

    board_tickers = {s["ticker"] for s in board.get("stocks", [])}
    by_sec: dict[str, list] = defaultdict(list)
    for s in board.get("stocks", []):
        if s.get("sector"):
            by_sec[s["sector"]].append(s)

    mem_checked = med_checked = 0
    for b in rotation.get("buckets", []):
        sec = b["bucket"]
        members = by_sec.get(sec, [])
        missing = [t for t in b.get("members", []) if t not in board_tickers]
        if missing:
            problems.append(f"{sec}: {len(missing)} member ticker(s) not in board.json (e.g. {missing[:3]})")
        if b.get("member_count") is not None:
            mem_checked += 1
            if b["member_count"] != len(members):
                problems.append(f"{sec}: member_count rotation={b['member_count']} vs board={len(members)}")
        comps = [s["composite"] for s in members if s.get("composite") is not None]
        if comps and b.get("composite_median") is not None:
            med_checked += 1
            med = statistics.median(comps)
            if abs(b["composite_median"] - med) > MED_TOL:
                problems.append(f"{sec}: composite_median rotation={b['composite_median']} vs board median={med:.2f}")

    stats = {
        "board_stocks": len(board_tickers),
        "rotation_buckets": len(rotation.get("buckets", [])),
        "member_count_checked": mem_checked,
        "composite_median_checked": med_checked,
    }
    return (not problems), problems, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M3.5 C9 cross-surface check (rotation vs board).")
    ap.add_argument("--board", default=str(ROOT / "web" / "public" / "data" / "board.json"))
    ap.add_argument("--rotation", default=str(ROOT / "web" / "public" / "data" / "rotation.json"))
    args = ap.parse_args(argv)

    board = json.loads(Path(args.board).read_text())
    rotation = json.loads(Path(args.rotation).read_text())
    ok, problems, stats = check(board, rotation)

    print(f"[rotation-c9] as_of board={board.get('as_of_date')} rotation={rotation.get('as_of_date')}  "
          f"buckets={stats['rotation_buckets']}  member_count_checked={stats['member_count_checked']}  "
          f"composite_median_checked={stats['composite_median_checked']}")
    if ok:
        print("[rotation-c9] GATE_PASS C9 rotation league↔board members consistent "
              "(member_count, composite_median, members⊆board)")
        return 0
    print(f"[rotation-c9] GATE_FAIL {len(problems)} mismatch(es):", file=sys.stderr)
    for p in problems[:20]:
        print(f"    {p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
