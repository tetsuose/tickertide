"""SEC EDGAR fundamentals ingest (M0.2) -> fundamentals_q.

Pulls companyfacts per ticker and assembles trailing-4Q financials, point-in-time
(filed_date = as-of, anti-lookahead). Spec: PRD §6, §10.5, §12; data shape per the
M0.2 probe.

Trailing-4Q from companyfacts (which mixes single-quarter, YTD, and annual facts
under one concept):
  - single quarter  = fact whose (end-start) span ≈ 90d, OR a YTD difference (Q2=H1−Q1,
                      Q3=9M−H1, Q4=FY−9M) for concepts reported only cumulatively per
                      quarter (typical of cash-flow items like D&A)
  - annual / FY     = span ≈ 365d, fp=FY (10-K)
  - derive Q4 single = annual − sum(Q1,Q2,Q3 singles) of the same fiscal year
  - ttm(period_end) = sum of the 4 trailing single quarters (span-checked ~1yr)
  - annual-only filers fall back to yearly ttm points at each FY end
  - EBITDA = EBIT + D&A; EBIT = OperatingIncomeLoss, else pretax+interest (≈ EBIT) when a filer
             dropped it (KLAC post-2015) — best-effort (interest may be absent → pretax+D&A bound)
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
# EBIT fallback when a filer drops OperatingIncomeLoss (KLAC stopped tagging it after 2015,
# and GrossProfit/CostsAndExpenses too): pretax income + interest expense ≈ EBIT (operating
# income). Best-effort — interest may also be absent, then EBITDA = pretax + D&A (a lower
# bound, since interest isn't added back). See extract().
PRETAX = ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
          "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]
INTEREST = ["InterestExpense", "InterestExpenseNonoperating", "InterestAndDebtExpense"]
DDA = ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
       "DepreciationAndAmortization"]
# D&A component fallback for filers that tag depreciation and amortization SEPARATELY with no
# combined concept (MSFT: Depreciation $15.2B + AmortizationOfIntangibleAssets $4.8B, no
# DepreciationDepletionAndAmortization). D&A ≈ Depreciation + intangible amortization; misses the
# cash-flow "& other" line (operating/finance-lease etc., ~$2.3B for MSFT) → slight undercount,
# best-effort (PRD §10.5). Used ONLY when the combined concepts above yield nothing, so combined-
# tag filers (KLAC/AAPL/NVDA) never touch this path (no double-count).
DEPREC = ["Depreciation"]
AMORT = ["AmortizationOfIntangibleAssets", "FiniteLivedIntangibleAssetsAmortizationExpense"]
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


def _flow_ttm(units: list[dict], ytd_diff: bool = True) -> dict[str, tuple[float, str]]:
    """period_end -> (trailing-4Q value, filed_date) for a flow concept.

    Keyed by the (start,end) PERIOD, not fy/fp — EDGAR mislabels fy/fp on repeated
    comparatives (a prior quarter re-stated in a later filing keeps the new filing's
    fy/fp), which corrupts grouping. Earliest filed per period = original report
    (PIT, anti-restatement).

    Single quarters come from two sources: (a) DIRECT ~90d facts, and (b) YTD DIFFERENCING.
    Many cash-flow-statement concepts (e.g. DepreciationDepletionAndAmortization) report ONLY
    cumulative YTD per quarter — Q1=~91d, H1=~183d, 9M=~273d, FY=~365d — never a standalone
    Q2/Q3/Q4. The single quarter is then the consecutive-YTD diff within one fiscal year
    (same start): Q2 = H1−Q1, Q3 = 9M−H1, Q4 = FY−9M. Without (b) such concepts produce NO
    quarterly TTM (only annual points), which is why EBITDA was n.m. for YTD-only D&A filers
    (KLAC). A direct ~90d single always wins; differencing only fills ends with no direct single.
    """
    # Earliest-filed dedup per (start,end) period = original report (PIT, anti-restatement).
    raw: dict[tuple, tuple[float, str]] = {}  # (start,end) -> (val, filed)
    for f in units:
        if "val" not in f or not f.get("start") or not f.get("end"):
            continue
        k = (f["start"], f["end"])
        filed = f.get("filed", "")
        if k not in raw or filed < raw[k][1]:
            raw[k] = (float(f["val"]), filed)

    singles: dict[str, tuple] = {}   # end -> (start, end, val, filed)
    annual: dict[str, tuple] = {}    # end -> (start, end, val, filed)
    for (start, end), (val, filed) in raw.items():
        span = (date.fromisoformat(end) - date.fromisoformat(start)).days
        if 80 <= span <= 100:
            if end not in singles or filed < singles[end][3]:
                singles[end] = (start, end, val, filed)
        elif 340 <= span <= 380:
            if end not in annual or filed < annual[end][3]:
                annual[end] = (start, end, val, filed)

    # YTD differencing: within one fiscal year (same start), consecutive-YTD ends differ by one
    # single quarter. Only FILLS ends that have no direct ~90d single (direct always wins).
    # OFF for per-share concepts (eps, ytd_diff=False): EPS is NOT additive across quarters, so
    # synthesizing a quarter via YTD diff would perturb the existing Σ-of-direct-singles TTM —
    # we keep eps_ttm byte-stable and only enable differencing for additive USD flows.
    if ytd_diff:
        by_start: dict[str, list] = {}
        for (start, end), (val, filed) in raw.items():
            by_start.setdefault(start, []).append((end, val, filed))
        for lst in by_start.values():
            lst.sort()  # by end
            for (pend, pval, _), (end, val, filed) in zip(lst, lst[1:]):
                seg = (date.fromisoformat(end) - date.fromisoformat(pend)).days
                if 80 <= seg <= 100 and end not in singles:
                    singles[end] = (pend, end, val - pval, filed)

    # Derive Q4 single = annual − 3 single quarters inside the fiscal year — fallback for filers
    # that give annual + 3 singles but no 9M YTD to diff Q4 from (YTD differencing covers the rest).
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
    """companyfacts -> rows in db.FUNDAMENTALS_COLS order:
    (period_end, filed, effective_eod_date, source_type, source_form,
     revenue_ttm, shares, total_debt, cash, ebitda_ttm, eps_ttm).

    Formal-filing PIT (PRD §10.5): companyfacts exposes only formal SEC filings, so every
    row is source_type='formal_filing'. v1 sets effective_eod_date = filed (the official
    filing date) — companyfacts has no accepted-timestamp, so we cannot yet tell a
    pre-close from a post-close filing; v2 would push post-close filings to the next
    trading day. source_form stays 'unknown' (companyfacts doesn't carry the form reliably)."""
    gaap = cf.get("facts", {}).get("us-gaap", {})
    if not gaap:
        return []
    rev = _flow_ttm(_units(gaap, REVENUE, "USD"))
    eps = _flow_ttm(_units(gaap, EPS, "USD/shares"), ytd_diff=False)  # EPS not additive — keep Σ-singles TTM stable
    opinc = _flow_ttm(_units(gaap, OPINC, "USD"))
    pretax = _flow_ttm(_units(gaap, PRETAX, "USD"))
    interest = _flow_ttm(_units(gaap, INTEREST, "USD"))
    # D&A: prefer a COMBINED concept (DDA merges synonymous / over-time-switched tags — a filer may
    # use DepreciationDepletionAndAmortization some years, DepreciationAndAmortization others; AAPL/
    # NVDA do — merging covers both). DDA excludes the bare component Depreciation, so no double-count.
    # If NO combined concept is present (MSFT tags depreciation + amortization separately), sum the
    # components: D&A ≈ Depreciation + intangible amortization (per period; amortization 0 if absent,
    # filed = later of the two for PIT). Misses cash-flow "& other" → slight undercount, best-effort.
    dda = _flow_ttm(_units(gaap, DDA, "USD"))
    if not dda:
        dep = _flow_ttm(_units(gaap, DEPREC, "USD"))
        amort = _flow_ttm(_units(gaap, AMORT, "USD"))
        dda = {}
        for pe, (dv, df) in dep.items():
            av, af = amort.get(pe, (0.0, df))
            dda[pe] = (dv + av, max(df, af))
    shares_i = _instant(_units(gaap, SHARES, "shares"))
    cash_i = _instant(_units(gaap, CASH, "USD"))
    debt_lt_i = _instant(_units(gaap, DEBT_LT, "USD"))
    debt_cur_i = _instant(_units(gaap, DEBT_CUR, "USD"))

    rows: list[tuple] = []
    for pe in sorted(rev):
        rev_v, filed = rev[pe]
        op, dd = opinc.get(pe), dda.get(pe)
        # EBIT = operating income; fall back to pretax + interest (≈ EBIT) when the filer
        # dropped OperatingIncomeLoss (KLAC post-2015). EBITDA = EBIT + D&A; the D&A single
        # quarters may be YTD-differenced (_flow_ttm). If interest is also absent, EBITDA is the
        # pretax+D&A lower bound (interest not added back) — best-effort, EV/EBITDA falls back to EV/S.
        if op:
            ebit = op[0]
        else:
            pt, ie = pretax.get(pe), interest.get(pe)
            ebit = (pt[0] + (ie[0] if ie else 0.0)) if pt else None
        ebitda = (ebit + dd[0]) if (ebit is not None and dd) else None
        lt = _nearest(debt_lt_i, pe)
        cur = _nearest(debt_cur_i, pe)
        total_debt = (lt + (cur or 0.0)) if lt is not None else None
        rows.append((
            pe, filed,
            filed, db.SOURCE_FORMAL_FILING, db.SOURCE_FORM_UNKNOWN,  # formal-filing PIT (v1: effective == filed)
            rev_v,
            _nearest(shares_i, pe), total_debt, _nearest(cash_i, pe),
            ebitda, eps.get(pe, (None,))[0],
        ))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M0.2 EDGAR fundamentals ingest.")
    ap.add_argument("--limit", type=int, default=500, help="top-N universe by mktcap (when --min-mktcap unset)")
    ap.add_argument("--min-mktcap", type=float, default=None,
                    help="M6 floor mode: pull fundamentals for ALL names with mktcap >= this "
                         "(USD); overrides --limit. EDGAR is rate-limited (~10 req/s) so this is "
                         "the slow step — Ocean's P/S axis needs it, Breakouts detection does not.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    if args.min_mktcap is not None:
        universe = con.execute(
            "SELECT ticker FROM universe WHERE mktcap >= ? ORDER BY mktcap DESC",
            [args.min_mktcap],
        ).fetchall()
    else:
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
