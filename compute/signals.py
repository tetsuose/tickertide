"""Per-stock signal math (M0.3). Math spec: PRD §10.

Division of labor (PRD §5.2, §17): pandas does the per-stock TIME-SERIES work it
is good at (rolling, ewm, pct_change); DuckDB does the CROSS-SECTIONAL percentile
+ composite in compute/run.py. This split can migrate fully into DuckDB SQL later.

The composite is `100 · Σ wᵢ·componentᵢ` with components ∈ [0,1] (PRD §10.6). The
`early⟷reliable` knob k∈[0,1] only re-weights — it never drops a component, and
the weights sum to 1 for every k (their slopes cancel), so no renormalization.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# EWMAC horizon pairs (fast, slow) — multi-horizon per PRD §10.1.
EWMAC_PAIRS = {"ewmac_fast": (16, 64), "ewmac_slow": (32, 128)}
KER_WINDOW = 63          # Kaufman efficiency ratio lookback
RS_WIN_SHORT = 63        # ~3 months
RS_WIN_LONG = 126        # ~6 months
HIGH_WIN = 252           # 52-week high proximity


def weights(k: float) -> dict[str, float]:
    """early⟷reliable weight curve (PRD §10.6). k=0 reliable, k=1 early.

    Σ = 1 for all k: slopes (+.03 -.24 -.10 -.04 +.35) sum to 0.
    """
    k = max(0.0, min(1.0, float(k)))
    return {
        "rs":    0.20 + 0.03 * k,
        "high":  0.34 - 0.24 * k,
        "trend": 0.22 - 0.10 * k,
        "vol":   0.14 - 0.04 * k,
        "accel": 0.10 + 0.35 * k,
    }


def _ewmac(px: pd.Series, fast: int, slow: int) -> pd.Series:
    """Vol-normalized EWMAC: (EMA_fast - EMA_slow) / EWMA-std of price changes."""
    ef = px.ewm(span=fast, adjust=False).mean()
    es = px.ewm(span=slow, adjust=False).mean()
    sigma = px.diff().ewm(span=slow, adjust=False).std()
    return (ef - es) / sigma.replace(0, np.nan)


def compute_metrics(bars: pd.DataFrame, spx: pd.DataFrame) -> pd.DataFrame:
    """Per-stock daily metrics from one ticker's bars + the benchmark.

    Returns a frame keyed by date (str) with the columns compute/run.py expects.
    Uses adj_close as the price series (split/div adjusted) for return-based math.
    """
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    px = df["adj_close"].astype(float)
    vol = df["volume"].fillna(0).astype(float)

    # Benchmark close aligned to this ticker's trading dates (forward-fill).
    s = spx.copy()
    s["date"] = pd.to_datetime(s["date"])
    spx_close = s.sort_values("date").set_index("date")["close"].astype(float)
    spx_al = spx_close.reindex(df["date"], method="ffill").reset_index(drop=True)

    ret_63 = px / px.shift(RS_WIN_SHORT) - 1
    ret_126 = px / px.shift(RS_WIN_LONG) - 1
    spx_63 = spx_al / spx_al.shift(RS_WIN_SHORT) - 1
    spx_126 = spx_al / spx_al.shift(RS_WIN_LONG) - 1
    rs_raw = (ret_63 - spx_63) + (ret_126 - spx_126)

    ma50 = px.rolling(50).mean()
    ma150 = px.rolling(150).mean()
    ma200 = px.rolling(200).mean()
    high_prox = px / px.rolling(HIGH_WIN, min_periods=20).max()

    # KER trend quality ∈ [0,1].
    direction = (px - px.shift(KER_WINDOW)).abs()
    volatility = px.diff().abs().rolling(KER_WINDOW).sum()
    trend_quality = (direction / volatility.replace(0, np.nan)).clip(0, 1)

    vol_ratio = vol.rolling(50).mean() / vol.rolling(200).mean().replace(0, np.nan)
    up = px > px.shift(1)
    up_vol = vol.where(up, 0.0).rolling(50).sum()
    down_vol = vol.where(~up, 0.0).rolling(50).sum()
    ud_vol_ratio = up_vol / down_vol.replace(0, np.nan)

    out = pd.DataFrame({
        "date": df["date"].dt.strftime("%Y-%m-%d"),
        "ret_63": ret_63, "ret_126": ret_126, "rs_raw": rs_raw,
        "high_prox": high_prox, "ma50": ma50, "ma150": ma150, "ma200": ma200,
        "trend_quality": trend_quality, "vol_ratio": vol_ratio, "ud_vol_ratio": ud_vol_ratio,
    })
    for col, (fast, slow) in EWMAC_PAIRS.items():
        out[col] = _ewmac(px, fast, slow)
    return out
