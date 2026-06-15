"""M8 C9 cross-surface check: ocean.json positions trace to Stock/Discovery numbers.

AC (PRD §14): "Ocean 点位与 Stock 数字一致 (C9)". Ocean (export/ocean.py) and the Discovery
board (export/board.py) are two independent exporters reading the SAME DuckDB. This script
proves they agree on the latest snapshot, so an Ocean point is traceable to the very numbers
the Discovery card / Stock view show. M8 axes are Ignition × Valuation, so the C9 link is:

  - same as_of date (both export the latest derived_daily snapshot);
  - ign_pct (y): ocean bulk ign_pct[-1] == board.ignition.ign_pct (both = derived_daily.ign_pct);
  - candidate : ocean bulk cand[-1] == board.ignition.candidate (both = the 持续点火 gate,
    ign_pct>=90 AND ign_persist_days>=5 — a point above Ocean's sea level IS a Discovery candidate);
  - ps (x)    : ocean bulk ps[-1] == board.valuation.ps (both = valuation_daily.ps at the latest date).

SCHEMA v3 SPLIT: ocean.json is now a COLUMNAR bulk carrying only the three draw fields
(ps / ign_pct / cand) per stock; the nine hover fields live in per-stock ocean/<TICKER>.json.
So this check ALSO proves the split stayed consistent (C9 across the two files):
  - detail aligns to the bulk window (detail.n == len(ocean.dates));
  - the bulk `cand` flag equals (ign_pct>=90 AND detail.ign_persist_days>=5) at the latest day
    — i.e. the gate the bulk precomputes matches the persistence the detail carries;
  - detail evs[-1] == board.valuation.evs (the detail's valuation traces to the SAME board number).

Run on the SAME DB's two exports (see `make ocean-c9`). Exits non-zero on any mismatch so it
can gate. Names/counts only — no secrets.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGN_TOL = 0.1   # both rounded to 1 decimal off the same derived_daily.ign_pct
PS_TOL = 0.01   # both rounded to 2 decimals off the same valuation_daily.ps
EVS_TOL = 0.01  # both rounded to 2 decimals off the same valuation_daily.evs
SEA_LEVEL = 90      # == export/ocean.py SEA_LEVEL (the candidate gate's ign_pct floor)
IGN_PERSIST_MIN = 5  # == export/ocean.py IGN_PERSIST_MIN (the candidate gate's persistence floor)


def _latest_bulk(stock: dict):
    """Reconstruct the latest (x, y, gate) from the v3 columnar bulk, or None if the last day
    has no renderable position. Mirrors the export's inclusion rule (latest must be non-null)."""
    ps = stock.get("ps") or []
    ig = stock.get("ign_pct") or []
    cand = stock.get("cand") or []
    if not ps or not ig or ps[-1] is None or ig[-1] is None:
        return None
    return {"ps": ps[-1], "ign_pct": ig[-1], "candidate": bool(cand[-1]) if cand else False}


def check(board: dict, ocean: dict, detail_by_ticker: dict | None = None) -> tuple[bool, list[str], dict]:
    """Return (ok, problems, stats). Compares the two exports' latest snapshot, plus (when a
    detail map is given) the v3 bulk↔detail split for the same shared tickers."""
    problems: list[str] = []
    detail_by_ticker = detail_by_ticker or {}

    if board.get("as_of_date") != ocean.get("as_of_date"):
        problems.append(f"as_of mismatch: board={board.get('as_of_date')} ocean={ocean.get('as_of_date')}")

    n_dates = len(ocean.get("dates") or [])
    b_by = {s["ticker"]: s for s in board.get("stocks", [])}
    shared = [s for s in ocean.get("stocks", []) if s["ticker"] in b_by]

    ign_checked = ps_checked = cand_checked = 0
    gate_checked = evs_checked = detail_checked = 0
    for o in shared:
        t = o["ticker"]
        b = b_by[t]
        pt = _latest_bulk(o)
        if pt is None:
            problems.append(f"{t}: ocean latest pt is null")
            continue
        big = b.get("ignition") or {}
        # ign_pct: ocean.ign_pct vs board.ignition.ign_pct (both = derived_daily.ign_pct).
        b_ign = big.get("ign_pct")
        if b_ign is not None and pt.get("ign_pct") is not None:
            ign_checked += 1
            if abs(pt["ign_pct"] - b_ign) > IGN_TOL:
                problems.append(f"{t}: ign_pct ocean={pt['ign_pct']} vs board={b_ign}")
        # candidate: the 持续点火 gate must agree (sea-level population == Discovery candidates).
        if "candidate" in big:
            cand_checked += 1
            if bool(pt["candidate"]) != bool(big["candidate"]):
                problems.append(f"{t}: candidate ocean={pt['candidate']} vs board={big['candidate']}")
        # ps: ocean.ps vs board.valuation.ps (both = valuation_daily.ps at latest).
        b_ps = (b.get("valuation") or {}).get("ps")
        if b_ps is not None and pt.get("ps") is not None:
            ps_checked += 1
            if abs(pt["ps"] - b_ps) > PS_TOL:
                problems.append(f"{t}: ps ocean={pt['ps']} vs board={b_ps}")

        # v3 split: the per-stock detail file must align to the bulk window and stay consistent.
        det = detail_by_ticker.get(t)
        if det is not None:
            detail_checked += 1
            if n_dates and det.get("n") != n_dates:
                problems.append(f"{t}: detail n={det.get('n')} != ocean dates {n_dates}")
            persist = (det.get("ign_persist_days") or [None])[-1]
            # the bulk's precomputed `cand` must equal the gate recomputed from the detail's
            # persistence + the bulk's ign_pct (proves the split didn't desync the gate).
            if persist is not None and pt.get("ign_pct") is not None:
                gate_checked += 1
                gate = pt["ign_pct"] >= SEA_LEVEL and persist >= IGN_PERSIST_MIN
                if bool(gate) != bool(pt["candidate"]):
                    problems.append(
                        f"{t}: detail gate mismatch cand={pt['candidate']} but "
                        f"ign_pct={pt['ign_pct']}/persist={persist}"
                    )
            # detail evs traces to the SAME board valuation number.
            d_evs = (det.get("evs") or [None])[-1]
            b_evs = (b.get("valuation") or {}).get("evs")
            if d_evs is not None and b_evs is not None:
                evs_checked += 1
                if abs(d_evs - b_evs) > EVS_TOL:
                    problems.append(f"{t}: evs detail={d_evs} vs board={b_evs}")

    stats = {
        "board_stocks": len(b_by),
        "ocean_stocks": len(ocean.get("stocks", [])),
        "shared": len(shared),
        "ign_checked": ign_checked,
        "cand_checked": cand_checked,
        "ps_checked": ps_checked,
        "detail_checked": detail_checked,
        "gate_checked": gate_checked,
        "evs_checked": evs_checked,
    }
    return (not problems), problems, stats


def _load_detail(detail_dir: Path, tickers) -> dict:
    """Load ocean/<TICKER>.json for the given tickers (skip missing — the check counts what it
    actually read). Returns {ticker -> detail dict}."""
    out: dict[str, dict] = {}
    if not detail_dir.is_dir():
        return out
    for t in tickers:
        p = detail_dir / f"{t}.json"
        if p.is_file():
            out[t] = json.loads(p.read_text())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M8 C9 cross-surface check (ocean vs board, v3 bulk + detail).")
    ap.add_argument("--board", default=str(ROOT / "web" / "public" / "data" / "board.json"))
    ap.add_argument("--ocean", default=str(ROOT / "web" / "public" / "data" / "ocean.json"))
    ap.add_argument("--ocean-detail-dir", default=str(ROOT / "web" / "public" / "data" / "ocean"),
                    help="per-stock hover detail dir (ocean/<TICKER>.json, schema v3)")
    args = ap.parse_args(argv)

    board = json.loads(Path(args.board).read_text())
    ocean = json.loads(Path(args.ocean).read_text())
    b_tickers = {s["ticker"] for s in board.get("stocks", [])}
    shared_tickers = [s["ticker"] for s in ocean.get("stocks", []) if s["ticker"] in b_tickers]
    detail_by_ticker = _load_detail(Path(args.ocean_detail_dir), shared_tickers)
    ok, problems, stats = check(board, ocean, detail_by_ticker)

    print(f"[ocean-c9] as_of board={board.get('as_of_date')} ocean={ocean.get('as_of_date')}  "
          f"shared={stats['shared']}  ign_checked={stats['ign_checked']}  "
          f"cand_checked={stats['cand_checked']}  ps_checked={stats['ps_checked']}  "
          f"detail_checked={stats['detail_checked']}  gate_checked={stats['gate_checked']}  "
          f"evs_checked={stats['evs_checked']}")
    if ok:
        print("[ocean-c9] GATE_PASS C9 ocean↔board consistent (ign_pct=ign_pct, candidate=持续点火 gate, "
              "ps=valuation_daily.ps) + v3 bulk↔detail split aligned (gate==ign_pct&persist, evs traces)")
        return 0
    print(f"[ocean-c9] GATE_FAIL {len(problems)} mismatch(es):", file=sys.stderr)
    for p in problems[:20]:
        print(f"    {p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
