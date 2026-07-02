"""AC-M7 aggregate acceptance check (PRD §14, §10.8) — one-command, traceable.

After the 2026-07-02 spine pivot II the core screen is steady-riser (base→breakout retired
§10.9). The individual invariants are enforced piecemeal (compute/check.py asserts the
derived_daily columns; export/check_riser.py proves the board riser block is same-source as
the screen + does the stock↔board cross-check; the web vitest suite asserts the Risers/Stock
render order). This script is the SINGLE labelled gate that maps 1:1 onto the five AC-M7
clauses (PRD §14, rewritten for steady-riser) so the milestone is replayable in one command.

It reads the EXPORTED artifacts (board.json + per-name stock bundles — the same files the
browser consumes) and asserts each AC-M7 clause explicitly:

  AC-M7.1  derived_daily ships steady-riser: every board stock carries the full riser block
           (net5/net10/net20/up10/ddw10/ker10/net10_pct/candidate/streak_days), in range.
  AC-M7.2  Risers sorts by gate + net10, NOT composite: the board's recall-first order
           (candidate → net10 desc, the key web/src/views/Risers.tsx uses) is asserted to
           DIFFER from a pure composite ranking on this snapshot (PRD §9.3, §10.8).
  AC-M7.3  evidence-first: every stock's riser block carries the chart-verifiable evidence
           columns the card shows — net5/net10/net20, up-day ratio, in-window drawdown,
           path efficiency, streak (PRD §9.3, §10.8.1).
  AC-M7.4  riser C9 same-source: the riser block rides every per-stock row, and a sample of
           per-name Stock bundles carry byte-identical riser blocks to board.json (cross-
           surface C9 — both assembled by board._riser from one derived_daily).
  AC-M7.5  the candidate board is non-empty AND consistent: ≥1 candidate, count <= top-N,
           and each candidate's STORED flag agrees with its own shipped gate evidence
           (up10>=0.6 AND net10>0) — the flag is the single truth, never re-derived
           (PRD §10.8.2, the #92-#94 boundary lesson).

This reuses export/check_riser.check (the same-source + gate-evidence + stock↔board guard)
rather than re-deriving it — DRY, one source of the C9 logic. It only ADDS the clauses that
guard had no single labelled home for: the composite-vs-riser order divergence (AC-M7.2)
and the per-clause framing.

Runs on the exported board.json + stock bundles (see `make ac-m7`). Exits non-zero on any
failure so it gates. Names/counts only — no secrets.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from export import check_riser  # noqa: E402  (reuse the same-source C9 guard)

RISER_KEYS = {  # PRD §10.8 — the full chart-verifiable riser block board.py ships
    "net5", "net10", "net20", "up10", "ddw10", "ker10", "net10_pct", "candidate", "streak_days",
}


def _riser_key(s: dict):
    """The Risers sort key — candidate first, then net10 desc (recall-first).
    Mirrors web/src/views/Risers.tsx (PRD §9.3, §10.8.2)."""
    rk = s.get("riser") or {}
    return (
        1 if rk.get("candidate") else 0,
        rk.get("net10") if rk.get("net10") is not None else -1e9,
    )


def ac_m7_checks(board: dict, stock_dir: Path) -> list[tuple[str, bool, str]]:
    """Return [(clause, ok, detail)] for the five AC-M7 clauses (PRD §14, steady-riser)."""
    out: list[tuple[str, bool, str]] = []
    stocks = board.get("stocks", [])

    # Lean on the existing same-source guard for coverage/ranges/gate-evidence/streak.
    ok_core, problems, stats = check_riser.check(board)
    cov = stats["riser_coverage"]
    n = len(stocks)

    # AC-M7.1 — derived_daily ships steady-riser (full block, in range).
    keys_ok = all(set(s.get("riser") or {}) == RISER_KEYS for s in stocks)
    range_problems = [p for p in problems if "out of" in p or "> 0 (a drawdown" in p or "riser keys" in p]
    out.append((
        "AC-M7.1 derived_daily ships steady-riser (full block + ranges)",
        cov == n and n > 0 and keys_ok and not range_problems,
        f"coverage={cov}/{n}, block+range ok",
    ))

    # AC-M7.2 — Risers sorts by gate + net10, NOT composite. Prove orders DIFFER.
    by_ris = [s.get("ticker") for s in sorted(stocks, key=_riser_key, reverse=True)]
    by_comp = [s.get("ticker") for s in sorted(
        stocks, key=lambda s: (s.get("composite") if s.get("composite") is not None else -1),
        reverse=True)]
    orders_differ = by_ris != by_comp
    keys = [_riser_key(s) for s in sorted(stocks, key=_riser_key, reverse=True)]
    monotone = all(keys[i] >= keys[i + 1] for i in range(len(keys) - 1))
    out.append((
        "AC-M7.2 Risers order = candidate→net10, differs from composite",
        orders_differ and monotone and n > 0,
        f"riser_top={by_ris[:3]} composite_top={by_comp[:3]} differ={orders_differ}",
    ))

    # AC-M7.3 — evidence-first: every stock ships the chart-verifiable evidence columns.
    ev_ok = all(RISER_KEYS <= set((s.get("riser") or {}).keys()) for s in stocks)
    out.append((
        "AC-M7.3 chart-verifiable evidence present (net5/10/20, up10, ddw10, ker10, streak)",
        ev_ok and n > 0,
        f"riser keys complete on all {n}",
    ))

    # AC-M7.4 — riser C9 same-source: every row carries it + stock↔board identity.
    covered = all(s.get("riser") is not None for s in stocks)
    xs_problems, stock_checked = check_riser.check_stock_same_source(board, stock_dir) \
        if stock_dir.exists() else (["stock bundles missing — run `make export`"], 0)
    out.append((
        "AC-M7.4 riser C9 same-source: every row + stock↔board identical",
        covered and not xs_problems and stock_checked > 0,
        f"covered={covered} stock_xcheck={stock_checked}",
    ))

    # AC-M7.5 — candidate board non-empty, bounded by top-N, flag ⇔ gate evidence consistent.
    cands = [s for s in stocks if (s.get("riser") or {}).get("candidate")]
    top_n = board.get("riser_top_n") or 0
    gate_problems = [p for p in problems if "gate evidence fails" in p or "streak_days" in p]
    out.append((
        "AC-M7.5 candidate board non-empty + <=top-N + stored flag consistent with gate evidence",
        1 <= len(cands) <= max(top_n, 1) and not gate_problems,
        f"candidates={len(cands)}/top-{top_n}, gate-evidence ok={not gate_problems}",
    ))

    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide AC-M7 aggregate acceptance check (steady-riser).")
    ap.add_argument("--board", default=str(ROOT / "web" / "public" / "data" / "board.json"))
    ap.add_argument("--stock-dir", default=str(ROOT / "web" / "public" / "data" / "stock"))
    args = ap.parse_args(argv)

    board_path = Path(args.board)
    if not board_path.exists():
        print(f"[ac-m7] board.json missing at {board_path} — run `make export` first.", file=sys.stderr)
        return 1
    board = json.loads(board_path.read_text())
    checks = ac_m7_checks(board, Path(args.stock_dir))

    print(f"AC-M7 acceptance (PRD §14, steady-riser) — as_of={board.get('as_of_date')} "
          f"stocks={board.get('count')} candidates={board.get('riser_candidates')}:")
    all_ok = True
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} ({detail})")
        all_ok = all_ok and ok

    if all_ok:
        print("\n[ac-m7] GATE_PASS AC-M7 all 5 clauses (PRD §14 §10.8)")
        return 0
    print("\n[ac-m7] GATE_FAIL — see failing clause(s) above", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
