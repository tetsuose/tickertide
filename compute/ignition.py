"""Per-stock ignition signal math (M7.1). Math spec: PRD §10.8.1.

The SECOND engine (ignition = early discovery), parallel to composite (signals.py,
confirmation). It measures a DIFFERENT physical quantity — acceleration / inflection
/ breakout, all SHORT-window — so a name lights up months before composite's long
windows confirm it (PRD §10.8: composite lags emerging leaders by 14-45 weeks).

Same division of labor as signals.py (PRD §5.2): pandas does the per-stock
TIME-SERIES work here (rolling, pct_change, slopes); the CROSS-SECTIONAL
percentile-rank of each component + the equal-weight average + `ign_pct` +
persistence all run in DuckDB SQL in compute/run.py. Both engines read the SAME
per-stock bars (C9) and land in the SAME derived_daily row, so every lens stays
data-consistent.

The 5 components are all SELF-relative (no cross-section here): each is ranked
cross-sectionally to [0,1] by the caller, then averaged. `early⟷reliable` does NOT
touch ignition (PRD §10.8/P7) — that knob only re-weights composite; ignition's
precision comes from persistence (consecutive days in the top decile), not weights.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Short-window horizons (PRD §10.8.1) — deliberately short vs signals.py's
# 63/126/252 long windows, so ignition catches the inflection, not the level.
ACCEL_FAST = 10          # momentum acceleration: fast step-rate window
ACCEL_SLOW = 50          # momentum acceleration: mid step-rate window
EXPAND_FAST = 10         # squeeze->expansion: recent true-range window
EXPAND_SLOW = 60         # squeeze->expansion: base true-range window
VSURGE_FAST = 5          # volume surge: recent volume window (self, not 50/200)
VSURGE_SLOW = 60         # volume surge: own recent base
BREAKOUT_WIN = 60        # breakout/reclaim: prior-high window (bottom-up, not 52w)
MA_RECLAIM = 50          # breakout gate: must be above MA50
RSTURN_FAST = 10         # RS-line turn: short slope window
RSTURN_SLOW = 30         # RS-line turn: reference slope window

IGNITION_COMPONENTS = ["ig_accel", "ig_expand", "ig_vsurge", "ig_breakout", "ig_rsturn"]


def compute_ignition(bars: pd.DataFrame, spx: pd.DataFrame) -> pd.DataFrame:
    """Per-stock daily ignition components from one ticker's bars + the benchmark.

    Returns a frame keyed by date (str, %Y-%m-%d, matching signals.compute_metrics)
    with the 5 raw self-relative components. The benchmark `spx` carries a `close`
    column (spx_daily, adj_close basis per db.upsert_spx); forward-filled onto this
    ticker's trading dates so the RS-line aligns. Uses adj_close as the price series.
    """
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    px = df["adj_close"].astype(float)
    vol = df["volume"].fillna(0).astype(float)

    # Benchmark close aligned to this ticker's trading dates (forward-fill), same
    # pattern as signals.compute_metrics so both engines share one benchmark frame.
    s = spx.copy()
    s["date"] = pd.to_datetime(s["date"])
    spx_close = s.sort_values("date").set_index("date")["close"].astype(float)
    spx_al = spx_close.reindex(df["date"], method="ffill").reset_index(drop=True)

    # 1. momentum acceleration: short-window step-rate minus mid-window step-rate.
    #    >0 = slope is STEEPENING (not just high). PRD §10.8.1.1.
    r_fast = px / px.shift(ACCEL_FAST) - 1
    r_slow = px / px.shift(ACCEL_SLOW) - 1
    accel = r_fast / ACCEL_FAST - r_slow / ACCEL_SLOW

    # 2. squeeze->expansion: recent true-range vs its base (>1 = range expanding
    #    after a low-vol base, i.e. a breakout). PRD §10.8.1.2.
    tr = (px - px.shift(1)).abs()
    expand = tr.rolling(EXPAND_FAST).mean() / tr.rolling(EXPAND_SLOW).mean().replace(0, np.nan)

    # 3. volume surge vs own recent base (SHORT/self, NOT the 50/200 slow vol_ratio
    #    composite uses). PRD §10.8.1.3.
    vsurge = vol.rolling(VSURGE_FAST).mean() / vol.rolling(VSURGE_SLOW).mean().replace(0, np.nan)

    # 4. breakout / reclaim: proximity to the 60d high, gated by being above MA50
    #    (lifting off a bottom, NOT nearing a 52w high). PRD §10.8.1.4.
    hi60 = px.rolling(BREAKOUT_WIN).max()
    ma50 = px.rolling(MA_RECLAIM).mean()
    breakout = (px / hi60).clip(0, 1) * (px > ma50).astype(float)

    # 5. RS-line turn: short slope of the price-relative line rising faster than its
    #    reference slope (INFLECTION, not RS already high). PRD §10.8.1.5.
    rs_line = px / spx_al.replace(0, np.nan)
    slope_fast = rs_line / rs_line.shift(RSTURN_FAST) - 1
    slope_slow = rs_line / rs_line.shift(RSTURN_SLOW) - 1
    rsturn = slope_fast - slope_slow / 3.0

    return pd.DataFrame({
        "date": df["date"].dt.strftime("%Y-%m-%d"),
        "ig_accel": accel, "ig_expand": expand, "ig_vsurge": vsurge,
        "ig_breakout": breakout, "ig_rsturn": rsturn,
    })
