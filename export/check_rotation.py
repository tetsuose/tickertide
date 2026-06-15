"""M3.5 C9 cross-surface check: rotation.json league traces to board.json members.

AC-M3/AC-M4 (PRD §14): the Rotation league's member aggregates must agree with the
Discovery board — both read the SAME DuckDB (derived_daily / valuation_daily). Rotation
(export/rotation.py) aggregates per bucket (sector via universe.sector; theme via
theme_membership point-in-time); the board (export/board.py) is per stock. This proves a
bucket's league row is traceable to the very member cards Discovery shows (C9 — "聚合量取自
成员"). The grouping follows the rotation file's bucket_type, so the same check gates both
the sector (rotation.json) and theme (rotation.theme.json) exports:

  - same as_of date (both export the latest snapshot);
  - members[] ⊆ board tickers (the client filters board.json by scope=sector for cards);
  - member_count == # board stocks in that sector;
  - igniting == # board members above the sea level (ignition.ign_pct >= 90);
  - candidates == # board members flagged ignition.candidate (the 持续点火 gate).

M8: the league aggregates the discovery engine (ignition), not the composite median that
is no longer user-visible — so this proves the league's ignition counts trace to the very
candidate flags the Discovery cards show (C9). Run on the SAME DB's two exports (see
`make rotation-c9`). Exits non-zero on any mismatch so it can gate. Names/counts only — no
secrets. NOTE: this holds when board and rotation see the same member set; board.py's
--min-bars filter (default 60) can prune a thin-history stock the rotation aggregate still
counts — align them before relying on this against real (vs fixture) data.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEA_LEVEL = 90  # ign_pct >= this = lit (== export/board.py IGN_TOP_DECILE / ocean.py SEA_LEVEL)


def check(board: dict, rotation: dict) -> tuple[bool, list[str], dict]:
    """Return (ok, problems, stats). Compares the two exports' latest snapshot."""
    problems: list[str] = []
    if board.get("as_of_date") != rotation.get("as_of_date"):
        problems.append(f"as_of mismatch: board={board.get('as_of_date')} rotation={rotation.get('as_of_date')}")

    board_tickers = {s["ticker"] for s in board.get("stocks", [])}
    # Group board stocks into the rotation file's buckets. sector: one bucket per stock
    # (universe.sector); theme: a stock joins EACH of its point-in-time theme chips
    # (many-to-many — NVDA-like ticker counts in AI and SEMI), so the theme league's
    # PIT member set must match the board's PIT theme chips (closes the theme C9 loop).
    btype = rotation.get("bucket_type", "sector")
    by_bucket: dict[str, list] = defaultdict(list)
    for s in board.get("stocks", []):
        if btype == "theme":
            for ch in s.get("themes", []):
                if ch.get("theme"):
                    by_bucket[ch["theme"]].append(s)
        elif s.get("sector"):
            by_bucket[s["sector"]].append(s)

    def _ign_pct(s):
        return (s.get("ignition") or {}).get("ign_pct")

    mem_checked = ign_checked = 0
    for b in rotation.get("buckets", []):
        bk = b["bucket"]
        members = by_bucket.get(bk, [])
        missing = [t for t in b.get("members", []) if t not in board_tickers]
        if missing:
            problems.append(f"{bk}: {len(missing)} member ticker(s) not in board.json (e.g. {missing[:3]})")
        if b.get("member_count") is not None:
            mem_checked += 1
            if b["member_count"] != len(members):
                problems.append(f"{bk}: member_count rotation={b['member_count']} vs board={len(members)}")
        # igniting / candidates trace to the board's own ignition block (the SAME gate).
        if b.get("igniting") is not None:
            ign_checked += 1
            lit = sum(1 for s in members if _ign_pct(s) is not None and _ign_pct(s) >= SEA_LEVEL)
            if b["igniting"] != lit:
                problems.append(f"{bk}: igniting rotation={b['igniting']} vs board={lit}")
        if b.get("candidates") is not None:
            cands = sum(1 for s in members if (s.get("ignition") or {}).get("candidate"))
            if b["candidates"] != cands:
                problems.append(f"{bk}: candidates rotation={b['candidates']} vs board={cands}")

    stats = {
        "board_stocks": len(board_tickers),
        "rotation_buckets": len(rotation.get("buckets", [])),
        "member_count_checked": mem_checked,
        "ignition_checked": ign_checked,
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
          f"ignition_checked={stats['ignition_checked']}")
    if ok:
        print("[rotation-c9] GATE_PASS C9 rotation league↔board members consistent "
              "(member_count, igniting, candidates, members⊆board)")
        return 0
    print(f"[rotation-c9] GATE_FAIL {len(problems)} mismatch(es):", file=sys.stderr)
    for p in problems[:20]:
        print(f"    {p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
