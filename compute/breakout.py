"""Per-stock base→breakout engine (the core detection engine). Math spec: PRD §10.8.

The single core engine after the 2026-06-16 spine pivot (ignition + composite retired).
North star: catch the anomaly at the EARLY stage of a multi-bagger's long rise. The
shape that serves it is "long flat base → steep breakout": on LOG price, estimate a
single changepoint τ by a 2-segment piecewise-linear (OLS) fit — τ is ESTIMATED (scan
legal split points for min total SSE), NOT a fixed base/breakout window. From it we
derive dimensionless features (÷ daily-return σ) and a recall-first STRENGTH.

Causal & rolling: at each trading day `e` the descriptor uses ONLY the trailing window
ending at `e` (lookback H), and τ is required RECENT (within a recency band before `e`),
so every (ticker, date) row reflects "is this name breaking out OUT OF a long base AS OF
this day". This mirrors compute/ignition.py's division of labor: pandas/numpy does the
per-stock time-series here; the CROSS-SECTIONAL percentile of `brk_strength` →
`brk_strength_pct` runs in DuckDB SQL in compute/run.py (so every lens is C9-consistent).

Recall-first by design (PRD §10.8.3): STRENGTH ranks candidates, false positives are
expected, fundamentals/financials are the downstream precision stage. No tunable knob —
the constants below are frozen offline (PRD §10.8.4 / §17). Reference prototype:
analysis/ (base_breakout / live_screen / full_screen, validated on the full US habitat).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Frozen offline constants (PRD §10.8.4 / §17) — NOT user-tunable knobs.
H = 504          # lookback window (~2y of trading days)
MINSEG = 40      # min length of the base segment (bars)
REC_LO = 15      # breakout segment must be >= this many bars (τ at most this recent)
REC_HI = 252     # τ at most this old (~1y) — else it is not a "current" breakout
SLACK_FLAT = 1.5  # flat-base weight in the strength combination: exp(-SLACK_FLAT*|base_slope/σ|)
CLEAR_MAX = 2.5   # ceiling-clearance upper guard (already-ran / degenerate names out)
BRK_SLOPE_CAP = 0.6   # brk_slope/σ upper guard (gap / tiny-base degeneracy)
BASE_PX_MIN = 3.0     # base median price floor ($) — drop penny / post-split / SPAC artifacts
BASE_FLAT_MAX = 0.08  # |base_slope/σ| gate — base must be ~flat (not already trending)
VCP_FWD = 20     # bars after τ used for breakout-side ATR / volume surge

FEATURES = ["brk_base_slope", "brk_brk_slope", "brk_drift_step", "brk_fit_gain",
            "brk_clearance", "brk_vcp", "brk_vsurge", "brk_strength"]


def _prefix(a: np.ndarray):
    """Cumulative sum with a leading 0 → O(1) segment sums via c[b]-c[a]."""
    return np.concatenate([[0.0], np.cumsum(a)])


def _seg(cy, cyy, cx, cxx, cxy, a, b):
    """OLS line fit over half-open [a,b) (a,b scalar or ndarray) → (SSE, slope).

    Uses the centered normal-equation form; degenerate segments → NaN (filtered out)."""
    n = b - a
    Sx = cx[b] - cx[a]; Sy = cy[b] - cy[a]
    Sxx = cxx[b] - cxx[a]; Sxy = cxy[b] - cxy[a]; Syy = cyy[b] - cyy[a]
    Sxxc = Sxx - Sx * Sx / n
    Sxyc = Sxy - Sx * Sy / n
    Syyc = Syy - Sy * Sy / n
    Sxxc = np.where(np.abs(Sxxc) < 1e-12, np.nan, Sxxc)
    return Syyc - Sxyc * Sxyc / Sxxc, Sxyc / Sxxc


def compute_breakout(bars: pd.DataFrame, _spx: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-stock daily base→breakout features from one ticker's bars.

    Returns a frame keyed by date (str %Y-%m-%d, matching signals/ignition) with the raw
    per-stock features + `brk_strength` and the estimated `brk_tau_date`. `brk_strength_pct`
    (cross-sectional) is added by the caller (compute/run.py). `_spx` is unused (the shape
    is self-relative on the name's own log price) — kept for a uniform engine signature.
    """
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    P = df["adj_close"].astype(float).to_numpy()
    V = df["volume"].fillna(0).astype(float).to_numpy()
    dates = df["date"].dt.strftime("%Y-%m-%d").to_numpy()
    n = len(P)

    out = {c: np.full(n, np.nan) for c in FEATURES}
    tau_date = np.array([None] * n, dtype=object)

    if n >= MINSEG + REC_LO + 5:
        L = np.log(np.maximum(P, 1e-9))
        idx = np.arange(n, dtype=float)
        cy, cyy = _prefix(L), _prefix(L * L)
        cx, cxx, cxy = _prefix(idx), _prefix(idx * idx), _prefix(idx * L)
        dL = np.diff(L, prepend=L[0])              # daily log returns (dL[0]=0)
        cr, crr = _prefix(dL), _prefix(dL * dL)    # for trailing σ
        atr = np.abs(dL)                           # bar-level true range (log)

        for e in range(MINSEG + REC_LO, n):
            ws = max(0, e - H + 1)
            lo = max(ws + MINSEG, e - REC_HI + 1)
            hi = e + 1 - REC_LO                     # seg2 = [τ, e+1) has >= REC_LO bars
            if hi <= lo:
                continue
            taus = np.arange(lo, hi)
            # trailing-window daily-return σ (window (ws, e])
            m = e - ws
            mu = (cr[e + 1] - cr[ws + 1]) / m
            var = (crr[e + 1] - crr[ws + 1]) / m - mu * mu
            sig = float(np.sqrt(var)) + 1e-9
            # 2-segment fit over all candidate τ (vectorized): seg1=[ws,τ), seg2=[τ,e+1)
            sse1, sl1 = _seg(cy, cyy, cx, cxx, cxy, np.full_like(taus, ws), taus)
            sse2, sl2 = _seg(cy, cyy, cx, cxx, cxy, taus, np.full_like(taus, e + 1))
            tot = sse1 + sse2
            if np.all(np.isnan(tot)):
                continue
            j = int(np.nanargmin(tot))
            tau = int(taus[j]); s1 = sl1[j]; s2 = sl2[j]
            sse_line = float(_seg(cy, cyy, cx, cxx, cxy, np.array([ws]), np.array([e + 1]))[0][0])
            fit = 1.0 - tot[j] / sse_line if sse_line > 0 else 0.0
            base_slope = s1 / sig
            brk_slope = s2 / sig
            drift = (s2 - s1) / sig
            ceiling = float(np.max(P[ws:tau]))            # base-segment high (indices ws..tau-1)
            clearance = P[e] / ceiling - 1.0 if ceiling > 0 else np.nan
            base_atr = atr[ws + 1:tau].mean() if tau - (ws + 1) > 0 else np.nan
            fwd = atr[tau:min(n, tau + VCP_FWD)]
            vcp = (fwd.mean() / base_atr) if (base_atr and base_atr > 0 and len(fwd)) else np.nan
            base_vol = V[ws:tau].mean() if tau - ws > 0 else np.nan
            fwd_vol = V[tau:min(n, tau + VCP_FWD)]
            vsurge = (fwd_vol.mean() / base_vol) if (base_vol and base_vol > 0 and len(fwd_vol)) else np.nan
            base_px = float(np.median(P[ws:tau]))

            # recall-first STRENGTH with offline-frozen degeneracy guards (PRD §10.8.4).
            ok = (np.isfinite(clearance) and 0.0 < clearance < CLEAR_MAX and drift > 0
                  and brk_slope < BRK_SLOPE_CAP and base_px > BASE_PX_MIN
                  and abs(base_slope) < BASE_FLAT_MAX)
            strength = (fit * max(0.0, drift) * np.exp(-SLACK_FLAT * abs(base_slope))) if ok else 0.0

            out["brk_base_slope"][e] = base_slope
            out["brk_brk_slope"][e] = brk_slope
            out["brk_drift_step"][e] = drift
            out["brk_fit_gain"][e] = fit
            out["brk_clearance"][e] = clearance
            out["brk_vcp"][e] = vcp
            out["brk_vsurge"][e] = vsurge
            out["brk_strength"][e] = strength
            tau_date[e] = dates[tau]

    res = pd.DataFrame({"date": dates})
    res["brk_tau_date"] = tau_date
    for c in FEATURES:
        res[c] = out[c]
    return res
