"""Formal-filing PIT boundary check (AC-1 / AC-3, PRD §10.5).

Locks the crux of the formal-filing口径: P/S must NOT backfill to period_end. Between a
quarter's period_end and its effective_eod_date the PRIOR quarter's revenue is used; only
on/after effective_eod_date does the new quarter's revenue enter the denominator.

Self-contained — no network, no fixture: it builds a tiny two-quarter sample directly through
the production write path (compute.db.upsert_*) into a throwaway DuckDB, runs the real
compute.valuation, and asserts the boundary. Deterministic, so it pins the behaviour even if
the synthetic fixture's shape changes. PASS/FAIL, non-zero exit on failure (CI-friendly).

Canonical sample (the spec's AC-1):
    prev quarter:  period_end 2025-12-31, filed/effective 2026-02-15, revenue_ttm 100
    curr quarter:  period_end 2026-03-31, filed/effective 2026-04-24, revenue_ttm 200
    price 10 × shares 1000 → mktcap 10000, so P/S = 10000 / revenue_ttm.
Expect P/S = 100 (prior) through 2026-04-23, then 50 (current) from 2026-04-24 — NOT 50 from
2026-03-31, which would be the period_end backfill this check forbids.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compute import db, valuation  # noqa: E402

TICKER = "TEST"
# (date, open, high, low, close, adj_close, volume) — flat price so P/S moves only with the
# denominator. Dates straddle the current quarter's effective date (2026-04-24).
BARS = [
    ("2026-03-02", 10.0, 10.0, 10.0, 10.0, 10.0, 1000),
    ("2026-04-23", 10.0, 10.0, 10.0, 10.0, 10.0, 1000),  # day BEFORE the filing → prior quarter
    ("2026-04-24", 10.0, 10.0, 10.0, 10.0, 10.0, 1000),  # filing effective → current quarter
    ("2026-04-27", 10.0, 10.0, 10.0, 10.0, 10.0, 1000),
]
# db.FUNDAMENTALS_COLS order: period_end, filed_date, effective_eod_date, source_type,
# source_form, revenue_ttm, shares, total_debt, cash, ebitda_ttm, eps_ttm.
FUNDAMENTALS = [
    ("2025-12-31", "2026-02-15", "2026-02-15", db.SOURCE_FORMAL_FILING, db.SOURCE_FORM_UNKNOWN,
     100.0, 1000.0, 0.0, 0.0, None, None),
    ("2026-03-31", "2026-04-24", "2026-04-24", db.SOURCE_FORMAL_FILING, db.SOURCE_FORM_UNKNOWN,
     200.0, 1000.0, 0.0, 0.0, None, None),
]
# (query date, expected ps, expected as_of_period_end, expected as_of_effective_eod)
CASES = [
    ("2026-04-23", 100.0, "2025-12-31", "2026-02-15"),  # prior quarter still in force
    ("2026-04-24", 50.0, "2026-03-31", "2026-04-24"),   # current quarter just became effective
    ("2026-04-27", 50.0, "2026-03-31", "2026-04-24"),
]


def run_checks(con) -> list[tuple[str, bool, str]]:
    db.upsert_bars(con, TICKER, BARS)
    db.upsert_fundamentals(con, TICKER, FUNDAMENTALS)
    valuation.compute_valuation(con)

    checks: list[tuple[str, bool, str]] = []
    for qdate, exp_ps, exp_pe, exp_eff in CASES:
        row = con.execute(
            "SELECT ps, CAST(as_of_period_end AS VARCHAR), CAST(as_of_effective_eod AS VARCHAR), "
            "valuation_basis FROM valuation_daily WHERE ticker = ? AND date = ?",
            [TICKER, qdate],
        ).fetchone()
        if row is None:
            checks.append((f"{qdate}: row present", False, "no valuation_daily row"))
            continue
        ps, pe, eff, basis = row
        ok = (
            ps is not None and abs(ps - exp_ps) < 1e-6
            and pe == exp_pe and eff == exp_eff and basis == "formal_filing_pit"
        )
        checks.append((
            f"{qdate}: P/S={exp_ps:g} from {exp_pe} (effective {exp_eff})",
            ok,
            f"ps={ps} period_end={pe} effective={eff} basis={basis}",
        ))
    return checks


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        con = db.connect(Path(tmp) / "pit.duckdb")
        checks = run_checks(con)
        con.close()

    print("formal-filing PIT boundary (AC-1/AC-3, PRD §10.5):")
    all_ok = True
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} ({detail})")
        all_ok = all_ok and ok
    print(f"\nPIT_{'OK' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
