"""Per-stock steady-riser metrics (the core screen). Math spec: PRD §10.8.

The single core screen after the 2026-07-02 spine pivot II (base→breakout retired,
§10.9). The product semantics: mathematize "scan thousands of K-line charts every day
for names that kept rising over the last 1-2 weeks with shallow pullbacks". Hard
requirements (user-decided): SIMPLE, hard to get wrong, and CHART-VERIFIABLE — every
number here can be counted off the candles by a human in seconds. It claims NO forward
return (exp 10: picks ≈ universe median); it is a recall/efficiency tool and the
precision stage is the user reading fundamentals downstream.

Metrics per (ticker, date), primary window W=10 trading days (δ = daily log return):
  rise_net5/net10/net20  net rise close_t/close_{t-k} - 1 (k=5/10/20; 10 = "两周" main)
  rise_up10              fraction of up days in the last 10 (count the green candles)
  rise_ddw10             max drawdown inside the last-10d window (11 closes) from the
                         window's running peak (<= 0; the "回撤少" direct read)
  rise_ker10             path efficiency |Σδ|/Σ|δ| in [0,1] (1 = straight line)

Division of labor mirrors the previous engines: pandas/numpy does the per-stock time
series here; the CROSS-SECTIONAL work (rise_net10_pct percentile, the gate
`up10>=0.6 AND net10>0`, the net10 top-N candidate flag and the on-list streak) runs in
DuckDB SQL in compute/run.py so every lens reads one row (C9). `rise_candidate` is the
SINGLE source of truth — export/web never re-derive it (the #92-#94 rounding lesson).

Smoothness (ker/ddw) is NEVER a hard gate (PRD §10.8.3): the strict-smoothness gate
missed SNDK until d66 in exp 10 — real rockets are not smooth early. They are evidence
columns for the user to tighten in the UI. Constants are UX constants, not fitted:
W=10 ("一两周"), gate up>=6/10, TOP_N=50. Validation: analysis/steady_riser.py (exp 10).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# UX constants (PRD §10.8.5) — product semantics, NOT fitted / NOT user-tunable.
W = 10            # primary window: "the last 1-2 weeks"
W_SHORT = 5       # short reference net-rise column
W_LONG = 20       # long reference net-rise column
UP_MIN = 0.6      # gate: at least 6 of 10 days up
TOP_N = 50        # candidate list size (net10-sorted among gate passers)

FEATURES = ["rise_net5", "rise_net10", "rise_net20", "rise_up10", "rise_ddw10", "rise_ker10"]


def compute_riser(bars: pd.DataFrame, _spx: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-stock daily steady-riser metrics from one ticker's bars.

    Returns a frame keyed by date (str %Y-%m-%d, matching signals.py) with the raw
    per-stock metrics. The cross-sectional percentile / gate / candidate / streak are
    added by the caller (compute/run.py). `_spx` is unused (the screen is self-relative
    on the name's own closes) — kept for a uniform engine signature.
    """
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    P = df["adj_close"].astype(float)
    dates = df["date"].dt.strftime("%Y-%m-%d").to_numpy()
    n = len(P)

    dL = np.log(P.clip(lower=1e-9)).diff()          # daily log returns (NaN at 0)

    net5 = P / P.shift(W_SHORT) - 1.0
    net10 = P / P.shift(W) - 1.0
    net20 = P / P.shift(W_LONG) - 1.0
    up10 = (dL > 0).rolling(W).sum() / float(W)     # exact count/10 (NaN-leading handled below)
    ker10 = (dL.rolling(W).sum().abs() / dL.abs().rolling(W).sum()).clip(0.0, 1.0)

    # in-window max drawdown over the last W days (W+1 closes): min over the window of
    # (price / running-max-within-window) - 1. O(n·W) — trivially fast at W=10.
    arr = P.to_numpy()
    ddw = np.full(n, np.nan)
    for t in range(W, n):
        seg = arr[t - W:t + 1]
        run = np.maximum.accumulate(seg)
        ddw[t] = float((seg / run - 1.0).min())

    # first W rows have no full window: leave metrics NaN there (rolling already does;
    # blank up10 too — its window would otherwise count the day-0 NaN return as a down
    # day, and a partial window must never sneak a name through the gate).
    up10.iloc[:W] = np.nan

    res = pd.DataFrame({"date": dates})
    res["rise_net5"] = net5.to_numpy()
    res["rise_net10"] = net10.to_numpy()
    res["rise_net20"] = net20.to_numpy()
    res["rise_up10"] = up10.to_numpy()
    res["rise_ddw10"] = ddw
    res["rise_ker10"] = ker10.to_numpy()
    return res
