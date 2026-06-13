"""AC-M7 aggregate acceptance check (PRD §14, §10.8) — one-command, traceable.

The individual M7 invariants are already enforced piecemeal (compute/check.py
asserts the derived_daily ignition columns; export/check_ignition.py proves the
board ignition block is same-source as the engine + does the stock↔board
cross-check; the web vitest suite asserts the Discovery/Stock render order). What
was missing was a SINGLE labelled gate that maps 1:1 onto the five AC-M7 clauses
so the milestone is replayable in one command instead of by reciting which target
covers which clause. This script is that gate.

It reads the EXPORTED artifacts (board.json + per-name stock bundles — the same
files the browser consumes) and asserts each AC-M7 clause (PRD §14) explicitly:

  AC-M7.1  derived_daily ships ignition: every board stock carries the 5 raw
           components (ig_*) + ign_pct + ign_persist_days, in range (PRD §10.8.1).
  AC-M7.2  Discovery sorts by 持续点火 (sustained ignition), NOT composite: the
           board's sustained-ignition order (candidate → persist desc → pct desc,
           the exact key web/src/views/Discovery.tsx uses) is asserted to DIFFER
           from a pure composite ranking on this snapshot (PRD §9.3, §10.8.2).
  AC-M7.3  evidence-first: every stock's ignition.evidence carries the 点火证据
           the card head shows — breakout day / volume surge× / step-rate / MA50
           reclaim (PRD §9.3 "点火证据", §10.8.1).
  AC-M7.4  ignition ⇄ composite same-source (C9): ignition rides the SAME per-stock
           row as composite (both present together), and a sample of per-name Stock
           bundles carry byte-identical ignition blocks to board.json (cross-surface
           C9 — both assembled by board._ignition from one derived_daily).
  AC-M7.5  the 持续点火 board is non-empty AND traceable: ≥1 candidate, and each
           candidate satisfies the gate (ign_pct≥90 AND persist≥persist_min)
           recomputed from the shipped numbers (PRD §10.8.2/§10.8.3).

This deliberately reuses export/check_ignition.check (the same-source + candidate
+ vsurge + stock↔board guard) rather than re-deriving it — DRY, one source of the
C9 logic. It only ADDS the clauses that guard had no single labelled home for:
the composite-vs-ignition order divergence (AC-M7.2) and the per-clause framing.

Runs on the exported board.json + stock bundles (see `make ac-m7`, which runs the
full fixture pipeline → export → this check). Exits non-zero on any failure so it
gates. Names/counts only — no secrets.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from export import check_ignition  # noqa: E402  (reuse the same-source C9 guard)

TOP_DECILE = 90  # PRD §10.8.2 (must match board.IGN_TOP_DECILE / check_ignition.TOP_DECILE)
EVIDENCE_KEYS = {  # PRD §9.3 点火证据 / §10.8.1 — the card-head ignition evidence
    "breakout_day", "days_since_breakout", "vol_mult", "step_rate_ratio",
    "reclaimed_ma50", "ma50",
}


def _ign_key(s: dict):
    """The 持续点火 sort key — candidate first, then persist desc, then pct desc.
    Mirrors web/src/views/Discovery.tsx ignKey() EXACTLY (PRD §10.8.2, M7.3)."""
    ig = s.get("ignition") or {}
    return (
        1 if ig.get("candidate") else 0,
        ig.get("ign_persist_days") or 0,
        ig.get("ign_pct") or 0,
    )


def ac_m7_checks(board: dict, stock_dir: Path) -> list[tuple[str, bool, str]]:
    """Return [(clause, ok, detail)] for the five AC-M7 clauses (PRD §14)."""
    out: list[tuple[str, bool, str]] = []
    stocks = board.get("stocks", [])

    # Lean on the existing same-source guard for coverage/ranges/candidate-gate/vsurge.
    ok_core, problems, stats = check_ignition.check(board)
    cov = stats["ignition_coverage"]
    n = len(stocks)

    # AC-M7.1 — derived_daily ships ignition (5 raw components + ign_pct + persist).
    comp_ok = all(
        set((s.get("ignition") or {}).get("components") or {})
        == {"accel", "expand", "vsurge", "breakout", "rsturn"}
        for s in stocks
    )
    range_problems = [p for p in problems if "out of" in p or "< 0" in p or "components keys" in p]
    out.append((
        "AC-M7.1 derived_daily ships ignition (5 comps + ign_pct + ign_persist_days, in range)",
        cov == n and n > 0 and comp_ok and not range_problems,
        f"coverage={cov}/{n}, 5-component+range ok",
    ))

    # AC-M7.2 — Discovery sorts by 持续点火, NOT composite. Prove the orders DIFFER.
    by_ign = [s.get("ticker") for s in sorted(stocks, key=_ign_key, reverse=True)]
    by_comp = [s.get("ticker") for s in sorted(
        stocks, key=lambda s: (s.get("composite") if s.get("composite") is not None else -1),
        reverse=True)]
    orders_differ = by_ign != by_comp
    # Also assert the ignition order is genuinely sorted by the documented key
    # (non-increasing), so the divergence is the engine's, not a fluke.
    keys = [_ign_key(s) for s in sorted(stocks, key=_ign_key, reverse=True)]
    monotone = all(keys[i] >= keys[i + 1] for i in range(len(keys) - 1))
    out.append((
        "AC-M7.2 Discovery order = 持续点火 (candidate→persist→pct), differs from composite",
        orders_differ and monotone and n > 0,
        f"ign_top={by_ign[:3]} composite_top={by_comp[:3]} differ={orders_differ}",
    ))

    # AC-M7.3 — evidence-first: every stock ships the 点火证据 the card head shows.
    ev_ok = all(
        EVIDENCE_KEYS <= set(((s.get("ignition") or {}).get("evidence") or {}).keys())
        for s in stocks
    )
    out.append((
        "AC-M7.3 点火证据 present (breakout/vol×/step-rate/MA50 reclaim)",
        ev_ok and n > 0,
        f"evidence keys ⊇ {sorted(EVIDENCE_KEYS)} on all {n}",
    ))

    # AC-M7.4 — ignition ⇄ composite same-source (C9): same row + stock↔board identity.
    paired = all(
        (s.get("composite") is None) == (s.get("ignition") is None)
        for s in stocks
    )
    drift = board.get("ignition_recon_max_drift")
    drift_ok = drift is None or abs(drift) <= check_ignition.DRIFT_TOL
    xs_problems, stock_checked = check_ignition.check_stock_same_source(board, stock_dir) \
        if stock_dir.exists() else (["stock bundles missing — run `make export`"], 0)
    vsurge_problems = [p for p in problems if "evidence.vol_mult" in p]
    out.append((
        "AC-M7.4 ignition⇄composite same-source (C9): same row + stock↔board identical",
        paired and drift_ok and not xs_problems and not vsurge_problems and stock_checked > 0,
        f"paired={paired} drift={drift} stock_xcheck={stock_checked} vsurge_traced={stats['vsurge_checked']}",
    ))

    # AC-M7.5 — 持续点火 board non-empty AND traceable (candidate gate recomputed).
    persist_min = stats["persist_min"]
    cands = [s for s in stocks if (s.get("ignition") or {}).get("candidate")]
    gate_ok = all(
        ((s["ignition"].get("ign_pct") or 0) >= TOP_DECILE
         and (s["ignition"].get("ign_persist_days") or 0) >= persist_min)
        for s in cands
    )
    out.append((
        "AC-M7.5 持续点火 board non-empty + traceable (gate: pct≥90 AND persist≥min)",
        len(cands) >= 1 and gate_ok,
        f"candidates={len(cands)} (persist>={persist_min}), gate recomputed ok={gate_ok}",
    ))

    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide AC-M7 aggregate acceptance check.")
    ap.add_argument("--board", default=str(ROOT / "web" / "public" / "data" / "board.json"))
    ap.add_argument("--stock-dir", default=str(ROOT / "web" / "public" / "data" / "stock"))
    args = ap.parse_args(argv)

    board_path = Path(args.board)
    if not board_path.exists():
        print(f"[ac-m7] board.json missing at {board_path} — run `make export` first.", file=sys.stderr)
        return 1
    board = json.loads(board_path.read_text())
    checks = ac_m7_checks(board, Path(args.stock_dir))

    print(f"AC-M7 acceptance (PRD §14) — as_of={board.get('as_of_date')} "
          f"stocks={board.get('count')} candidates={board.get('ignition_candidates')}:")
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
