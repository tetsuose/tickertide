"""Split-alignment boundary check (AC-SPLIT, PRD §10.5).

Locks the crux of split-alignment: when a stock split takes effect on the exchange, the
price series (daily_bars, yfinance) is split-adjusted to the latest session immediately,
but the per-share fundamentals (fundamentals_q, EDGAR) only re-state at the NEXT formal
filing. Between those two events `shares × adj_close ÷ revenue` (and `adj_close ÷ eps`)
would mix a POST-split price with a PRE-split share count, collapsing P/S, P/E, EV/S,
EV/EBITDA, PEG by the split ratio (KLAC's 10-for-1 ex-2026-06-11 made them ~10× too small).
compute/valuation.py lifts eps/shares by split_adj = ∏ ratio of splits with ex_date in
(filing effective_eod, price basis]; revenue/ebitda/debt/cash are absolute and untouched.

Self-contained — no network, no fixture: builds three tiny tickers directly through the
production write path (compute.db.upsert_*) into a throwaway DuckDB, runs the real
compute.valuation, and asserts each split_adj regime. Deterministic, so it pins the
behaviour even if the synthetic fixture's shape changes. PASS/FAIL, non-zero exit on
failure (CI-friendly).

Three regimes (each: flat split-adjusted price, so the multiple moves only with split_adj):
  A SPLIT_LAG   — split AFTER the only filing → split_adj = ratio (the bug this fixes).
                  pre-split eps 20 / shares 100, rev 1000, 10-for-1 split, price 10 →
                  P/E 5, P/S 10 (NOT 0.5 / 1, the pre-fix collapse).
  B NO_SPLIT    — no split → split_adj = 1 → byte-identical to the pre-split behaviour.
                  eps 20 / shares 100, rev 1000, price 10 → P/E 0.5, P/S 1.
  C POST_FILING — split BEFORE a (post-split-basis) filing → split_adj = 1, no double-count.
                  post-split eps 2 / shares 1000, rev 1000, price 10 → P/E 5, P/S 10.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compute import db, valuation  # noqa: E402

FF, FU = db.SOURCE_FORMAL_FILING, db.SOURCE_FORM_UNKNOWN


def _bar(d: str) -> tuple:
    """Flat bar (date, o, h, l, close, adj_close, vol); adj_close is the split-adjusted basis
    yfinance would emit (whole history lifted to the latest session)."""
    return (d, 10.0, 10.0, 10.0, 10.0, 10.0, 1000)


# fundamentals row = db.FUNDAMENTALS_COLS order: period_end, filed_date, effective_eod_date,
# source_type, source_form, revenue_ttm, shares, total_debt, cash, ebitda_ttm, eps_ttm.
SCENARIOS = {
    "SPLIT_LAG": {  # A — split lags the filing → align (the KLAC case)
        "bars": [_bar("2026-02-20"), _bar("2026-03-15")],
        "fundamentals": [("2025-12-31", "2026-02-15", "2026-02-15", FF, FU, 1000.0, 100.0, 0.0, 0.0, None, 20.0)],
        "splits": [("2026-03-01", 10.0)],
        "cases": [("2026-02-20", 5.0, 10.0), ("2026-03-15", 5.0, 10.0)],  # (date, exp_pe, exp_ps)
    },
    "NO_SPLIT": {  # B — no split → split_adj = 1 (back-compat)
        "bars": [_bar("2026-02-20"), _bar("2026-03-15")],
        "fundamentals": [("2025-12-31", "2026-02-15", "2026-02-15", FF, FU, 1000.0, 100.0, 0.0, 0.0, None, 20.0)],
        "splits": [],
        "cases": [("2026-03-15", 0.5, 1.0)],
    },
    "POST_FILING": {  # C — filing already in post-split basis → no double-count
        "bars": [_bar("2026-05-10")],
        "fundamentals": [("2026-03-31", "2026-05-01", "2026-05-01", FF, FU, 1000.0, 1000.0, 0.0, 0.0, None, 2.0)],
        "splits": [("2026-03-01", 10.0)],
        "cases": [("2026-05-10", 5.0, 10.0)],
    },
}


def run_checks(con) -> list[tuple[str, bool, str]]:
    for t, s in SCENARIOS.items():
        db.upsert_bars(con, t, s["bars"])
        db.upsert_fundamentals(con, t, s["fundamentals"])
        if s["splits"]:
            db.upsert_splits(con, t, s["splits"])
    valuation.compute_valuation(con)

    checks: list[tuple[str, bool, str]] = []
    for t, s in SCENARIOS.items():
        for qdate, exp_pe, exp_ps in s["cases"]:
            row = con.execute(
                "SELECT pe, ps FROM valuation_daily WHERE ticker = ? AND date = ?", [t, qdate]
            ).fetchone()
            if row is None:
                checks.append((f"{t} {qdate}: row present", False, "no valuation_daily row"))
                continue
            pe, ps = row
            ok = (
                pe is not None and abs(pe - exp_pe) < 1e-6
                and ps is not None and abs(ps - exp_ps) < 1e-6
            )
            checks.append((
                f"{t} {qdate}: P/E={exp_pe:g} P/S={exp_ps:g}",
                ok,
                f"pe={pe} ps={ps}",
            ))
    return checks


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        con = db.connect(Path(tmp) / "split.duckdb")
        checks = run_checks(con)
        con.close()

    print("split-alignment boundary (AC-SPLIT, PRD §10.5):")
    all_ok = True
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} ({detail})")
        all_ok = all_ok and ok
    print(f"\nSPLIT_{'OK' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
