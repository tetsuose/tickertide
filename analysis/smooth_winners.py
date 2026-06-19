"""STEP 1+2 of the 'learn-the-winner-shape' pipeline: find stocks that achieved a 6-month
SMOOTH strong uptrend (high growth + low drawdown + continuous), starting from a base, and
SAMPLE them for human K-line inspection.

Winner episode = a launch date t0 where, over the forward 126 trading days [t0, t0+126]:
  - growth:    P[t0+126]/P[t0]-1            >= GROWTH      (strong 6-month gain)
  - low DD:    max intra-window drawdown    >= -MAXDD      (shallow retracement = smooth)
  - smooth:    KER = |net move|/sum|moves|  >= KER_MIN     (efficient, continuous climb)
  - from base: trailing 60d return at t0    <= BASE_RET    ("最初靠近增长起点", not mid-run)
Dedup: keep launches >= 126d apart per ticker so each episode is distinct.

This DEFINES winners using the forward window (lookahead — fine for LABELLING; the eventual
SCREENING signal in step 5 must use only pre-t0 data). Outputs the base rate (what fraction of
all stock-days are such launches) so the precision discussion is grounded, and dumps a diverse
sample (across decades, distinct tickers) of normalized price paths [t0-60, t0+126] for a gallery.

Honest notes: survivorship (yfinance still-listed) inflates winner counts; long-history cache is
adj-close only (no OHLC) so the gallery shows the price SHAPE (log line + drawdown), which is what
'smooth high-growth low-drawdown' is about — true candlesticks need an OHLC refetch for the picks.

Run: /Users/.../.venv/bin/python analysis/smooth_winners.py [--growth 0.4] [--maxdd 0.2] [--ker 0.55] [--n 12]
Outputs: stdout summary + data/smooth_winners_sample.json (paths+meta for the gallery)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import stable_momentum as sm   # for load_prices  # noqa: E402

DATA = ROOT / "data"
SAMPLE = DATA / "smooth_winners_sample.json"
W = 126            # 6-month forward window (trading days)
PRE = 60           # pre-launch context shown in the gallery
RNG = np.random.default_rng(0)


def _ker_fwd(p: pd.Series, w: int) -> pd.Series:
    num = (p.shift(-w) - p).abs()
    den = p.diff().abs().rolling(w).sum().shift(-w)
    return num / den


def find_winners(px: pd.DataFrame, growth, maxdd, ker_min, base_ret):
    """Return DataFrame of launch episodes with metadata; also total candidate stats."""
    rows = []
    n_days_total = 0
    n_growth = 0
    for t in px.columns:
        p = px[t].dropna()
        if len(p) < PRE + W + 5:
            continue
        n_days_total += len(p)
        arr = p.to_numpy()
        idx = p.index
        fwd_ret = arr[W:] / arr[:-W] - 1.0                      # aligned to t = 0..len-W-1
        fwd_ret = np.concatenate([fwd_ret, np.full(W, np.nan)])
        ker = _ker_fwd(p, W).to_numpy()
        trail60 = (arr / np.concatenate([np.full(60, np.nan), arr[:-60]]) - 1.0)
        cand = (fwd_ret >= growth) & (ker >= ker_min) & (trail60 <= base_ret)
        cand &= np.arange(len(arr)) >= PRE
        n_growth += int(np.nansum((fwd_ret >= growth)))
        ci = np.where(cand)[0]
        # exact intra-window max drawdown only for return/smoothness candidates (cheap)
        last_launch = -10 ** 9
        for t0 in ci:
            seg = arr[t0:t0 + W + 1]
            dd = float((seg / np.maximum.accumulate(seg) - 1.0).min())
            if dd < -maxdd:
                continue
            if t0 - last_launch < W:                            # dedup overlapping episodes
                continue
            last_launch = t0
            rows.append({"ticker": t, "t0_i": int(t0), "date": str(idx[t0].date()),
                         "ret126": float(fwd_ret[t0]), "maxdd": dd, "ker": float(ker[t0]),
                         "trail60": float(trail60[t0]), "year": int(idx[t0].year)})
    return pd.DataFrame(rows), n_days_total, n_growth


def sample_diverse(winners: pd.DataFrame, n: int) -> pd.DataFrame:
    """Sample n episodes spread across decades and distinct tickers."""
    if len(winners) <= n:
        return winners
    winners = winners.copy()
    winners["decade"] = (winners["year"] // 10) * 10
    picks = []
    decades = sorted(winners["decade"].unique())
    per = max(1, n // len(decades))
    used_tickers = set()
    for dec in decades:
        pool = winners[(winners["decade"] == dec) & (~winners["ticker"].isin(used_tickers))]
        k = min(per, len(pool))
        if k:
            s = pool.sample(k, random_state=int(dec))
            picks.append(s); used_tickers.update(s["ticker"])
    out = pd.concat(picks) if picks else winners.sample(n, random_state=0)
    if len(out) < n:
        extra = winners[~winners.index.isin(out.index)].sample(n - len(out), random_state=1)
        out = pd.concat([out, extra])
    return out.sort_values("date").head(n)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--growth", type=float, default=0.40)
    ap.add_argument("--maxdd", type=float, default=0.20)
    ap.add_argument("--ker", type=float, default=0.55)
    ap.add_argument("--base-ret", type=float, default=0.15)
    ap.add_argument("--n", type=int, default=12)
    a = ap.parse_args(argv)
    px = sm.load_prices(False)
    print(f"[panel] {px.shape[1]} names  {px.index.min().date()}..{px.index.max().date()}  rows={len(px)}")
    print(f"[def] winner = fwd126 ret>=+{a.growth:.0%}, intra-window maxDD>=-{a.maxdd:.0%}, "
          f"KER>={a.ker}, trailing-60d<=+{a.base_ret:.0%} (from a base), episodes >=126d apart")
    W_, n_days, n_growth = find_winners(px, a.growth, a.maxdd, a.ker, a.base_ret)
    print(f"\n[found] {len(W_)} distinct smooth-winner launch episodes across {W_['ticker'].nunique()} tickers")
    print(f"[base rate] launches per stock-day ≈ {len(W_)/max(1,n_days):.4%}  "
          f"(of days that merely hit +{a.growth:.0%}/6mo: {len(W_)/max(1,n_growth):.1%} also passed the DD+smooth+base gates)")
    by_dec = (W_["year"]//10*10).value_counts().sort_index()
    print("[by decade]", {int(k): int(v) for k, v in by_dec.items()})
    print(f"[median episode] ret126={W_['ret126'].median():.0%}  maxDD={W_['maxdd'].median():.0%}  KER={W_['ker'].median():.2f}")

    samp = sample_diverse(W_, a.n)
    charts = []
    for _, r in samp.iterrows():
        p = px[r["ticker"]].dropna()
        t0 = int(r["t0_i"])
        lo, hi = max(0, t0 - PRE), min(len(p), t0 + W + 1)
        seg = p.iloc[lo:hi]
        base_px = float(p.iloc[t0])
        norm = (seg / base_px).round(4).tolist()                 # price relative to launch=1.0
        charts.append({"ticker": r["ticker"], "date": r["date"], "year": int(r["year"]),
                       "ret126": round(r["ret126"], 3), "maxdd": round(r["maxdd"], 3),
                       "ker": round(r["ker"], 2), "trail60": round(r["trail60"], 3),
                       "launch_idx": t0 - lo, "path": norm})
    DATA.mkdir(exist_ok=True)
    json.dump({"def": {"growth": a.growth, "maxdd": a.maxdd, "ker": a.ker, "base_ret": a.base_ret, "W": W, "PRE": PRE},
               "n_found": len(W_), "sample": charts}, open(SAMPLE, "w"), indent=1)
    print(f"\n[sample] {len(charts)} episodes -> {SAMPLE}")
    for c in charts:
        print(f"  {c['ticker']:6} {c['date']}  ret126={c['ret126']:+.0%}  maxDD={c['maxdd']:+.0%}  KER={c['ker']:.2f}  trail60={c['trail60']:+.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
