"""Does ranking by "MORE-momentum + MORE-STABLE uptrend" beat the naive daily-gainers list?
(The project's north star, in the user's words: "比盯每日涨跌榜,发现更动量更稳定的上涨".)

THE QUESTION (cross-sectional, parameter-free signals — no fitting, so no backtest-optimize):
  Each formation date, rank the universe by several signals; take the top decile; then measure
  what those picks actually DO over the next H days. The naive baseline is the "涨跌榜" —
  trailing return (ret_5 = last week's gainers, ret_21/63). The candidate is "stable momentum":
    slope_r2  = Clenow: annualized OLS slope of log-price (90d) x R^2 (steady steep climb)
    ker_63    = Kaufman efficiency ratio (|net move| / sum|daily move|) — trend smoothness
    sharpe_63 = trailing 63d return / trailing vol (vol-adjusted momentum)
    stable_mom= cross-sectional rank-average of the three (the "更动量更稳定" candidate)
  (These mirror derived_daily's trend_quality/KER, vol_ratio, rs_pct — computed fresh here so
  the experiment is self-contained, like analysis/walkforward_breakout.py.)

WHAT "BETTER" MEANS — two axes, report both honestly:
  (1) forward RETURN: top-decile forward return, top-minus-bottom spread, and Information
      Coefficient (Spearman of signal vs forward return per date).
  (2) forward STABILITY (the actual goal — "更稳定的上涨"): top-decile forward volatility and
      forward worst-drawdown-from-entry, and forward return/vol. Stable-momentum should give a
      SMOOTHER forward ride than the gainers list even if raw return is similar.
  Reference = the equal-weight universe ("just hold everything"). A signal only earns its keep
  if it beats BOTH the naive gainers list AND the universe.

BRUTAL-HONESTY CAVEATS (printed, not hidden):
  - Survivorship: the universe is yfinance still-listed names (the analysis habitat) — delisted
    losers are absent, which FLATTERS momentum. Rank-based IC and top-minus-bottom partially
    control; absolute returns do not. Do not read absolute numbers as live-tradable.
  - Regime: 2010s-2026 is mostly bull + a few shocks; momentum is famously regime-dependent
    (the repo's own base->breakout walk-forward sign-flipped TRAIN/TEST). Per-year is reported
    so you can SEE the regime dependence rather than trust one number.
  - Overlap: formation dates step 21 trading days; for H=63 forward windows overlap ~3x, so the
    time-aggregation is autocorrelated (per-date IC is not). Treat spreads as indicative.

Research-only (analysis/, never product path). Deps already present: pandas/numpy/scipy/matplotlib.
Run: /Users/youihan/Projects/tickertide/.venv/bin/python analysis/stable_momentum.py [--refresh] [--horizon 63]
Outputs: stdout report + data/stable_momentum_summary.json + data/stable_momentum_riskreturn.png
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "_stablemom_cache.pkl"
# universe membership comes from the existing precision habitat (random $0.3B-$100B, seed 42)
UNIVERSE_SRC = [DATA / "_precision_cache.pkl", Path("/Users/youihan/Projects/tickertide/data/_precision_cache.pkl")]
SUMMARY = DATA / "stable_momentum_summary.json"
PLOT = DATA / "stable_momentum_riskreturn.png"

BENCH = "SPY"
HORIZONS = [21, 63]
STEP = 21                 # formation-date spacing (trading days)
TOPQ, BOTQ = 0.10, 0.10
SLOPE_W = 90              # window for Clenow slope x R^2
KER_W = 63
MIN_HIST = 252           # need >= 1y trailing to form signals
MIN_NAMES = 60           # need enough cross-section per date
ANN = np.sqrt(252.0)

NAIVE = ["ret_5", "ret_21", "ret_63"]                 # the "涨跌榜" baselines
STABLE = ["slope_r2", "ker_63", "sharpe_63", "stable_mom"]
EXTRA = ["mom_12_1", "ret_126"]
SIGNALS = NAIVE + EXTRA + STABLE


# ---------------------------------------------------------------------- data
def _universe_tickers():
    for p in UNIVERSE_SRC:
        if p.exists():
            ks = list(pickle.load(open(p, "rb")).keys())
            return [t for t in ks if t != BENCH], p
    raise SystemExit("no precision cache to source the universe from")


def load_prices(refresh: bool) -> pd.DataFrame:
    """Wide adj-close DataFrame (index=date, cols=ticker) over FULL available history."""
    if CACHE.exists() and not refresh:
        return pickle.load(open(CACHE, "rb"))
    import yfinance as yf
    tickers, src = _universe_tickers()
    print(f"[fetch] {len(tickers)} tickers (universe from {src.name}) full history via yfinance ...", flush=True)
    frames = {}
    chunk = 100
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        df = yf.download(part, period="max", auto_adjust=True, progress=False, threads=True)["Close"]
        if isinstance(df, pd.Series):
            df = df.to_frame(part[0])
        for t in df.columns:
            s = df[t].dropna()
            if len(s) >= MIN_HIST + max(HORIZONS) + 5:
                frames[t] = s
        print(f"  fetched {i+len(part)}/{len(tickers)}  kept={len(frames)}", flush=True)
    px = pd.DataFrame(frames)
    px.index = pd.DatetimeIndex(px.index).tz_localize(None).normalize()
    px = px.sort_index()
    DATA.mkdir(exist_ok=True)
    pickle.dump(px, open(CACHE, "wb"))
    return px


# ------------------------------------------------------------------ signals
def _slope_r2(logpx: pd.DataFrame, w: int):
    """Vectorized rolling OLS of log-price on time: annualized slope x R^2 (Clenow)."""
    n = w
    i = pd.DataFrame(np.arange(len(logpx))[:, None].repeat(logpx.shape[1], axis=1),
                     index=logpx.index, columns=logpx.columns).astype(float)
    Sy = logpx.rolling(w).sum()
    Syy = (logpx ** 2).rolling(w).sum()
    Siy = (i * logpx).rolling(w).sum()
    Sii = (i ** 2).rolling(w).sum()
    Si = i.rolling(w).sum()
    den = n * Sii - Si ** 2
    slope = (n * Siy - Si * Sy) / den
    num_r = (n * Siy - Si * Sy) ** 2
    den_r = den * (n * Syy - Sy ** 2)
    r2 = num_r / den_r
    return (slope * 252.0) * r2          # annualized log-slope, weighted by fit quality


def build_signals(px: pd.DataFrame) -> dict:
    logpx = np.log(px)
    lr = logpx.diff()
    sig = {}
    sig["ret_5"] = px.pct_change(5)
    sig["ret_21"] = px.pct_change(21)
    sig["ret_63"] = px.pct_change(63)
    sig["ret_126"] = px.pct_change(126)
    sig["mom_12_1"] = px.shift(21) / px.shift(252) - 1.0
    sig["slope_r2"] = _slope_r2(logpx, SLOPE_W)
    sig["ker_63"] = (px - px.shift(KER_W)).abs() / px.diff().abs().rolling(KER_W).sum()
    sig["sharpe_63"] = sig["ret_63"] / (lr.rolling(63).std() * ANN)
    return sig


def build_forward(px: pd.DataFrame, h: int) -> dict:
    lr = np.log(px).diff()
    fwd = {}
    fwd["ret"] = px.shift(-h) / px - 1.0
    fwd["vol"] = (lr.rolling(h).std().shift(-h)) * ANN
    fwd["trough"] = px.rolling(h).min().shift(-h) / px - 1.0     # worst close vs entry (drawdown-from-entry)
    return fwd


# ------------------------------------------------------------------ eval
def run_horizon(px, sig, h):
    from scipy.stats import spearmanr
    fwd = build_forward(px, h)
    dates = px.index
    lo = MIN_HIST
    hi = len(dates) - h - 1
    form = list(range(lo, hi, STEP))

    rows = {s: [] for s in SIGNALS}          # per-date dict metrics
    ic = {s: [] for s in SIGNALS}
    uni = []                                  # universe (equal-weight all valid) per date
    years = {}                                # per-year accumulation: {year: {sig: [ret...]}}

    # composite stable_mom needs cross-sectional ranks of its 3 parts each date
    for di in form:
        d = dates[di]
        fr = fwd["ret"].iloc[di]
        fv = fwd["vol"].iloc[di]
        ft = fwd["trough"].iloc[di]
        valid = fr.notna() & fv.notna()
        # assemble this date's signal frame
        sv = {s: sig[s].iloc[di] for s in SIGNALS if s != "stable_mom"}
        cur = pd.DataFrame(sv)
        cur = cur[valid.reindex(cur.index, fill_value=False)]
        cur = cur.dropna(how="all")
        if len(cur) < MIN_NAMES:
            continue
        # composite: rank-average of the 3 stability signals (higher = better)
        parts = ["slope_r2", "ker_63", "sharpe_63"]
        rk = cur[parts].rank(pct=True)
        cur["stable_mom"] = rk.mean(axis=1)
        fr_d = fr.reindex(cur.index); fv_d = fv.reindex(cur.index); ft_d = ft.reindex(cur.index)
        uni.append({"ret": float(fr_d.mean()), "vol": float(fv_d.mean()), "trough": float(ft_d.mean()),
                    "n": int(len(cur)), "year": d.year})
        yk = d.year
        years.setdefault(yk, {s: [] for s in SIGNALS})
        for s in SIGNALS:
            col = cur[s].dropna()
            if len(col) < MIN_NAMES:
                continue
            fr_s = fr_d.reindex(col.index);
            ok = fr_s.notna()
            if ok.sum() < MIN_NAMES:
                continue
            rho = spearmanr(col[ok], fr_s[ok]).statistic
            ic[s].append(rho)
            ntop = max(5, int(len(col) * TOPQ))
            top = col.sort_values(ascending=False).head(ntop).index
            bot = col.sort_values(ascending=False).tail(ntop).index
            rows[s].append({"ret": float(fr_d.reindex(top).mean()),
                            "vol": float(fv_d.reindex(top).mean()),
                            "trough": float(ft_d.reindex(top).mean()),
                            "bot_ret": float(fr_d.reindex(bot).mean())})
            years[yk][s].append(float(fr_d.reindex(top).mean()))

    def agg(ms, key):
        a = np.array([m[key] for m in ms if not np.isnan(m[key])])
        return float(a.mean()) if len(a) else np.nan

    out = {"horizon": h, "n_form_dates": len(uni), "signals": {}}
    for s in SIGNALS:
        ms = rows[s]
        icv = np.array([x for x in ic[s] if not np.isnan(x)])
        out["signals"][s] = {
            "ic_mean": float(icv.mean()) if len(icv) else np.nan,
            "ic_std": float(icv.std()) if len(icv) else np.nan,
            "ic_t": float(icv.mean() / (icv.std() / np.sqrt(len(icv)))) if len(icv) > 2 and icv.std() > 0 else np.nan,
            "top_ret": agg(ms, "ret"), "top_vol": agg(ms, "vol"), "top_trough": agg(ms, "trough"),
            "spread": agg(ms, "ret") - agg([{"r": m["bot_ret"]} for m in ms], "r")
            if ms else np.nan,
            "ret_over_vol": (agg(ms, "ret") / agg(ms, "vol")) if ms and agg(ms, "vol") else np.nan,
            "n": len(ms),
        }
    out["universe"] = {"ret": float(np.mean([u["ret"] for u in uni])) if uni else np.nan,
                       "vol": float(np.mean([u["vol"] for u in uni])) if uni else np.nan,
                       "trough": float(np.mean([u["trough"] for u in uni])) if uni else np.nan}
    # per-year top-decile mean return for the key signals
    py = {}
    for yk in sorted(years):
        py[yk] = {s: (float(np.mean(years[yk][s])) if years[yk][s] else np.nan)
                  for s in ["ret_5", "ret_63", "slope_r2", "stable_mom"]}
    out["per_year_top_ret"] = py
    return out


# ------------------------------------------------------------------ report
def fmt(x, d=3, pct=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "   n/a"
    return f"{x*100:+.1f}%" if pct else f"{x:+.{d}f}"


def report(res, px):
    print("\n" + "=" * 92)
    print(f"STABLE MOMENTUM vs the daily-gainers list   universe={px.shape[1]} names  "
          f"{px.index.min().date()}..{px.index.max().date()}")
    print("=" * 92)
    for r in res:
        h = r["horizon"]
        print(f"\n### forward horizon = {h}d   ({r['n_form_dates']} formation dates, every {STEP}d)")
        print(f"  {'signal':11}{'IC':>8}{'IC_t':>7}{'topRet':>9}{'spread':>9}{'topVol':>9}{'topTrough':>11}{'ret/vol':>9}")
        for s in SIGNALS:
            g = r["signals"][s]
            tag = " *" if s in NAIVE else ("  <" if s == "stable_mom" else "  ")
            print(f"  {s:11}{fmt(g['ic_mean']):>8}{fmt(g['ic_t'],1):>7}{fmt(g['top_ret'],pct=True):>9}"
                  f"{fmt(g['spread'],pct=True):>9}{fmt(g['top_vol'],pct=True):>9}{fmt(g['top_trough'],pct=True):>11}"
                  f"{fmt(g['ret_over_vol'],2):>9}{tag}")
        u = r["universe"]
        print(f"  {'[universe]':11}{'--':>8}{'--':>7}{fmt(u['ret'],pct=True):>9}{'--':>9}"
              f"{fmt(u['vol'],pct=True):>9}{fmt(u['trough'],pct=True):>11}"
              f"{fmt(u['ret']/u['vol'],2) if u['vol'] else '   n/a':>9}")
        print("  (* = naive 涨跌榜 baseline ; < = the 更动量更稳定 candidate ; topTrough = worst forward drawdown-from-entry)")
        print(f"  per-year top-decile forward {h}d return  (regime dependence):")
        print(f"    {'year':6}{'ret_5*':>9}{'ret_63*':>9}{'slope_r2':>10}{'stable_mom':>12}")
        for yk, d in r["per_year_top_ret"].items():
            print(f"    {yk:<6}{fmt(d['ret_5'],pct=True):>9}{fmt(d['ret_63'],pct=True):>9}"
                  f"{fmt(d['slope_r2'],pct=True):>10}{fmt(d['stable_mom'],pct=True):>12}")


def verdict(res):
    print("\n" + "=" * 92)
    print("VERDICT")
    print("=" * 92)
    for r in res:
        h = r["horizon"]; S = r["signals"]; u = r["universe"]
        naive_best_ic = max(S[n]["ic_mean"] for n in NAIVE)
        sm = S["stable_mom"]; sl = S["slope_r2"]
        # stability win: does stable_mom give a SMOOTHER forward ride than the best naive gainer (ret_5)?
        n5 = S["ret_5"]
        smoother = (sm["top_trough"] > n5["top_trough"]) and (sm["ret_over_vol"] > n5["ret_over_vol"])
        higher_ic = sm["ic_mean"] > naive_best_ic and sm["ic_mean"] > 0
        beats_uni = sm["top_ret"] > u["ret"]
        print(f"  [h={h}d] stable_mom IC={fmt(sm['ic_mean'])} (best naive IC={fmt(naive_best_ic)}) | "
              f"slope_r2 IC={fmt(sl['ic_mean'])}")
        print(f"          forward ride vs ret_5(weekly gainers): trough {fmt(n5['top_trough'],pct=True)}"
              f" -> {fmt(sm['top_trough'],pct=True)} ; ret/vol {fmt(n5['ret_over_vol'],2)} -> {fmt(sm['ret_over_vol'],2)}")
        msg = []
        msg.append("HIGHER IC than gainers" if higher_ic else "IC NOT better than gainers")
        msg.append("SMOOTHER forward ride" if smoother else "NOT smoother than gainers")
        msg.append("beats universe avg" if beats_uni else "does NOT beat universe")
        print(f"          => " + " | ".join(msg))
    print("\n  Read: the goal ('更动量更稳定的上涨') is served only if stable_mom gives a SMOOTHER forward")
    print("  ride (shallower topTrough, higher ret/vol) than the naive gainers list — ideally with")
    print("  higher IC too. Survivorship flatters all momentum; trust the RELATIVE ranking + per-year.")


def make_plot(res, px):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"[plot] skipped ({type(e).__name__})"); return
    r = next((x for x in res if x["horizon"] == 63), res[0])
    S = r["signals"]
    fig, ax = plt.subplots(figsize=(9, 6))
    for s in SIGNALS:
        g = S[s]
        if np.isnan(g["top_ret"]) or np.isnan(g["top_trough"]):
            continue
        color = "#888780" if s in NAIVE else ("#185FA5" if s == "stable_mom" else "#1D9E75")
        ax.scatter(g["top_trough"] * 100, g["top_ret"] * 100, s=80, color=color, zorder=3)
        ax.annotate(s, (g["top_trough"] * 100, g["top_ret"] * 100), fontsize=8,
                    xytext=(4, 4), textcoords="offset points")
    u = r["universe"]
    ax.scatter(u["trough"] * 100, u["ret"] * 100, marker="x", s=90, color="#A32D2D", zorder=3)
    ax.annotate("universe", (u["trough"] * 100, u["ret"] * 100), fontsize=8, color="#A32D2D",
                xytext=(4, -10), textcoords="offset points")
    ax.set_xlabel("forward worst drawdown-from-entry (%)  ->  righter = smoother ride")
    ax.set_ylabel("forward top-decile return (%)")
    ax.set_title(f"Stable momentum vs gainers — forward {r['horizon']}d risk/return of top-decile picks")
    ax.grid(alpha=0.2)
    fig.tight_layout(); DATA.mkdir(exist_ok=True); fig.savefig(PLOT, dpi=110)
    print(f"[plot] wrote {PLOT}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args(argv)
    px = load_prices(a.refresh)
    print(f"[panel] {px.shape[1]} names  {px.index.min().date()}..{px.index.max().date()}  rows={len(px)}")
    sig = build_signals(px)
    res = [run_horizon(px, sig, h) for h in HORIZONS]
    report(res, px)
    verdict(res)
    make_plot(res, px)
    DATA.mkdir(exist_ok=True)
    json.dump({"universe_n": px.shape[1],
               "window": [str(px.index.min().date()), str(px.index.max().date())],
               "results": res}, open(SUMMARY, "w"), indent=1, default=float)
    print(f"\n[done] summary -> {SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
