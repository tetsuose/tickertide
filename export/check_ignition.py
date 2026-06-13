"""M7.2 ignition self-check: board.json ignition block traces to the engine (C9).

AC-M7 (PRD §14): ignition shares the per-stock data with composite (C9), Discovery
sorts by "持续点火" (sustained ignition, NOT composite), and the sustained-ignition
board is non-empty + traceable. board.py (export/board.py) ships each stock's
ignition score / ign_pct / persistence / 5 raw components verbatim from
derived_daily, plus a `candidate` flag and human-readable 点火证据. This script
re-reads the exported board.json and proves the ignition block is internally
consistent and same-source, so a re-scoring / drift / gate bug fails loudly here
instead of silently in Discovery:

  - coverage: every stock carries an ignition block with the 5 components;
  - ranges: ignition∈[0,100], ign_pct∈[0,100], persist>=0 (PRD §10.8.2);
  - candidate gate: `candidate` == (ign_pct>=90 AND persist>=ignition_persist_min)
    EXACTLY — the "持续点火" definition, recomputed from the shipped numbers;
  - evidence trace: evidence.vol_mult == component vsurge (ig_vsurge verbatim — the
    same-source identity guard board.py asserts at build, re-checked off the file);
  - non-empty: at least one sustained-ignition candidate (else Discovery's board
    would be empty — flagged, not fatal, since a quiet tape can have zero);
  - the top-level ignition_recon_max_drift the exporter wrote is ~0.

Runs on the exported board.json (see `make ignition-c9`). Exits non-zero on any
inconsistency so it can gate. Names/counts only — no secrets.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VSURGE_TOL = 1e-3   # evidence.vol_mult rounded to 3 decimals off the same ig_vsurge
DRIFT_TOL = 1e-6    # exporter's own ignition_recon_max_drift must be ~0
TOP_DECILE = 90     # PRD §10.8.2 (must match board.IGN_TOP_DECILE)


def check(board: dict) -> tuple[bool, list[str], dict]:
    """Return (ok, problems, stats). Validates board.json's ignition is same-source."""
    problems: list[str] = []
    stocks = board.get("stocks", [])
    persist_min = board.get("ignition_persist_min")
    if persist_min is None:
        problems.append("board missing ignition_persist_min (candidate gate undefined)")
        persist_min = 5

    n_ign = n_cand = vsurge_checked = 0
    for s in stocks:
        t = s.get("ticker")
        ig = s.get("ignition")
        if ig is None:
            problems.append(f"{t}: no ignition block (C9 coverage gap)")
            continue

        score, pct, persist = ig.get("ignition"), ig.get("ign_pct"), ig.get("ign_persist_days")
        comps = ig.get("components") or {}
        if score is not None:
            n_ign += 1
            if not (-1e-9 <= score <= 100 + 1e-9):
                problems.append(f"{t}: ignition={score} out of [0,100]")
        if pct is not None and not (-1e-9 <= pct <= 100 + 1e-9):
            problems.append(f"{t}: ign_pct={pct} out of [0,100]")
        if persist is not None and persist < 0:
            problems.append(f"{t}: ign_persist_days={persist} < 0")
        if set(comps) != {"accel", "expand", "vsurge", "breakout", "rsturn"}:
            problems.append(f"{t}: ignition.components keys={sorted(comps)} != 5 expected")

        # candidate gate must EXACTLY equal the "持续点火" definition (PRD §10.8.2).
        want = (pct is not None and persist is not None
                and pct >= TOP_DECILE and persist >= persist_min)
        if bool(ig.get("candidate")) != want:
            problems.append(
                f"{t}: candidate={ig.get('candidate')} but ign_pct={pct} persist={persist} "
                f"(gate: pct>={TOP_DECILE} and persist>={persist_min} => {want})")
        if ig.get("candidate"):
            n_cand += 1

        # evidence.vol_mult must trace to the vsurge component (ig_vsurge verbatim).
        ev = ig.get("evidence") or {}
        ev_v, comp_v = ev.get("vol_mult"), comps.get("vsurge")
        if ev_v is not None and comp_v is not None:
            vsurge_checked += 1
            if abs(ev_v - comp_v) > VSURGE_TOL:
                problems.append(f"{t}: evidence.vol_mult={ev_v} != component vsurge={comp_v}")

    drift = board.get("ignition_recon_max_drift")
    if drift is not None and abs(drift) > DRIFT_TOL:
        problems.append(f"ignition_recon_max_drift={drift} > {DRIFT_TOL} (exporter saw drift)")

    if n_cand == 0:
        problems.append("zero sustained-ignition candidates — Discovery board would be empty")

    stats = {
        "stocks": len(stocks),
        "ignition_coverage": n_ign,
        "candidates": n_cand,
        "vsurge_checked": vsurge_checked,
        "persist_min": persist_min,
    }
    return (not problems), problems, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M7.2 ignition C9 self-check (board.json).")
    ap.add_argument("--board", default=str(ROOT / "web" / "public" / "data" / "board.json"))
    args = ap.parse_args(argv)

    board = json.loads(Path(args.board).read_text())
    ok, problems, stats = check(board)

    print(f"[ignition-c9] as_of={board.get('as_of_date')}  stocks={stats['stocks']}  "
          f"coverage={stats['ignition_coverage']}  candidates={stats['candidates']}"
          f"(persist>={stats['persist_min']})  vsurge_checked={stats['vsurge_checked']}")
    if ok:
        print("[ignition-c9] GATE_PASS ignition same-source (candidate gate + vsurge trace + ranges)")
        return 0
    print(f"[ignition-c9] GATE_FAIL {len(problems)} problem(s):", file=sys.stderr)
    for p in problems[:20]:
        print(f"    {p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
