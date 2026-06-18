"""EBITDA assembly check (AC-EBITDA, PRD §10.5).

Locks the two fixes that made EBITDA — and the margin / rule40 that derive from it —
computable for filers where it was permanently n.m.:
  (1) YTD DIFFERENCING in _flow_ttm: cash-flow concepts (D&A) reported only cumulatively per
      quarter (Q1≈91d, H1≈183d, 9M≈273d, FY≈365d) now yield single quarters (Q2=H1−Q1, ...)
      and hence a quarterly trailing-4Q. EPS is excluded (ytd_diff=False) — not additive.
  (2) EBIT FALLBACK in extract: when a filer drops OperatingIncomeLoss (KLAC post-2015), EBIT =
      pretax income + interest expense, so EBITDA = EBIT + D&A is still produced. OperatingIncomeLoss
      wins when present.

Self-contained, no network: feeds synthetic companyfacts / unit lists through the REAL
ingest.edgar functions. Deterministic. PASS/FAIL, non-zero exit (CI-friendly).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingest import edgar  # noqa: E402

_Q = [("2024-01-01", "2024-03-31"), ("2024-04-01", "2024-06-30"), ("2024-07-01", "2024-09-30"),
      ("2024-10-01", "2024-12-31"), ("2025-01-01", "2025-03-31"), ("2025-04-01", "2025-06-30"),
      ("2025-07-01", "2025-09-30")]


def _singles(vals: list[float]) -> list[dict]:
    """7 calendar quarters 2024Q1..2025Q3 as DIRECT single-quarter (~90d) facts."""
    return [{"start": s, "end": e, "val": v, "filed": e} for (s, e), v in zip(_Q, vals)]


def _ytd(year_pts: dict[int, list[tuple]]) -> list[dict]:
    """Cumulative YTD facts (same fiscal-year start) — the shape D&A often takes."""
    return [{"start": f"{yr}-01-01", "end": end, "val": val, "filed": end}
            for yr, pts in year_pts.items() for end, val in pts]


# Trailing-4Q ending 2025-09-30 spans 2024Q4 + 2025Q1..Q3.
_DDA_YTD = _ytd({2024: [("2024-03-31", 5), ("2024-06-30", 10), ("2024-09-30", 15), ("2024-12-31", 20)],
                 2025: [("2025-03-31", 5), ("2025-06-30", 10), ("2025-09-30", 15)]})
_SHARES = [{"end": e, "val": 1000, "filed": e} for _, e in _Q]


def _cf(extra: dict | None = None) -> dict:
    g = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": _singles([100] * 7)}},
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest":
            {"units": {"USD": _singles([20] * 7)}},
        "InterestExpense": {"units": {"USD": _singles([2] * 7)}},
        "DepreciationDepletionAndAmortization": {"units": {"USD": _DDA_YTD}},
        "CommonStockSharesOutstanding": {"units": {"shares": _SHARES}},
    }
    if extra:
        g.update(extra)
    return {"facts": {"us-gaap": g}}


def _ebitda_at(rows: list[tuple], period_end: str):
    for r in rows:  # row[9] = ebitda_ttm, row[0] = period_end
        if str(r[0]) == period_end:
            return r[9]
    return None


def run_checks() -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []

    # (1) YTD differencing → quarterly TTM. TTM(2025-09-30) = Q4'24(5)+Q1'25(5)+Q2'25(5)+Q3'25(5) = 20.
    ttm = edgar._flow_ttm(_DDA_YTD)
    got = ttm.get("2025-09-30")
    checks.append(("YTD diff → quarterly TTM(2025-09-30)=20", got is not None and abs(got[0] - 20) < 1e-9, f"{got}"))

    # ytd_diff=False (EPS semantics): Q2/Q3 not synthesized → no quarterly TTM at 2025-09-30.
    ttm_nod = edgar._flow_ttm(_DDA_YTD, ytd_diff=False)
    checks.append(("ytd_diff=False → no synthetic quarter", ttm_nod.get("2025-09-30") is None, f"{ttm_nod.get('2025-09-30')}"))

    # (2) EBIT fallback: OperatingIncomeLoss absent → EBIT = pretax(80) + interest(8) = 88;
    # EBITDA = 88 + D&A(20) = 108.
    eb = _ebitda_at(edgar.extract(_cf()), "2025-09-30")
    checks.append(("EBIT fallback (no opinc): EBITDA=108", eb is not None and abs(eb - 108) < 1e-6, f"{eb}"))

    # OperatingIncomeLoss present (25/q → TTM 100) wins: EBITDA = 100 + D&A(20) = 120 (NOT 108).
    eb2 = _ebitda_at(edgar.extract(_cf({"OperatingIncomeLoss": {"units": {"USD": _singles([25] * 7)}}})), "2025-09-30")
    checks.append(("opinc present wins: EBITDA=120", eb2 is not None and abs(eb2 - 120) < 1e-6, f"{eb2}"))

    return checks


def main() -> int:
    checks = run_checks()
    print("EBITDA assembly (AC-EBITDA, PRD §10.5):")
    all_ok = True
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} ({detail})")
        all_ok = all_ok and ok
    print(f"\nEBITDA_{'OK' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
