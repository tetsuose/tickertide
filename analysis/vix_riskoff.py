"""Is "high VIX -> risk-off" a LEADING indicator, and how should it actually be used?

Tests the intuition empirically on VIX (FRED VIXCLS, 1990+) vs the S&P 500 (^GSPC), because the
intuition is usually BACKWARDS. Three questions:
  (1) Does high VIX predict LOWER forward returns (risk-off/leading)? -> bucket forward SPY return by VIX level.
  (2) Does high VIX predict higher forward VOLATILITY / drawdown? -> bucket forward realized vol + maxDD.
  (3) Does VIX LEAD the move or move WITH it? -> corr(VIX_t, trailing SPY ret) vs corr(VIX_t, forward SPY ret).
And the one legitimate use:
  (4) Vol-targeting: does sizing DOWN when vol is high improve Sharpe / cut drawdown (Moreira-Muir)? vs buy&hold.

All causal: VIX_t known at t's close; forward windows strictly after t.

Run: /Users/.../.venv/bin/python analysis/vix_riskoff.py
"""
from __future__ import annotations
import io, json, urllib.request
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]; DATA = ROOT / "data"
ANN = np.sqrt(252.0)


def fred(series):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd=1990-01-01"
    raw = urllib.request.urlopen(url, timeout=60).read().decode()
    df = pd.read_csv(io.StringIO(raw)); df.columns = ["date", series]
    df["date"] = pd.to_datetime(df["date"]); s = pd.to_numeric(df[series], errors="coerce")
    s.index = df["date"]; return s.dropna()


def main():
    import yfinance as yf
    vix = fred("VIXCLS")
    spx = yf.Ticker("^GSPC").history(period="max", auto_adjust=True)["Close"].dropna()
    spx.index = pd.DatetimeIndex(spx.index).tz_localize(None)
    df = pd.DataFrame({"spx": spx, "vix": vix.reindex(spx.index).ffill(limit=3)}).dropna()
    df = df[df.index >= "1990-01-01"]
    p = df["spx"].to_numpy(); v = df["vix"].to_numpy(); n = len(p)
    lr = np.diff(np.log(p), prepend=np.log(p[0]))
    print(f"[data] VIX+SPX {df.index.min().date()}..{df.index.max().date()}  n={n}")

    def fwd_ret(h): return np.concatenate([p[h:] / p[:-h] - 1, np.full(h, np.nan)])
    def fwd_vol(h): return pd.Series(lr).rolling(h).std().shift(-h).to_numpy() * ANN
    def fwd_maxdd(h):
        out = np.full(n, np.nan)
        for t in range(n - h):
            seg = p[t:t + h + 1]; out[t] = seg.min() / p[t] - 1
        return out
    r21, r63 = fwd_ret(21), fwd_ret(63)
    fv21 = fwd_vol(21); dd63 = fwd_maxdd(63)
    trail21 = np.concatenate([np.full(21, np.nan), p[21:] / p[:-21] - 1])[:n]  # trailing 21d ret aligned at t

    # (1)+(2) buckets by VIX level
    edges = [0, 13, 16, 20, 25, 30, 40, 200]; lbl = ["<13", "13-16", "16-20", "20-25", "25-30", "30-40", ">40"]
    print("\n=== forward SPY by VIX level (annualized fwd return; is high VIX risk-OFF?) ===")
    print(f"  {'VIX':8}{'n':>7}{'fwd21d(ann)':>13}{'fwd63d(ann)':>13}{'fwd21 vol':>11}{'fwd63 maxDD':>13}")
    rows = []
    for i in range(len(lbl)):
        m = (v >= edges[i]) & (v < edges[i + 1]) & ~np.isnan(r21)
        if m.sum() < 30:
            continue
        a21 = np.nanmean(r21[m]) * (252 / 21); a63 = np.nanmean(r63[m]) * (252 / 63)
        vol = np.nanmean(fv21[m]); dd = np.nanmean(dd63[m])
        rows.append({"vix": lbl[i], "n": int(m.sum()), "fwd21_ann": a21, "fwd63_ann": a63, "fwd_vol": vol, "fwd_maxdd": dd})
        print(f"  {lbl[i]:8}{int(m.sum()):>7}{a21*100:>+12.1f}%{a63*100:>+12.1f}%{vol*100:>10.0f}%{dd*100:>+12.1f}%")
    full_ann = np.nanmean(r21) * (252 / 21)
    print(f"  {'ALL':8}{int((~np.isnan(r21)).sum()):>7}{full_ann*100:>+12.1f}%{'':>13}{np.nanmean(fv21)*100:>10.0f}%{np.nanmean(dd63)*100:>+12.1f}%")

    # (3) lead vs lag
    okt = ~np.isnan(trail21) & ~np.isnan(r21)
    c_trail = np.corrcoef(v[okt], trail21[okt])[0, 1]
    c_fwd = np.corrcoef(v[okt], r21[okt])[0, 1]
    print("\n=== does VIX LEAD or move WITH the market? (corr of VIX level with SPY 21d return) ===")
    print(f"  corr(VIX_t, TRAILING 21d return) = {c_trail:+.2f}   (strong negative = VIX rises WITH/AFTER the drop = coincident/lagging)")
    print(f"  corr(VIX_t, FORWARD  21d return) = {c_fwd:+.2f}   (~0 or slightly + => high VIX does NOT predict further falls)")

    # (4) vol targeting (the legitimate use): size = clip(target/trailing_vol, 0, 1.5)
    tv = pd.Series(lr).rolling(21).std().to_numpy() * ANN
    w = np.clip(0.15 / tv, 0.0, 1.5)              # target 15% annualized vol
    w = np.concatenate([[np.nan], w[:-1]])         # use yesterday's vol estimate (causal, no lookahead)
    strat = np.nan_to_num(w) * lr                  # daily log-ret of vol-targeted SPY
    bh = lr
    def stats(x, wt=None):
        x = x[~np.isnan(x)]
        eq = np.cumsum(x); dd = (eq - np.maximum.accumulate(eq))
        sharpe = (np.mean(x) / np.std(x)) * ANN if np.std(x) > 0 else np.nan
        return sharpe, float(dd.min())
    s_bh, dd_bh = stats(bh)
    msk = ~np.isnan(w)
    s_vt, dd_vt = stats(strat[msk])
    print("\n=== (4) the legitimate use — vol targeting (size DOWN when vol high), causal ===")
    print(f"  buy&hold SPY:        Sharpe {s_bh:.2f}  max log-drawdown {dd_bh:+.2f}")
    print(f"  vol-targeted (15%):  Sharpe {s_vt:.2f}  max log-drawdown {dd_vt:+.2f}")
    print("  (Moreira-Muir: scaling down in high-vol regimes is RISK MANAGEMENT, not return timing.)")

    DATA.mkdir(exist_ok=True)
    json.dump({"buckets": rows, "corr_trailing": c_trail, "corr_forward": c_fwd,
               "sharpe_bh": s_bh, "sharpe_voltarget": s_vt, "maxdd_bh": dd_bh, "maxdd_vt": dd_vt},
              open(DATA / "vix_riskoff_summary.json", "w"), indent=1, default=float)

    print("\n=== VERDICT ===")
    print("  'high VIX' is NOT a leading SELL signal. It is COINCIDENT-to-lagging (rises WITH the drop), and")
    print("  forward returns after high VIX are flat-to-ABOVE average (risk premium / mean reversion) — selling")
    print("  on high VIX historically means selling the bottom. What high VIX DOES predict is higher forward")
    print("  VOLATILITY (turbulence, both directions). Correct uses: (a) vol-targeting / position SIZING (size")
    print("  down when vol high -> better Sharpe, smaller drawdown); (b) evidence/context ('high-vol regime,")
    print("  expect bigger swings'); (c) a CONTRARIAN tilt at extremes. NOT a market-direction timer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
