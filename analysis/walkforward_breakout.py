"""Walk-forward / OOS check for the base→breakout engine (PRD §10.8). Does the PRODUCTION
descriptor (compute/breakout.py) carry forward edge OUT OF SAMPLE, or is it a full-sample
artifact? The descriptor has NO fitted parameters (constants frozen offline, §10.8.4), so
"walk-forward" here = a temporal holdout: rank cross-sectionally each day, take the top-decile
base→breakout candidates, and measure their forward return RELATIVE to SPY in a TEST window
that the (parameter-free) descriptor never "saw" during a TRAIN window.

Honesty (mirrors precision_ignition.py): report MEDIAN lift AND the TAIL (mean / P>+25% /
P>+50%) — the north star is catching the few multi-baggers, so the median can be ~0 while the
tail carries the edge. CAVEAT: yfinance = still-listed only → survivorship inflates BOTH the
event and base columns; LIFT (event − base) is robust to it. 2023–26 is an AI bull → high base.

Reuses the SAME engine the product ships (compute/breakout.compute_breakout) on the non-cherry-
picked 754-name habitat cache (analysis/_precision_cache.pkl, the precision_ignition.py pool).
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compute import breakout  # noqa: E402  (the PRODUCTION base→breakout engine)

CACHE = ROOT / "data" / "_precision_cache.pkl"
BENCH = "SPY"
TOP = 90.0           # candidate = brk_strength_pct cross-sectional top decile (== product gate)
FWD = 60             # forward window (trading days)
TRAIN_FRAC = 0.60    # first 60% of dates = TRAIN (descriptor is parameter-free; holdout = TEST)


def main() -> int:
    d = pickle.load(open(CACHE, "rb"))
    spy = d[BENCH].sort_values("date").reset_index(drop=True)
    spy_px = spy.set_index(pd.to_datetime(spy["date"]))["adj_close"]
    print(f"[wf] {len(d)-1} names + SPY; running the PRODUCTION compute/breakout.py per stock ...")

    frames = []
    for t, bars in d.items():
        if t == BENCH:
            continue
        b = bars.sort_values("date").reset_index(drop=True)
        if len(b) < 200:
            continue
        g = breakout.compute_breakout(b)                       # rolling, causal, per-day brk_strength
        px = b["adj_close"].astype(float).to_numpy()
        rec = pd.DataFrame({"ticker": t, "date": pd.to_datetime(b["date"]).values,
                            "brk_strength": g["brk_strength"].values, "px": px})
        sp = spy_px.reindex(rec["date"]).to_numpy()
        rec["fwd"] = (pd.Series(px).shift(-FWD) / pd.Series(px) - 1
                      - (pd.Series(sp).shift(-FWD) / pd.Series(sp) - 1)).clip(-0.95, 10.0).values
        frames.append(rec)
    L = pd.concat(frames, ignore_index=True).sort_values(["date", "ticker"]).reset_index(drop=True)

    # cross-sectional percentile of brk_strength per date (== compute/run.py brk_strength_pct)
    L["brk_pct"] = L.groupby("date")["brk_strength"].rank(pct=True) * 100
    L = L.sort_values(["ticker", "date"]).reset_index(drop=True)
    L["prev"] = L.groupby("ticker")["brk_pct"].shift(1)
    L["entry"] = (L["brk_pct"] >= TOP) & (L["prev"] < TOP)      # fresh crossing into top decile

    dates = np.sort(L["date"].unique())
    split = dates[int(len(dates) * TRAIN_FRAC)]
    L["seg"] = np.where(L["date"] < split, "TRAIN", "TEST")
    print(f"[wf] dates {pd.Timestamp(dates[0]).date()}..{pd.Timestamp(dates[-1]).date()}  "
          f"split @ {pd.Timestamp(split).date()}  (TRAIN<split, TEST>=split)\n")

    def stats(seg):
        sub = L[L["seg"] == seg]
        ev = sub.loc[sub["entry"], "fwd"].dropna()
        base = sub["fwd"].dropna()
        if len(ev) == 0 or len(base) == 0:
            return None
        return dict(n=len(ev), med_lift=ev.median() - base.median(), mean_lift=ev.mean() - base.mean(),
                    ev_p25=(ev > 0.25).mean(), base_p25=(base > 0.25).mean(),
                    ev_p50=(ev > 0.50).mean(), base_p50=(base > 0.50).mean())

    print(f"{'seg':6}{'n':>6}{'medLIFT':>9}{'meanLIFT':>10}{'ev>+25%':>9}{'base':>7}{'ev>+50%':>9}{'base':>7}")
    for seg in ("TRAIN", "TEST"):
        s = stats(seg)
        if not s:
            print(f"{seg:6}  (no events)"); continue
        print(f"{seg:6}{s['n']:>6}{s['med_lift']*100:>+8.1f}p{s['mean_lift']*100:>+9.1f}p"
              f"{s['ev_p25']*100:>8.0f}%{s['base_p25']*100:>6.0f}%{s['ev_p50']*100:>8.0f}%{s['base_p50']*100:>6.0f}%")

    print("\nread: medLIFT = event median − base median (≈0 expected — it is a lottery); the EDGE is in the")
    print("TAIL (mean / P>+25% / P>+50% vs base). OOS = TEST holds if its tail edge ~ TRAIN's (not a full-sample artifact).")
    print("CAVEAT: survivorship inflates BOTH columns; LIFT(diff) survives. In-sample-pool, single 754-name habitat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
