"""exp 10 — "steady riser" screen: can a SIMPLE, chart-verifiable rule replace the engine?

User's refactor spec (2026-07-02): the algorithm should be simple, hard to get wrong, and
verifiable by eye (it must MATCH what a human sees scanning K-line charts — it does NOT
claim to predict returns). Goal: from ~3000 stocks, surface the ones that kept rising over
the last 1-2 weeks with shallow pullbacks — i.e. mathematize the daily chart scan. Picks
that later decline are acceptable (recall tool feeding human fundamental review).

Metrics per stock per day, window W=10 trading days — every number readable off the chart:
  net10  = close_t / close_{t-10} - 1                (net rise over ~2 weeks)
  up10   = fraction of up days in the window         (count the green candles)
  ddw10  = max intra-window drawdown from the window's running peak (negative)
  ker10  = |sum(log ret)| / sum(|log ret|)           (path efficiency: 1 = straight line)

Screen variants (gate + sort), compared on 4 questions:
  V0 net alone (涨跌榜 baseline)      — junk magnet per exp 2 (one-day gap spikes)
  V1 strict gate  ker>=.6 & ddw>=-5%  — the "obvious" smoothness gate
  V2 net*ker product                  — soft smoothness penalty
  V3 up10>=0.6, sort net              — "at least 6 of 10 days up", most chart-intuitive
  V4 loose gate   ker>=.5 & ddw>=-8%  — junk floor between V1 and V3

  (Q1) recall+timing: do known big runs (SNDK/SOXL/ARM/MRVL/AAOI/CRDO/SITM) enter the
       top-50 within the FIRST 1-2 WEEKS of their run?
  (Q2) list quality: are picks visually smooth risers (median ker/ddw/one-day-spike share)?
  (Q3) usability: day-to-day Jaccard + gate size + time-on-list streaks.
  (Q4) honesty: forward 21d return of picks vs universe — we CLAIM none (exp 1-9 meta).

VERDICT (2026-07-02, ~1030 real names >= $2B, 3y daily):
  V3 wins. All 7 exemplars enter top-50 within d0-d10 of their trough (SNDK d0/d2-equal,
  SITM d9); strict smoothness V1 misses SNDK until d66 (+155%) — real rockets are often
  NOT smooth early (SNDK early ker .25-.52, ddw -11%): smoothness as a HARD gate loses
  the biggest fish; as a SORT KEY or display column it is fine. Junk reduction vs V0 is
  modest (1d-spike share 48% vs 52%) -> expose up10/ddw10/ker10 as evidence columns and
  let the user tighten, don't hard-code. Forward 21d picks +1.4% vs universe +1.1% = no
  predictive claim, consistent with the exp 1-9 meta-conclusion (recall tool, not alpha).

Cross-section: real Nasdaq-screener universe (same source as ingest), mktcap >= $2B
sampled every-other + exemplars, 3y daily bars via batch yfinance (cache: data/*.pkl).
Run from repo root: .venv/bin/python analysis/steady_riser.py
"""
from __future__ import annotations
import sys, pickle
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
CACHE = DATA / "steady_riser_bars.pkl"
EXEMPLARS = ["SNDK", "SOXL", "ARM", "MRVL", "AAOI", "CRDO", "SITM"]
W = 10
TOPN = 50


def load_bars() -> pd.DataFrame:
    if CACHE.exists():
        return pickle.load(open(CACHE, "rb"))
    from ingest.nasdaq import fetch_universe
    import yfinance as yf
    uni = fetch_universe()
    rows = [r for r in uni if (r.get("mktcap") or 0) >= 2e9]
    rows.sort(key=lambda r: -(r.get("mktcap") or 0))
    tickers = [r["ticker"] for r in rows[::2]]  # every other -> ~half, spans the cap range
    tickers = list(dict.fromkeys(tickers + EXEMPLARS))
    print(f"[universe] screener>=2B sampled {len(tickers)} tickers (+exemplars)")
    px = yf.download(tickers, period="3y", interval="1d", auto_adjust=True,
                     progress=False, threads=True)["Close"]
    px = px.dropna(axis=1, thresh=int(len(px) * 0.5))
    px.index = pd.DatetimeIndex(px.index).tz_localize(None)
    DATA.mkdir(exist_ok=True)
    pickle.dump(px, open(CACHE, "wb"))
    print(f"[bars] {px.shape[1]} tickers x {len(px)} days cached")
    return px


def metrics(px: pd.DataFrame):
    lr = np.log(px).diff()
    net = px / px.shift(W) - 1.0
    ker = (lr.rolling(W).sum().abs() / lr.abs().rolling(W).sum()).clip(0, 1)
    up = (lr > 0).rolling(W).mean()
    ddw = pd.DataFrame(np.nan, index=px.index, columns=px.columns)
    arr = px.to_numpy()
    for t in range(W, len(px)):
        seg = arr[t - W:t + 1]
        run = np.maximum.accumulate(seg, axis=0)
        ddw.iloc[t] = (seg / run - 1.0).min(axis=0)
    return net, ker, up, ddw


def ranks(net, ker, up, ddw):
    v0 = net.rank(axis=1, ascending=False)
    v1 = net.where((ker >= 0.6) & (ddw >= -0.05) & (net > 0)).rank(axis=1, ascending=False)
    v2 = (net * ker).where(net > 0).rank(axis=1, ascending=False)
    v3 = net.where((up >= 0.6) & (net > 0)).rank(axis=1, ascending=False)
    v4 = net.where((ker >= 0.5) & (ddw >= -0.08) & (net > 0)).rank(axis=1, ascending=False)
    return {"V0_net(涨跌榜)": v0, "V1_strictgate": v1, "V2_net*ker": v2,
            "V3_up6of10+net": v3, "V4_loosegate": v4}


def find_run(s: pd.Series):
    """Biggest min->max run: global max, then trough = min in the ~9 months before it."""
    s = s.dropna()
    peak_i = s.idxmax()
    pre = s.loc[:peak_i].iloc[-189:] if len(s.loc[:peak_i]) > 189 else s.loc[:peak_i]
    trough_i = pre.idxmin()
    return trough_i, peak_i, float(s[peak_i] / s[trough_i] - 1)


def main():
    px = load_bars()
    missing = [t for t in EXEMPLARS if t not in px.columns]
    if missing:  # e.g. SNDK relisted 2025-02 -> fails the 50% coverage threshold; fetch alone
        import yfinance as yf
        extra = yf.download(missing, period="3y", interval="1d", auto_adjust=True,
                            progress=False)["Close"]
        if isinstance(extra, pd.Series):
            extra = extra.to_frame(missing[0])
        extra.index = pd.DatetimeIndex(extra.index).tz_localize(None)
        px = px.join(extra.dropna(axis=1, how="all"), how="left")
        print(f"[exemplars] individually fetched: {list(extra.columns)}")
    have = [t for t in EXEMPLARS if t in px.columns]
    print(f"[exemplars] present: {have}  missing: {[t for t in EXEMPLARS if t not in px.columns]}")
    net, ker, up, ddw = metrics(px)
    variants = ranks(net, ker, up, ddw)

    # diagnostic: why does a strict smoothness gate miss SNDK's early run?
    if "SNDK" in px.columns:
        trough_i, _, _ = find_run(px["SNDK"])
        win = slice(trough_i, trough_i + pd.Timedelta(days=21))
        d = pd.DataFrame({"net10": net["SNDK"][win], "ker10": ker["SNDK"][win],
                          "up10": up["SNDK"][win], "ddw10": ddw["SNDK"][win]}).dropna()
        print("\n[diag] SNDK first ~15 trading days after trough (rockets are NOT smooth early):")
        print(d.round(2).to_string())

    print(f"\n=== (Q1) known runs: first day IN TOP-{TOPN} after trough (want: <=10 trading days) ===")
    print(f"  {'ticker':7}{'trough':>11}{'peak':>11}{'run':>7} | " +
          " | ".join(k.split('_')[0] for k in variants))
    for t in have:
        trough_i, peak_i, gain = find_run(px[t])
        cells = []
        for k, rk in variants.items():
            r = rk[t].loc[trough_i:peak_i]
            hit = r[r <= TOPN]
            if len(hit) == 0:
                cells.append("never")
            else:
                d0 = hit.index[0]
                day = int(px[t].loc[trough_i:d0].shape[0]) - 1
                gained = float(px[t][d0] / px[t][trough_i] - 1)
                cells.append(f"d{day:>3} {gained*100:+5.0f}%")
        print(f"  {t:7}{str(trough_i.date()):>11}{str(peak_i.date()):>11}{gain*100:>+6.0f}% | " + " | ".join(cells))

    print(f"\n=== (Q2) median pick quality across all days (top-{TOPN}) ===")
    print(f"  {'variant':16}{'med net10':>10}{'med ker':>9}{'med up%':>9}{'med ddw':>9}{'1d-spike%':>11}")
    lr = np.log(px).diff()
    spike = lr.rolling(W).max() / lr.rolling(W).sum().abs().clip(lower=1e-9)
    for k, rk in variants.items():
        m = rk <= TOPN
        print(f"  {k:16}{net[m].stack().median()*100:>+9.1f}%{ker[m].stack().median():>9.2f}"
              f"{up[m].stack().median()*100:>8.0f}%{ddw[m].stack().median()*100:>+8.1f}%"
              f"{spike[m].stack().median()*100:>10.0f}%")

    print(f"\n=== (Q3) usability: median day-to-day Jaccard of top-{TOPN}; gate size; streaks ===")
    for k, rk in variants.items():
        m = (rk <= TOPN).to_numpy()
        jac = []
        for i in range(W + 1, len(m)):
            a, b = m[i - 1], m[i]
            union = (a | b).sum()
            if union > 0: jac.append((a & b).sum() / union)
        print(f"  {k:16} median Jaccard {np.median(jac):.2f}")
    gate = (up >= 0.6) & (net > 0)
    gsz = gate.sum(axis=1).iloc[W + 1:]
    print(f"  V3 gate pass count/day: median {gsz.median():.0f}  p25 {gsz.quantile(.25):.0f}  "
          f"p75 {gsz.quantile(.75):.0f}  (universe {px.shape[1]})")
    m = (variants["V3_up6of10+net"] <= TOPN).to_numpy()
    streaks = []
    for j in range(m.shape[1]):
        run = 0
        for i in range(m.shape[0]):
            if m[i, j]: run += 1
            elif run: streaks.append(run); run = 0
        if run: streaks.append(run)
    streaks = np.array(streaks)
    print(f"  V3 time-on-list streaks: median {np.median(streaks):.0f}d  p75 {np.percentile(streaks,75):.0f}d  "
          f"max {streaks.max()}d  (share >=3d: {(streaks>=3).mean()*100:.0f}%)")

    print(f"\n=== (Q4) honesty: median forward 21d return, picks vs universe (we CLAIM none) ===")
    fwd = px.shift(-21) / px - 1.0
    uni_med = fwd.stack().median()
    for k, rk in variants.items():
        m = rk <= TOPN
        print(f"  {k:16} picks {fwd[m].stack().median()*100:+5.1f}%  vs universe {uni_med*100:+5.1f}%")

    print("\n=== VERDICT ===")
    print("  V3 (gate: >=6 of 10 days up & net>0; sort: net10) — all exemplars in top-50 by d0-d10.")
    print("  Strict smoothness gates lose the biggest fish (SNDK d66): rockets are not smooth early.")
    print("  Smoothness (ker/ddw/up) belongs in EVIDENCE COLUMNS, not hard gates. No forward-return claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
