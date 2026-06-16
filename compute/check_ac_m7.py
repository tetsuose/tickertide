"""AC-M7 aggregate acceptance check (PRD §14, §10.8) — one-command, traceable.

After the 2026-06-16 spine pivot the core engine is base→breakout (ignition retired). The
individual M7 invariants are enforced piecemeal (compute/check.py asserts the derived_daily
brk_* columns; export/check_breakout.py proves the board breakout block is same-source as the
engine + does the stock↔board cross-check; the web vitest suite asserts the Breakouts/Stock
render order). This script is the SINGLE labelled gate that maps 1:1 onto the five AC-M7
clauses (PRD §14, rewritten for base→breakout) so the milestone is replayable in one command.

It reads the EXPORTED artifacts (board.json + per-name stock bundles — the same files the
browser consumes) and asserts each AC-M7 clause explicitly:

  AC-M7.1  derived_daily ships base→breakout: every board stock carries the 6 dimensionless
           features + brk_strength_pct, in range (PRD §10.8.1-10.8.2).
  AC-M7.2  Breakouts sorts by base→breakout STRENGTH, NOT composite: the board's recall-first
           order (candidate → brk_strength_pct desc, the key web/src/views/Breakouts.tsx uses)
           is asserted to DIFFER from a pure composite ranking on this snapshot (PRD §9.3, §10.8).
  AC-M7.3  evidence-first: every stock's breakout.evidence carries the base/τ/breakout 证据 the
           card head shows — kink date τ / days since τ / drift_step / fit_gain / clearance /
           volume surge / MA50 (PRD §9.3, §10.8.1).
  AC-M7.4  base→breakout C9 same-source: the breakout block rides every per-stock row, its
           evidence.vol_mult traces features.vsurge verbatim, and a sample of per-name Stock
           bundles carry byte-identical breakout blocks to board.json (cross-surface C9 — both
           assembled by board._breakout from one derived_daily).
  AC-M7.5  the candidate board is non-empty AND traceable: ≥1 candidate, and each candidate
           satisfies the recall-first gate (brk_strength_pct≥90) recomputed from the shipped
           number (PRD §10.8.3).

This reuses export/check_breakout.check (the same-source + candidate + vsurge + stock↔board
guard) rather than re-deriving it — DRY, one source of the C9 logic. It only ADDS the clauses
that guard had no single labelled home for: the composite-vs-breakout order divergence (AC-M7.2)
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

from export import check_breakout  # noqa: E402  (reuse the same-source C9 guard)

TOP_DECILE = 90  # PRD §10.8 (must match board.BRK_TOP_DECILE / check_breakout.BRK_TOP_DECILE)
EVIDENCE_KEYS = {  # PRD §9.3 base/τ/breakout 证据 / §10.8.1 — the card-head breakout evidence
    "tau_date", "days_since_tau", "drift_step", "fit_gain", "clearance", "vol_mult", "ma50",
}


def _brk_key(s: dict):
    """The base→breakout sort key — candidate first, then brk_strength_pct desc (recall-first;
    NO persistence — ignition retired). Mirrors web/src/views/Breakouts.tsx (PRD §9.3, §10.8)."""
    bk = s.get("breakout") or {}
    return (
        1 if bk.get("candidate") else 0,
        bk.get("brk_strength_pct") or 0,
    )


def ac_m7_checks(board: dict, stock_dir: Path) -> list[tuple[str, bool, str]]:
    """Return [(clause, ok, detail)] for the five AC-M7 clauses (PRD §14, base→breakout)."""
    out: list[tuple[str, bool, str]] = []
    stocks = board.get("stocks", [])

    # Lean on the existing same-source guard for coverage/ranges/candidate-gate/vsurge.
    ok_core, problems, stats = check_breakout.check(board)
    cov = stats["breakout_coverage"]
    n = len(stocks)

    # AC-M7.1 — derived_daily ships base→breakout (6 features + brk_strength_pct, in range).
    feat_ok = all(
        set((s.get("breakout") or {}).get("features") or {})
        == {"base_slope", "brk_slope", "drift_step", "fit_gain", "clearance", "vsurge"}
        for s in stocks
    )
    range_problems = [p for p in problems if "out of" in p or "< 0" in p or "features keys" in p]
    out.append((
        "AC-M7.1 derived_daily ships base→breakout (6 features + brk_strength_pct, in range)",
        cov == n and n > 0 and feat_ok and not range_problems,
        f"coverage={cov}/{n}, 6-feature+range ok",
    ))

    # AC-M7.2 — Breakouts sorts by base→breakout strength, NOT composite. Prove orders DIFFER.
    by_brk = [s.get("ticker") for s in sorted(stocks, key=_brk_key, reverse=True)]
    by_comp = [s.get("ticker") for s in sorted(
        stocks, key=lambda s: (s.get("composite") if s.get("composite") is not None else -1),
        reverse=True)]
    orders_differ = by_brk != by_comp
    keys = [_brk_key(s) for s in sorted(stocks, key=_brk_key, reverse=True)]
    monotone = all(keys[i] >= keys[i + 1] for i in range(len(keys) - 1))
    out.append((
        "AC-M7.2 Breakouts order = base→breakout strength (candidate→brk_pct), differs from composite",
        orders_differ and monotone and n > 0,
        f"brk_top={by_brk[:3]} composite_top={by_comp[:3]} differ={orders_differ}",
    ))

    # AC-M7.3 — evidence-first: every stock ships the base/τ/breakout 证据 the card head shows.
    ev_ok = all(
        EVIDENCE_KEYS <= set(((s.get("breakout") or {}).get("evidence") or {}).keys())
        for s in stocks
    )
    out.append((
        "AC-M7.3 base/τ/breakout 证据 present (τ/days-since/drift/fit/clearance/vol×/MA50)",
        ev_ok and n > 0,
        f"evidence keys ⊇ {sorted(EVIDENCE_KEYS)} on all {n}",
    ))

    # AC-M7.4 — base→breakout C9 same-source: every row carries it + stock↔board identity.
    covered = all(s.get("breakout") is not None for s in stocks)
    xs_problems, stock_checked = check_breakout.check_stock_same_source(board, stock_dir) \
        if stock_dir.exists() else (["stock bundles missing — run `make export`"], 0)
    vsurge_problems = [p for p in problems if "evidence.vol_mult" in p]
    out.append((
        "AC-M7.4 base→breakout C9 same-source: every row + stock↔board identical + vsurge traced",
        covered and not xs_problems and not vsurge_problems and stock_checked > 0,
        f"covered={covered} stock_xcheck={stock_checked} vsurge_traced={stats['vsurge_checked']}",
    ))

    # AC-M7.5 — candidate board non-empty AND traceable (recall-first gate recomputed).
    cands = [s for s in stocks if (s.get("breakout") or {}).get("candidate")]
    gate_ok = all(
        (s["breakout"].get("brk_strength_pct") or 0) >= TOP_DECILE
        for s in cands
    )
    out.append((
        "AC-M7.5 candidate board non-empty + traceable (gate: brk_strength_pct≥90)",
        len(cands) >= 1 and gate_ok,
        f"candidates={len(cands)}, gate recomputed ok={gate_ok}",
    ))

    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide AC-M7 aggregate acceptance check (base→breakout).")
    ap.add_argument("--board", default=str(ROOT / "web" / "public" / "data" / "board.json"))
    ap.add_argument("--stock-dir", default=str(ROOT / "web" / "public" / "data" / "stock"))
    args = ap.parse_args(argv)

    board_path = Path(args.board)
    if not board_path.exists():
        print(f"[ac-m7] board.json missing at {board_path} — run `make export` first.", file=sys.stderr)
        return 1
    board = json.loads(board_path.read_text())
    checks = ac_m7_checks(board, Path(args.stock_dir))

    print(f"AC-M7 acceptance (PRD §14, base→breakout) — as_of={board.get('as_of_date')} "
          f"stocks={board.get('count')} candidates={board.get('breakout_candidates')}:")
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
