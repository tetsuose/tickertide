"""M0.4 valuation: daily_bars ASOF JOIN fundamentals_q -> valuation_daily.

Math spec: PRD §10.5. All multiples = price/EV ÷ trailing-4Q, computed daily —
numerator (price, mktcap=shares×close, EV) is daily; the denominator steps at each
filing. The ASOF JOIN keys on filed_date (NOT period_end) so a given trading day
only ever sees financials already public on that day (point-in-time, anti-lookahead).

  pe        = close / eps_ttm                         (eps_ttm<=0 -> NULL = n.m., fall back to ps)
  ps        = (shares*close) / revenue_ttm
  evs       = EV / revenue_ttm,  EV = shares*close + total_debt − cash
  ev_ebitda = EV / ebitda_ttm                          (ebitda_ttm<=0/NULL -> NULL, fall back to evs)
  growth    = revenue_ttm YoY (4 quarters back, ~1yr span-checked)
  margin    = ebitda_ttm / revenue_ttm
  rule40    = growth% + margin%
  peg       = pe / growth%                             (growth>0)

common-vintage ranking (PRD §10.5): percentile only within the fresh cohort
(as-of age <= ~95d); stale rows are excluded ("vint"), never ranked against fresh.

NOTE: daily mktcap here = shares(EDGAR) × close, the per-stock derived mktcap.
universe.mktcap (Nasdaq snapshot) is a separate latest-only figure; reconciling the
two is a later refinement (PRD §17).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compute import db  # noqa: E402

_SQL = """
INSERT INTO valuation_daily
WITH fe AS (
  SELECT ticker, period_end, filed_date, revenue_ttm, shares, total_debt, cash, ebitda_ttm, eps_ttm,
    CASE WHEN datediff('day', LAG(period_end, 4) OVER w, period_end) BETWEEN 330 AND 400
         THEN revenue_ttm / NULLIF(LAG(revenue_ttm, 4) OVER w, 0) - 1 END AS growth,
    CASE WHEN revenue_ttm > 0 AND ebitda_ttm IS NOT NULL THEN ebitda_ttm / revenue_ttm END AS margin
  FROM fundamentals_q
  WINDOW w AS (PARTITION BY ticker ORDER BY period_end)
),
j AS (
  SELECT b.ticker, b.date, b.adj_close AS px,
         f.period_end, f.filed_date, f.revenue_ttm, f.shares, f.total_debt, f.cash,
         f.ebitda_ttm, f.eps_ttm, f.growth, f.margin
  FROM daily_bars b
  ASOF LEFT JOIN fe f
    ON b.ticker = f.ticker AND b.date >= f.filed_date
)
SELECT ticker, date,
  CASE WHEN eps_ttm > 0 THEN px / eps_ttm END AS pe,
  CASE WHEN revenue_ttm > 0 AND shares > 0 THEN (shares * px) / revenue_ttm END AS ps,
  CASE WHEN revenue_ttm > 0 AND shares > 0
       THEN (shares * px + COALESCE(total_debt, 0) - COALESCE(cash, 0)) / revenue_ttm END AS evs,
  CASE WHEN ebitda_ttm > 0 AND shares > 0
       THEN (shares * px + COALESCE(total_debt, 0) - COALESCE(cash, 0)) / ebitda_ttm END AS ev_ebitda,
  CASE WHEN eps_ttm > 0 AND growth > 0 THEN (px / eps_ttm) / (growth * 100) END AS peg,
  growth, margin,
  CASE WHEN growth IS NOT NULL AND margin IS NOT NULL THEN growth * 100 + margin * 100 END AS rule40,
  period_end AS as_of_period_end, filed_date AS as_of_filed
FROM j
WHERE revenue_ttm IS NOT NULL AND shares IS NOT NULL
"""


def compute_valuation(con) -> dict:
    """Recompute valuation_daily from daily_bars + fundamentals_q. Returns counts."""
    if db.count(con, "fundamentals_q") == 0:
        raise RuntimeError("fundamentals_q is empty — run EDGAR ingest (M0.2) first.")
    db.clear_valuation(con)
    con.execute(_SQL)
    return {
        "rows": db.count(con, "valuation_daily"),
        "tickers": con.execute("SELECT count(DISTINCT ticker) FROM valuation_daily").fetchone()[0],
    }


def latest_common_vintage(con, metric: str = "ps", fresh_days: int = 95):
    """Common-vintage percentile of `metric` on the latest date.

    Returns (latest_date, {ticker: percentile}, n_fresh, n_stale). Stale rows
    (as-of age > fresh_days) are excluded from the cohort — never ranked.
    """
    latest = con.execute("SELECT max(date) FROM valuation_daily").fetchone()[0]
    rows = con.execute(
        f"SELECT ticker, {metric}, datediff('day', as_of_period_end, date) AS age "
        f"FROM valuation_daily WHERE date = ? AND {metric} IS NOT NULL",
        [latest],
    ).fetchall()
    fresh = sorted([(t, v) for t, v, age in rows if age is not None and age <= fresh_days], key=lambda x: x[1])
    n_stale = sum(1 for _, _, age in rows if age is None or age > fresh_days)
    n = len(fresh)
    pct = {t: (round(100 * i / (n - 1)) if n > 1 else 50) for i, (t, _) in enumerate(fresh)}
    return latest, pct, n, n_stale


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M0.4 valuation: valuation_daily.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    print("[valuation] ASOF JOIN daily_bars × fundamentals_q ...")
    stats = compute_valuation(con)
    print(f"[valuation] valuation_daily rows={stats['rows']} tickers={stats['tickers']}")

    latest = con.execute("SELECT max(date) FROM valuation_daily").fetchone()[0]
    print(f"[valuation] {latest} sample (P/E n.m. = E<=0):")
    for r in con.execute(
        "SELECT ticker, round(pe,1), round(ps,1), round(evs,1), round(growth*100,0), round(rule40,0), "
        "datediff('day', as_of_period_end, date) AS age "
        "FROM valuation_daily WHERE date = ? ORDER BY ps DESC NULLS LAST LIMIT 6", [latest]
    ).fetchall():
        pe = "n.m." if r[1] is None else r[1]
        print(f"    {r[0]:6} P/E={pe!s:>6} P/S={r[2]!s:>5} EV/S={r[3]!s:>5} growth={r[4]}% R40={r[5]} asof_age={r[6]}d")

    _, pct, n_fresh, n_stale = latest_common_vintage(con, "ps")
    print(f"[valuation] common-vintage P/S percentile: fresh cohort={n_fresh}, stale excluded={n_stale}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
