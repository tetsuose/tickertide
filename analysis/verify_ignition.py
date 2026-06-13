"""Historical back-look: does an `ignition` engine light up EARLIER than the
current `composite`? (One-off validation, not a product pipeline file.)

Premise (user's intent): catch SNDK/ARM/MRVL/AAOI in the first 1-2 weeks of their
multi-bagger run, not after they've already doubled. The current composite is a
trend-confirmation engine (long windows: rs 63/126, high 252, trend 63, vol 50/200)
so it lights up late. This script measures HOW late, against a from-scratch ignition
engine built only from short-window / inflection / breakout signals.

Method (transparent, in-sample TIMING test — see caveats printed at the end):
  1. Pull a real ~70-name tech/growth universe + SPY from yfinance (one batch).
  2. composite: reuse compute/signals.compute_metrics (SAME math as the product),
     then the cross-sectional rs_pct + composite exactly like compute/run.py, k=0.5.
  3. ignition: 5 short-window components (accel / squeeze-expansion / volume surge /
     breakout-reclaim / RS-line turn), each cross-sectionally ranked, averaged.
  4. For each target: detect the launch day t0 (first valid 60d-high breakout while
     price is still < 35% of its final high), then find the first day each engine
     enters the universe top decile (pctile >= 90). Report weeks-after-t0 and the
     run-up already gone by then.

This proves TIMING (when a known winner becomes visible), NOT precision (how many
top-decile names fizzle). False-positive cost of ignition is the next step.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compute import signals  # noqa: E402  (reuse the product's composite math)

TARGETS = ["ARM", "MRVL", "AAOI", "SNDK"]
BENCH = "SPY"
# ~70 real tech/growth names: a mix of strong + ordinary so the cross-sectional
# percentile has spread (not all multibaggers). Targets are inside the池.
UNIVERSE = sorted(set(TARGETS + [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "NFLX", "AVGO",
    "AMD", "QCOM", "MU", "TXN", "ADI", "NXPI", "ON", "MCHP", "MPWR", "LRCX",
    "AMAT", "KLAC", "ASML", "TSM", "INTC", "QRVO", "SWKS", "LSCC", "RMBS",
    "AMKR", "SMCI", "COHR", "LITE", "FN", "CIEN", "ANET", "WDC", "STX", "VRT",
    "DELL", "PLTR", "SNOW", "CRWD", "PANW", "DDOG", "NET", "ZS", "MDB", "NOW",
    "TEAM", "ORCL", "ADBE", "CRM", "APP", "COIN", "MSTR", "SOFI", "HOOD",
    "UBER", "ABNB", "SHOP",
]))

START = "2023-01-01"
TOP_DECILE = 90.0       # "lit" = cross-sectional percentile >= 90 (universe top 10%)
LAUNCH_HIGH_FRAC = 0.35  # t0 must be while price < 35% of the name's final high
BREAKOUT_WIN = 60       # t0 = breakout above the prior 60-day high


def fetch() -> dict[str, pd.DataFrame]:
    import pickle
    cache = ROOT / "data" / "_ign_cache.pkl"
    if cache.exists():
        print(f"[fetch] cache hit {cache.name}")
        return pickle.load(open(cache, "rb"))
    import yfinance as yf
    df = yf.download(UNIVERSE + [BENCH], start=START, auto_adjust=False,
                     progress=False, threads=True)
    close, adj, vol = df["Close"], df["Adj Close"], df["Volume"]
    out = {}
    for t in UNIVERSE + [BENCH]:
        if t not in close:
            continue
        s = pd.DataFrame({"adj_close": adj[t], "close": close[t], "volume": vol[t]}).dropna(subset=["adj_close"])
        if len(s) < 220:   # need ~1y for the long windows to warm
            continue
        s = s.reset_index().rename(columns={"Date": "date"})
        s["date"] = pd.to_datetime(s["date"])
        out[t] = s
    pickle.dump(out, open(cache, "wb"))
    print(f"[fetch] cached -> {cache.name}")
    return out


def ignition_metrics(bars: pd.DataFrame, spx: pd.DataFrame) -> pd.DataFrame:
    """5 short-window ignition components, per stock. All are SELF-relative (no
    cross-section here) — cross-sectional ranking happens in the caller."""
    df = bars.sort_values("date").reset_index(drop=True)
    px = df["adj_close"].astype(float)
    high, low, close = df.get("high", px), df.get("low", px), df["close"].astype(float)
    vol = df["volume"].fillna(0).astype(float)
    spx_al = (spx.set_index("date")["adj_close"].reindex(df["date"], method="ffill")
              .reset_index(drop=True).astype(float))

    # 1. momentum acceleration: short-window step-rate minus mid-window step-rate.
    r10 = px / px.shift(10) - 1
    r50 = px / px.shift(50) - 1
    accel = r10 / 10.0 - r50 / 50.0

    # 2. squeeze->expansion: recent true-range vs its 60d base (>1 = expanding).
    tr = (px - px.shift(1)).abs()
    expand = tr.rolling(10).mean() / tr.rolling(60).mean().replace(0, np.nan)

    # 3. volume surge vs own recent base (short, self — not 50/200).
    vsurge = vol.rolling(5).mean() / vol.rolling(60).mean().replace(0, np.nan)

    # 4. breakout / reclaim: proximity to the 60d high, gated by being above MA50.
    hi60 = px.rolling(BREAKOUT_WIN).max()
    ma50 = px.rolling(50).mean()
    breakout = (px / hi60).clip(0, 1) * (px > ma50).astype(float)

    # 5. RS-line turn: short slope of the price-relative line, and that it's rising
    #    faster than its 30d slope (inflection, not level).
    rs_line = px / spx_al
    slope10 = rs_line / rs_line.shift(10) - 1
    slope30 = rs_line / rs_line.shift(30) - 1
    rsturn = slope10 - slope30 / 3.0   # >0 => 10d pace beats the 30d pace

    return pd.DataFrame({
        "date": df["date"].dt.strftime("%Y-%m-%d"),
        "ig_accel": accel, "ig_expand": expand, "ig_vsurge": vsurge,
        "ig_breakout": breakout, "ig_rsturn": rsturn,
    })


def main() -> int:
    print(f"[fetch] yfinance {len(UNIVERSE)+1} names since {START} ...")
    data = fetch()
    if BENCH not in data:
        raise RuntimeError("benchmark SPY missing")
    spx_sig = data[BENCH][["date", "close"]].copy()          # signals.py wants 'close'
    spx_ign = data[BENCH][["date", "adj_close"]].copy()
    print(f"[fetch] usable names: {len(data)-1} + SPY")

    comp_frames, ign_frames = [], []
    for t, bars in data.items():
        if t == BENCH:
            continue
        m = signals.compute_metrics(bars, spx_sig)           # product composite inputs
        m["ticker"] = t
        comp_frames.append(m)
        g = ignition_metrics(bars, spx_ign)
        g["ticker"] = t
        ign_frames.append(g)

    cm = pd.concat(comp_frames, ignore_index=True)
    ig = pd.concat(ign_frames, ignore_index=True)

    # ---- cross-sectional composite (mirrors compute/run.py, k=0.5) ----
    w = signals.weights(0.5)
    cm["rs_pct"] = cm.groupby("date")["rs_raw"].rank(pct=True) * 100
    cm = cm.sort_values(["ticker", "date"])
    cm["rs_accel"] = cm.groupby("ticker")["rs_pct"].diff(21)
    cl = lambda s: s.clip(0, 1)
    cm["c_rs"] = cl(cm["rs_pct"] / 100)
    cm["c_high"] = cl(cm["high_prox"])
    cm["c_trend"] = cl(cm["trend_quality"])
    cm["c_vol"] = cl((cm["vol_ratio"] - 1.0) / 0.6 + 0.5)
    cm["c_accel"] = cl(cm["rs_accel"].fillna(0) / 100 + 0.5)
    cm["composite"] = 100 * (w["rs"]*cm["c_rs"] + w["high"]*cm["c_high"] +
                             w["trend"]*cm["c_trend"] + w["vol"]*cm["c_vol"] +
                             w["accel"]*cm["c_accel"])
    cm["comp_pct"] = cm.groupby("date")["composite"].rank(pct=True) * 100

    # ---- cross-sectional ignition: percentile-rank each component, then average ----
    for c in ["ig_accel", "ig_expand", "ig_vsurge", "ig_breakout", "ig_rsturn"]:
        ig[c + "_p"] = ig.groupby("date")[c].rank(pct=True)
    ig["ignition"] = 100 * ig[[c + "_p" for c in
                     ["ig_accel", "ig_expand", "ig_vsurge", "ig_breakout", "ig_rsturn"]]].mean(axis=1)
    ig["ign_pct"] = ig.groupby("date")["ignition"].rank(pct=True) * 100

    comp = cm[["ticker", "date", "comp_pct"]].copy()
    igni = ig[["ticker", "date", "ign_pct"]].copy()
    comp["date"] = pd.to_datetime(comp["date"])   # signals.py emits str dates; realign to Timestamp
    igni["date"] = pd.to_datetime(igni["date"])

    # ---- per-target timing ----
    rows, plot = [], {}
    for t in TARGETS:
        bars = data[t].sort_values("date").reset_index(drop=True)
        s = bars.set_index("date")["adj_close"]
        final_high = s.max()
        hi_prev = s.rolling(BREAKOUT_WIN, min_periods=20).max().shift(1)
        t0 = None
        for i, (d, p) in enumerate(s.items()):
            if pd.notna(hi_prev.get(d)) and p > hi_prev[d] and p < LAUNCH_HIGH_FRAC * final_high:
                fwd = s[s.index > d].head(60)
                if len(fwd) and fwd.max() > p * 1.15:
                    t0 = d
                    break
        if t0 is None:        # fallback: first day above 20% of final high
            t0 = s[s > 0.20 * final_high].index.min()
        p0 = float(s.loc[t0])

        ct = comp[comp["ticker"] == t].set_index("date")["comp_pct"]
        gt = igni[igni["ticker"] == t].set_index("date")["ign_pct"]

        def first_lit(series):
            after = series[series.index >= t0]
            hit = after[after >= TOP_DECILE]
            return hit.index.min() if len(hit) else None

        def runup_at(d):
            if d is None:
                return None
            return float(s.loc[d] / p0 - 1)

        comp_lit, ign_lit = first_lit(ct), first_lit(gt)
        rows.append({
            "ticker": t, "t0": str(t0.date()), "p0": round(p0, 2),
            "ign_lit": str(ign_lit.date()) if ign_lit is not None else None,
            "ign_wks": int((ign_lit - t0).days / 7) if ign_lit is not None else None,
            "ign_runup": runup_at(ign_lit),
            "comp_lit": str(comp_lit.date()) if comp_lit is not None else None,
            "comp_wks": int((comp_lit - t0).days / 7) if comp_lit is not None else None,
            "comp_runup": runup_at(comp_lit),
        })
        plot[t] = {
            "dates": [d.strftime("%Y-%m-%d") for d in s.index],
            "px": [round(float(x), 4) for x in s.values],
            "t0": str(t0.date()),
            "ign_lit": str(ign_lit.date()) if ign_lit is not None else None,
            "comp_lit": str(comp_lit.date()) if comp_lit is not None else None,
        }

    # ---- report ----
    print("\n================  IGNITION vs COMPOSITE — timing on known winners  ================")
    print(f"{'tk':5} {'t0(launch)':12} {'p0':>8} | {'IGN lit':11} {'wks':>4} {'run-up':>8} | "
          f"{'COMP lit':11} {'wks':>4} {'run-up':>8} | {'missed':>8}")
    for r in rows:
        ir = f"{r['ign_runup']*100:+.0f}%" if r['ign_runup'] is not None else "  —"
        cr = f"{r['comp_runup']*100:+.0f}%" if r['comp_runup'] is not None else "  —"
        miss = (f"{(r['comp_runup']-r['ign_runup'])*100:+.0f}pp"
                if r['comp_runup'] is not None and r['ign_runup'] is not None else "  —")
        print(f"{r['ticker']:5} {r['t0']:12} {r['p0']:8.2f} | "
              f"{str(r['ign_lit']):11} {str(r['ign_wks']):>4} {ir:>8} | "
              f"{str(r['comp_lit']):11} {str(r['comp_wks']):>4} {cr:>8} | {miss:>8}")
    print("\n'run-up' = price gain from t0 to the day that engine first entered the universe top decile.")
    print("'missed' = extra run-up already gone if you waited for composite instead of ignition.")
    print("\nCAVEAT: in-sample TIMING test on 4 hand-picked winners. Proves ignition surfaces a")
    print("true winner earlier — NOT that top-decile ignition names mostly win (precision needs")
    print("a full-universe false-positive pass — the next step).")

    out = ROOT / "data" / "verify_ignition_out.json"
    out.write_text(json.dumps({"rows": rows, "plot": plot}, separators=(",", ":")))
    print(f"\n[out] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
