"""SEC EDGAR fundamentals ingest (M0.2) -> fundamentals_q.

Pulls companyfacts per ticker and assembles trailing-4Q financials, point-in-time
(filed_date = as-of, anti-lookahead). Spec: PRD §6, §10.5, §12; data shape per the
M0.2 probe.

Trailing-4Q from companyfacts (which mixes single-quarter, YTD, and annual facts
under one concept):
  - single quarter  = fact whose (end-start) span ≈ 90d
  - annual / FY     = span ≈ 365d, fp=FY (10-K)
  - derive Q4 single = annual − sum(Q1,Q2,Q3 singles) of the same fiscal year
  - ttm(period_end) = sum of the 4 trailing single quarters (span-checked ~1yr)
  - annual-only filers fall back to yearly ttm points at each FY end
Balance-sheet items (shares/cash/debt) are instant — nearest value as-of period_end.

EDGAR requires a descriptive User-Agent and rate-limits ~10 req/s. companyfacts
concept names are inconsistent, so each metric has a fallback list. segment_revenue
is NOT populated here (companyfacts has no XBRL segment dimension — that is M4).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compute import db  # noqa: E402

UA = {"User-Agent": "tickertide/0.1 (personal research; ai@cyberbrid.com)"}
CIK_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
RATE_SLEEP = 0.13  # ~8 req/s, under EDGAR's ~10/s

# Concept fallback lists (first present wins).
REVENUE = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]
EPS = ["EarningsPerShareDiluted", "EarningsPerShareBasic"]
OPINC = ["OperatingIncomeLoss"]
DDA = ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
       "DepreciationAndAmortization"]
SHARES = ["CommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding"]
CASH = ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]
DEBT_LT = ["LongTermDebtNoncurrent", "LongTermDebt"]
DEBT_CUR = ["LongTermDebtCurrent", "DebtCurrent"]


def _get(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as resp:
        return json.load(resp)


def fetch_cik_map() -> dict[str, str]:
    """ticker (upper) -> zero-padded 10-digit CIK."""
    raw = _get(CIK_URL)
    out: dict[str, str] = {}
    for rec in raw.values():
        t = str(rec.get("ticker", "")).strip().upper()
        if t:
            out[t] = f"{int(rec['cik_str']):010d}"
    return out


def fetch_companyfacts(cik: str) -> dict | None:
    try:
        return _get(FACTS_URL.format(cik=cik))
    except Exception:
        return None


def _units(gaap: dict, concepts: list[str], unit_key: str) -> list[dict]:
    # Merge ALL present fallback concepts: a company may switch concepts over time
    # (e.g. RevenueFromContract... early, Revenues later) — first-present-only would
    # miss the later years. Downstream dedup keeps the earliest filing per period.
    out: list[dict] = []
    for c in concepts:
        node = gaap.get(c)
        if node and unit_key in node.get("units", {}):
            out.extend(node["units"][unit_key])
    return out


def _span_days(f: dict) -> int | None:
    if not f.get("start") or not f.get("end"):
        return None
    return (date.fromisoformat(f["end"]) - date.fromisoformat(f["start"])).days


def _flow_ttm(units: list[dict]) -> dict[str, tuple[float, str]]:
    """period_end -> (trailing-4Q value, filed_date) for a flow concept.

    Keyed by the (start,end) PERIOD, not fy/fp — EDGAR mislabels fy/fp on repeated
    comparatives (a prior quarter re-stated in a later filing keeps the new filing's
    fy/fp), which corrupts grouping. Earliest filed per period = original report
    (PIT, anti-restatement). Q4 single is derived from annual − the 3 single
    quarters that fall inside the fiscal year.
    """
    singles: dict[str, tuple] = {}   # end -> (start, end, val, filed)
    annual: dict[str, tuple] = {}    # end -> (start, end, val, filed)
    for f in units:
        span = _span_days(f)
        if span is None or "val" not in f or not f.get("end"):
            continue
        start, end, filed = f.get("start"), f["end"], f.get("filed", "")
        if 80 <= span <= 100:
            if end not in singles or filed < singles[end][3]:
                singles[end] = (start, end, float(f["val"]), filed)
        elif 340 <= span <= 380:
            if end not in annual or filed < annual[end][3]:
                annual[end] = (start, end, float(f["val"]), filed)

    # Derive Q4 single = annual − sum(3 single quarters inside the fiscal year).
    for aend, (astart, _, aval, afiled) in annual.items():
        if aend in singles or not astart:
            continue
        inside = [s for s in singles.values() if s[0] and s[0] >= astart and s[1] < aend]
        if len(inside) == 3:
            singles[aend] = (astart, aend, aval - sum(x[2] for x in inside), afiled)

    qs = sorted(singles.values(), key=lambda x: x[1])  # by end
    ttm: dict[str, tuple[float, str]] = {}
    for i in range(3, len(qs)):
        win = qs[i - 3:i + 1]
        # 4 consecutive quarter-ENDS span 3 gaps ≈ 273d (NOT 365d, which would be 5 quarters).
        span = (date.fromisoformat(win[-1][1]) - date.fromisoformat(win[0][1])).days
        if 250 <= span <= 295:
            ttm[win[-1][1]] = (sum(w[2] for w in win), max(w[3] for w in win))

    # Annual-only fallback: ensure every FY end has a ttm point.
    for aend, (_, _, aval, afiled) in annual.items():
        ttm.setdefault(aend, (aval, afiled))
    return ttm


def _instant(units: list[dict]) -> dict[str, tuple[float, str]]:
    """end -> (value, filed) for an instant (balance-sheet) concept."""
    out: dict[str, tuple[float, str]] = {}
    for f in units:
        if "val" not in f or not f.get("end"):
            continue
        e, filed = f["end"], f.get("filed", "")
        if e not in out or filed < out[e][1]:  # earliest filing = original (anti-restatement, PIT)
            out[e] = (float(f["val"]), filed)
    return out


def _nearest(inst: dict[str, tuple[float, str]], on: str) -> float | None:
    cands = [e for e in inst if e <= on]
    return inst[max(cands)][0] if cands else None


def extract(cf: dict) -> list[tuple]:
    """companyfacts -> rows (period_end, filed, revenue_ttm, shares, total_debt, cash, ebitda_ttm, eps_ttm)."""
    gaap = cf.get("facts", {}).get("us-gaap", {})
    if not gaap:
        return []
    rev = _flow_ttm(_units(gaap, REVENUE, "USD"))
    eps = _flow_ttm(_units(gaap, EPS, "USD/shares"))
    opinc = _flow_ttm(_units(gaap, OPINC, "USD"))
    dda = _flow_ttm(_units(gaap, DDA, "USD"))
    shares_i = _instant(_units(gaap, SHARES, "shares"))
    cash_i = _instant(_units(gaap, CASH, "USD"))
    debt_lt_i = _instant(_units(gaap, DEBT_LT, "USD"))
    debt_cur_i = _instant(_units(gaap, DEBT_CUR, "USD"))

    rows: list[tuple] = []
    for pe in sorted(rev):
        rev_v, filed = rev[pe]
        op, dd = opinc.get(pe), dda.get(pe)
        ebitda = (op[0] + dd[0]) if (op and dd) else None
        lt = _nearest(debt_lt_i, pe)
        cur = _nearest(debt_cur_i, pe)
        total_debt = (lt + (cur or 0.0)) if lt is not None else None
        rows.append((
            pe, filed, rev_v,
            _nearest(shares_i, pe), total_debt, _nearest(cash_i, pe),
            ebitda, eps.get(pe, (None,))[0],
        ))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M0.2 EDGAR fundamentals ingest.")
    ap.add_argument("--limit", type=int, default=500, help="top-N universe by mktcap to pull")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    universe = con.execute(
        "SELECT ticker FROM universe WHERE mktcap IS NOT NULL ORDER BY mktcap DESC LIMIT ?",
        [args.limit],
    ).fetchall()
    tickers = [r[0] for r in universe]
    if not tickers:
        print("[edgar] universe empty — run ingest (M0.1) first.")
        return 1

    print(f"[edgar] fetching CIK map ...")
    cik_map = fetch_cik_map()
    print(f"[edgar] cik map={len(cik_map)}; targets={len(tickers)}")

    ok = no_cik = no_facts = 0
    for i, t in enumerate(tickers, 1):
        cik = cik_map.get(t)
        if not cik:
            no_cik += 1
            continue
        cf = fetch_companyfacts(cik)
        time.sleep(RATE_SLEEP)
        if not cf:
            no_facts += 1
            continue
        try:
            rows = extract(cf)
        except Exception as e:
            print(f"  [skip] {t}: {type(e).__name__}: {str(e)[:70]}")
            no_facts += 1
            continue
        if rows:
            db.upsert_fundamentals(con, t, rows)
            ok += 1
        if i % 50 == 0:
            print(f"  ... {i}/{len(tickers)} (ok={ok} no_cik={no_cik} no_facts={no_facts})")

    print(f"[edgar] done ok={ok} no_cik={no_cik} no_facts={no_facts}")
    print(f"[summary] fundamentals_q rows={db.count(con,'fundamentals_q')} "
          f"tickers={con.execute('SELECT count(DISTINCT ticker) FROM fundamentals_q').fetchone()[0]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
