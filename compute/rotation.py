"""M3.2 rotation compute: bucket_bars + spx_daily -> bucket_rrg (weekly RS-Ratio).

Math spec: PRD §10.4 (JdK RS-Ratio, transparent reconstruction). Weekly basis: daily
bucket/SPX closes are resampled to Friday close, then per bucket:
    RS       = 100 * P_bucket / P_SPX                    (price relative; NOT RSI/IBD-RS)
    M        = EMA(RS, n1)
    RS-Ratio = 100 + k * (M - SMA(M, n2)) / std(M, n2)   (z-score recentered to 100)
>100 = the bucket is outperforming its own recent trend. The z-score basis is TEMPORAL
(each sector vs its own history) — valid because the 11 GICS sectors are a fixed set;
themes (M4, changing membership) will need point-in-time (PRD §10.4, C3).

RS-Momentum 归一量 is CUT (PRD §16): momentum = the SLOPE of rs_ratio, derived on the
fly (slope_4w / infer_state below, reused by export/web). bucket_rrg stores only the
rs line + rs_ratio.

Constants (n1, n2, k) are a transparent reconstruction — de Kempenaer's exact values
are unpublished, so this does NOT claim to replicate StockCharts numbers (PRD §10.4).
They live in PARAMS so export/rotation.json can surface them for audit.

Usage:
    python3 compute/rotation.py [--db data/tickertide.duckdb] [--n1 10] [--n2 10] [--k 1.0]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from compute import db  # noqa: E402

# Transparent-reconstruction constants (PRD §10.4, ROADMAP M3.2). Tunable; surfaced in
# export rotation.json params. NOT a claim to replicate StockCharts / de Kempenaer.
PARAMS = {"basis": "weekly", "n1_ema": 10, "n2_window": 10, "k": 1.0}
BUCKET_TYPE = "sector"


def to_weekly(dates: pd.Series, closes: pd.Series) -> pd.Series:
    """Resample a daily close series to weekly (Friday) last close, indexed by week-end date.
    'W-FRI' bins each Mon..Fri into its Friday; last() takes that week's final close."""
    s = pd.Series(np.asarray(closes, dtype=float), index=pd.to_datetime(np.asarray(dates))).sort_index()
    return s.resample("W-FRI").last().dropna()


def rs_ratio_series(rs: pd.Series, n1: int, n2: int, k: float) -> pd.Series:
    """JdK RS-Ratio from a weekly RS line: z-score of EMA(rs,n1) over its SMA/std(.,n2),
    recentered to 100 (PRD §10.4). First n1+n2-ish weeks are NaN (warm-up)."""
    m = rs.ewm(span=n1, adjust=False).mean()
    sma = m.rolling(n2).mean()
    sd = m.rolling(n2).std()
    return 100.0 + k * (m - sma) / sd.replace(0, np.nan)


def slope_4w(rs_ratio: pd.Series) -> float:
    """Δ4w = rs_ratio[t] - rs_ratio[t-4] (4 weeks) — the league momentum column + state input."""
    if len(rs_ratio) < 5:
        return 0.0
    return float(rs_ratio.iloc[-1] - rs_ratio.iloc[-5])


def infer_state(level: float, slope: float) -> str:
    """Four rotation states from RS-Ratio level + slope (PRD §9.4). Single definition so
    compute / export / web never fork the口径 (C9)."""
    if level >= 100 and slope >= 0:
        return "LEADING"
    if level >= 100:
        return "WEAKENING"
    if slope >= 0:
        return "IMPROVING"
    return "LAGGING"


def compute_rotation(con, n1: int | None = None, n2: int | None = None,
                     k: float | None = None, bucket_type: str = BUCKET_TYPE) -> dict:
    """Recompute bucket_rrg (weekly rs + rs_ratio) for every bucket of `bucket_type`.
    Reads bucket_bars + spx_daily only — universe daily_bars is never touched here
    (cross-section isolation, PRD §16). Returns counts + the params used."""
    n1 = PARAMS["n1_ema"] if n1 is None else n1
    n2 = PARAMS["n2_window"] if n2 is None else n2
    k = PARAMS["k"] if k is None else k

    spx = db.read_spx(con)
    if len(spx) == 0:
        raise RuntimeError("spx_daily is empty — run ingest first (RS needs the benchmark).")
    spx_wk = to_weekly(spx["date"], spx["close"])

    buckets = db.bucket_names(con, bucket_type)
    if not buckets:
        raise RuntimeError(
            f"bucket_bars has no {bucket_type} rows — run sector ETF ingest / fixture first."
        )

    db.clear_bucket_rrg(con)
    n_buckets = n_rows = skipped = 0
    for b in buckets:
        bars = db.read_bucket_bars(con, bucket_type, b)
        bk_wk = to_weekly(bars["date"], bars["close"])
        df = pd.DataFrame({"bucket": bk_wk, "spx": spx_wk}).dropna()
        if len(df) < n1 + n2:
            skipped += 1
            continue  # not enough common weeks to warm EMA + z-score window
        rs = 100.0 * df["bucket"] / df["spx"]
        rr = rs_ratio_series(rs, n1, n2, k)
        out = pd.DataFrame({
            "date": rs.index.strftime("%Y-%m-%d"),
            "rs": rs.to_numpy(),
            "rs_ratio": rr.to_numpy(),
        }).dropna()  # drop warm-up weeks where rs_ratio is NaN
        n_rows += db.upsert_bucket_rrg(con, bucket_type, b, list(out.itertuples(index=False, name=None)))
        n_buckets += 1

    return {"buckets": n_buckets, "rows": n_rows, "skipped": skipped,
            "params": {"basis": "weekly", "n1_ema": n1, "n2_window": n2, "k": k}}


# --- enriched league aggregates (PRD §9.4). All member-level numbers come from the
# bucket's universe MEMBERS in derived_daily / valuation_daily — the SAME source as
# Discovery / Ocean / Stock, so the league traces back (C9). Nothing here is persisted;
# export/rotation.py (M3.3) calls league_table() for the latest snapshot. ---

AT_HIGH_PROX = 0.99   # within 1% of the 252d high counts as "at 52-week high"
REL_HORIZONS = {"rel_ret_1m": 21, "rel_ret_3m": 63, "rel_ret_6m": 126}  # trading days


def _member_aggregates(con, latest_date) -> pd.DataFrame:
    """Per-sector member breadth / #at-52w-high / composite median on `latest_date`.
    Joins derived_daily (signals) to daily_bars (close, for the close>MA breadth) and
    universe (sector membership)."""
    return con.execute(
        """
        WITH m AS (
          SELECT u.sector AS bucket, d.composite,
                 CASE WHEN b.close > d.ma50  THEN 1.0 ELSE 0.0 END AS gt50,
                 CASE WHEN b.close > d.ma200 THEN 1.0 ELSE 0.0 END AS gt200,
                 CASE WHEN d.high_prox >= ? THEN 1 ELSE 0 END      AS athigh
          FROM derived_daily d
          JOIN universe u   ON u.ticker = d.ticker
          JOIN daily_bars b ON b.ticker = d.ticker AND b.date = d.date
          WHERE d.date = ?
        )
        SELECT bucket, count(*) AS member_count,
               100.0*avg(gt50)  AS breadth_ma50,
               100.0*avg(gt200) AS breadth_ma200,
               sum(athigh)      AS at_high,
               median(composite) AS composite_median
        FROM m GROUP BY bucket
        """,
        [AT_HIGH_PROX, latest_date],
    ).df()


def _agg_valuation(con) -> pd.DataFrame:
    """Per-sector aggregate EV/S = median(evs) of members on the latest valuation date.
    median is robust; a cap-weighted aggregate (Σ EV / Σ sales) is a later refinement
    (PRD §17). Reads valuation_daily.evs (same column Ocean/Valuation use, C9)."""
    return con.execute(
        """
        WITH latest AS (SELECT max(date) d FROM valuation_daily)
        SELECT u.sector AS bucket, median(v.evs) AS agg_evs
        FROM valuation_daily v
        JOIN universe u ON u.ticker = v.ticker
        WHERE v.date = (SELECT d FROM latest) AND v.evs IS NOT NULL
        GROUP BY u.sector
        """
    ).df()


def _rel_returns(con, bucket_type: str) -> pd.DataFrame:
    """Per-bucket relative return vs SPX over 1m/3m/6m from daily bucket_bars vs spx_daily:
    rel = (P_b[t]/P_b[t-N] - 1) - (P_spx[t]/P_spx[t-N] - 1). Sector-level (the ETF), not a
    member average — the league's horizon columns read off the same series as the chart."""
    spx = db.read_spx(con)
    spx_px = pd.Series(spx["close"].to_numpy(float), index=pd.to_datetime(spx["date"])).sort_index()
    recs = []
    for b in db.bucket_names(con, bucket_type):
        bars = db.read_bucket_bars(con, bucket_type, b)
        px = pd.Series(bars["close"].to_numpy(float), index=pd.to_datetime(bars["date"])).sort_index()
        sp = spx_px.reindex(px.index, method="ffill")
        row = {"bucket": b}
        for col, n in REL_HORIZONS.items():
            row[col] = (float((px.iloc[-1] / px.iloc[-1 - n] - 1) - (sp.iloc[-1] / sp.iloc[-1 - n] - 1))
                        if len(px) > n else None)
        recs.append(row)
    return pd.DataFrame(recs)


def league_table(con, bucket_type: str = BUCKET_TYPE) -> pd.DataFrame:
    """Enriched per-bucket league for Rotation (PRD §9.4), sorted by RS-Ratio. One row per
    bucket: RS-Ratio level + Δ4w + state (from bucket_rrg) PLUS member aggregates (breadth /
    #at-52w-high / composite median / agg EV-S) from the bucket's universe members (C9) PLUS
    the bucket ETF's relative return vs SPX. Member evidence cards are NOT built here —
    export filters board.json by scope=sector (DRY/C9). Returns empty if rotation未算."""
    rrg = db.read_bucket_rrg(con, bucket_type)
    if len(rrg) == 0:
        return pd.DataFrame()
    rows = []
    for b in rrg["bucket"].unique():
        sub = rrg[rrg["bucket"] == b].sort_values("date")["rs_ratio"].reset_index(drop=True)
        level = float(sub.iloc[-1])
        slope = slope_4w(sub)
        rows.append({"bucket": b, "rs_ratio": level, "slope_4w": slope,
                     "state": infer_state(level, slope)})
    league = pd.DataFrame(rows)

    latest = con.execute("SELECT max(date) FROM derived_daily").fetchone()[0]
    if latest is not None:
        league = league.merge(_member_aggregates(con, latest), on="bucket", how="left")
    if con.execute("SELECT count(*) FROM valuation_daily").fetchone()[0] > 0:
        league = league.merge(_agg_valuation(con), on="bucket", how="left")
    league = league.merge(_rel_returns(con, bucket_type), on="bucket", how="left")
    return league.sort_values("rs_ratio", ascending=False).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M3.2 rotation: bucket_rrg weekly RS-Ratio.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--n1", type=int, default=None, help=f"EMA span for M (default {PARAMS['n1_ema']})")
    ap.add_argument("--n2", type=int, default=None, help=f"SMA/std window for z-score (default {PARAMS['n2_window']})")
    ap.add_argument("--k", type=float, default=None, help=f"z-score scale (default {PARAMS['k']})")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    stats = compute_rotation(con, args.n1, args.n2, args.k)
    print(f"[rotation] buckets={stats['buckets']} rows={stats['rows']} skipped={stats['skipped']} "
          f"params={stats['params']}")

    lt = league_table(con, BUCKET_TYPE)
    if len(lt):
        latest_wk = db.read_bucket_rrg(con, BUCKET_TYPE)["date"].max()
        print(f"[rotation] latest week = {latest_wk}; enriched league by RS-Ratio:")
        show = lt.copy()
        for c in ("rs_ratio", "slope_4w", "breadth_ma50", "breadth_ma200",
                  "composite_median", "agg_evs", "rel_ret_1m", "rel_ret_3m", "rel_ret_6m"):
            if c in show:
                show[c] = show[c].astype(float).round(2)
        print(show.to_string(index=False))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
