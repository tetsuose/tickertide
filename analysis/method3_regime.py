"""Method 3 — Tier A decisive experiment: does a fitted LightGBM market-RISK-REGIME
filter beat a TRIVIAL VIX / HAR-RV baseline out-of-sample? (PRD §15 is an independent
"does market-weather have forward edge" question; this is RESEARCH, not a product feature.)

WHY THIS EXACT CUT (the cheapest honest test):
  The headline AUC of any forward-vol model is mostly FREE volatility persistence — a
  one-line "current VIX percentile" rule and a HAR-RV (Corsi 2009) vol forecast already
  capture the bulk of it. So the ONLY decision-useful number is the INCREMENTAL lift of
  LightGBM OVER the best trivial baseline, measured OOS with leakage controls. If the lift
  is inside the fold/episode spread, the honest verdict is "no edge over persistence" — a
  money-saving result that means do NOT buy survivorship-free universe data (Tier B).

SURVIVORSHIP-IMMUNE BY CONSTRUCTION: signals are ETF-derived (SPY/QQQ/IWM/RSP + 9 core
SPDR sectors) — index providers already reconstitute membership point-in-time, so we never
touch the constituent universe (no delisted-name bias). Macro = non-revised FRED daily
series via the unauthenticated fredgraph CSV (VIX/OAS/Treasuries) — FRED-latest == PIT for
these (they are not revised). Labels are defined on SPY itself (also survivorship-immune).
Revision-sensitive series (jobless claims, STLFSI) and constituent breadth are Tier B and
are deliberately EXCLUDED here.

LEAKAGE CONTROLS (this is the whole point):
  - Features use only data <= t; labels use only the strictly-forward window (t, t+H].
  - The vol-label threshold is a leak-free EXPANDING quantile of TRAILING realized vol.
  - Walk-forward is PURGED + EMBARGOED (drop the H+embargo rows before each test block) so a
    fitted model never trains on labels whose forward window overlaps the test period.
  - Leave-one-crisis-out additionally tests transfer to a regime the model never saw.

HONESTY CAVEATS (print, do not hide): yfinance ETFs are still survivorship-immune but the
window is 2003+ (RSP start) = ~6 independent crisis episodes (2008/2011/2015-16/2018Q4/
2020/2022); drawdown/AUC are effectively few-episode statistics, so we report PER-FOLD and
PER-CRISIS spreads, not just a point estimate. 2003-2026 is mostly bull regimes.

Research-only deps (NEVER add to repo requirements.txt / never imported by engine|compute|export):
    pip install "lightgbm>=4.6" "scikit-learn>=1.7" "statsmodels>=0.14" "scipy>=1.11" "matplotlib>=3.8"
(pandas/numpy already present.) FRED is no-key (fredgraph CSV via stdlib urllib); yfinance for ETFs.

Run:  /Users/youihan/Projects/tickertide/.venv/bin/python analysis/method3_regime.py
      [--refresh] [--folds 6] [--embargo 5]
Outputs: stdout report + data/method3_regime_summary.json + data/method3_regime_overlay.png
"""
from __future__ import annotations

import argparse
import io
import json
import pickle
import sys
import urllib.request
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "_method3_cache.pkl"
SUMMARY = DATA / "method3_regime_summary.json"
OVERLAY = DATA / "method3_regime_overlay.png"

ETFS = ["SPY", "QQQ", "IWM", "RSP"]
SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU"]  # 9 core, full history since 1998
FRED = {
    "vix": "VIXCLS",
    # BAA10Y = Moody's Baa corporate minus 10Y Treasury credit spread: daily, full history since
    # 1990, market-priced / non-revised (PIT-clean). Substitutes for ICE BofA OAS because the
    # no-key fredgraph CSV now HARD-CAPS the BAML OAS series (BAMLH0A0HYM2/BAMLC0A0CM) to ~3y;
    # BAA10Y carries the same economic content (credit-risk premium widening = risk-off).
    "baa10y": "BAA10Y",
    "t10y2y": "T10Y2Y",
    "t10y3m": "T10Y3M",
    "dgs2": "DGS2",
    "dgs10": "DGS10",
    "dgs3mo": "DGS3MO",
}
HORIZONS = [20, 60]
LABELS = ["vol", "drawdown"]
DD_THRESH = {20: -0.05, 60: -0.08}   # forward max-drawdown threshold per horizon (drawdown label)
VOL_Q = 0.80                          # forward vol above expanding-80th-pct of trailing vol = "bad" (vol label)
ANN = np.sqrt(252.0)

# Independent crisis episodes for leave-one-crisis-out (regime-transfer test).
CRISES = {
    "2008-GFC": ("2008-06-01", "2009-06-30"),
    "2011-EU/downgrade": ("2011-07-01", "2011-12-31"),
    "2015-16-China/oil": ("2015-08-01", "2016-02-29"),
    "2018Q4-taper": ("2018-10-01", "2018-12-31"),
    "2020-COVID": ("2020-02-15", "2020-05-31"),
    "2022-rate/grind": ("2022-01-01", "2022-10-31"),
}


# ----------------------------------------------------------------------------- data
def _fetch_etf(ticker: str) -> pd.Series:
    import yfinance as yf
    h = yf.Ticker(ticker).history(period="max", auto_adjust=True)["Close"].dropna()
    h.index = pd.DatetimeIndex(h.index).tz_localize(None).normalize()
    return h.rename(ticker)


def _fetch_fred(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd=1990-01-01"
    raw = urllib.request.urlopen(url, timeout=60).read().decode()
    df = pd.read_csv(io.StringIO(raw))
    df.columns = ["date", series_id]
    df["date"] = pd.to_datetime(df["date"])
    s = pd.to_numeric(df[series_id], errors="coerce")   # FRED uses "." for missing
    s.index = df["date"]
    return s.dropna()


def load_raw(refresh: bool) -> dict:
    if CACHE.exists() and not refresh:
        return pickle.load(open(CACHE, "rb"))
    print("[fetch] yfinance ETFs + sectors, FRED (no-key CSV) ...", flush=True)
    raw = {}
    for t in ETFS + SECTORS:
        raw[t] = _fetch_etf(t)
        print(f"  etf {t:5} {raw[t].index.min().date()}..{raw[t].index.max().date()} n={len(raw[t])}", flush=True)
    for k, sid in FRED.items():
        raw[k] = _fetch_fred(sid)
        print(f"  fred {k:7} ({sid}) {raw[k].index.min().date()}..{raw[k].index.max().date()} n={len(raw[k])}", flush=True)
    DATA.mkdir(exist_ok=True)
    pickle.dump(raw, open(CACHE, "wb"))
    return raw


# --------------------------------------------------------------------------- panel
def build_panel(raw: dict) -> pd.DataFrame:
    """Align everything onto the SPY trading-day calendar; macro ffilled (<=5 stale days)."""
    cal = raw["SPY"].index
    px = pd.DataFrame(index=cal)
    for t in ETFS:
        px[t] = raw[t].reindex(cal)
    sec = pd.DataFrame({t: raw[t].reindex(cal) for t in SECTORS})
    macro = pd.DataFrame(index=cal)
    for k in FRED:
        macro[k] = raw[k].reindex(cal).ffill(limit=5)
    panel = pd.concat([px, macro], axis=1)
    panel["_sector_disp"] = np.log(sec).diff().std(axis=1, ddof=0)  # cross-sectional std of sector daily log-returns
    return panel


def _rvol(logret: pd.Series, k: int) -> pd.Series:
    return logret.rolling(k).std() * ANN


def _expand_pct(s: pd.Series, minp: int = 252) -> pd.Series:
    """Causal expanding percentile rank in [0,1] of the latest value vs its own history."""
    return s.expanding(min_periods=minp).apply(lambda a: (a[-1] >= a).mean(), raw=True)


def build_features(panel: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=panel.index)
    lr = {t: np.log(panel[t]).diff() for t in ETFS}
    for t in ETFS:
        for k in (5, 22, 63):
            f[f"{t}_rv{k}"] = _rvol(lr[t], k)
        for k in (5, 20, 63):
            f[f"{t}_ret{k}"] = panel[t].pct_change(k)
        roll_hi = panel[t].rolling(252, min_periods=63).max()
        f[f"{t}_dd"] = panel[t] / roll_hi - 1.0           # current drawdown from trailing 1y high
    # breadth / risk-appetite proxies (all survivorship-immune ETF ratios)
    for name, num, den in [("rsp_spy", "RSP", "SPY"), ("iwm_spy", "IWM", "SPY"), ("iwm_qqq", "IWM", "QQQ")]:
        ratio = panel[num] / panel[den]
        f[f"{name}_chg20"] = ratio.pct_change(20)
        f[f"{name}_chg63"] = ratio.pct_change(63)
        f[f"{name}_z"] = (ratio - ratio.rolling(252, min_periods=63).mean()) / ratio.rolling(252, min_periods=63).std()
    f["sector_disp"] = panel["_sector_disp"]
    f["sector_disp_z"] = (panel["_sector_disp"] - panel["_sector_disp"].rolling(252, min_periods=63).mean()) \
        / panel["_sector_disp"].rolling(252, min_periods=63).std()
    # VIX
    f["vix"] = panel["vix"]
    f["vix_chg5"] = panel["vix"].diff(5)
    f["vix_pct"] = _expand_pct(panel["vix"])
    f["vix_minus_rv"] = panel["vix"] - f["SPY_rv22"]      # implied minus realized
    # credit (BAA10Y = Moody's Baa minus 10Y Treasury; daily, full history, market-priced/non-revised)
    f["baa10y"] = panel["baa10y"]
    f["baa10y_chg20"] = panel["baa10y"].diff(20)
    f["baa10y_chg63"] = panel["baa10y"].diff(63)
    f["baa10y_pct"] = _expand_pct(panel["baa10y"])
    # curve / rates
    for k in ("t10y2y", "t10y3m", "dgs2", "dgs10", "dgs3mo"):
        f[k] = panel[k]
    f["dgs10_chg20"] = panel["dgs10"].diff(20)
    f["dgs2_chg20"] = panel["dgs2"].diff(20)
    return f


def build_label(panel: pd.DataFrame, horizon: int, kind: str):
    """Leak-free forward 'bad regime' label on SPY. Returns (label int Series, extras dict)."""
    spy = panel["SPY"]
    lr = np.log(spy).diff()
    fwd_vol = lr.rolling(horizon).std().shift(-horizon) * ANN          # vol over (t, t+H]
    fwd_trough = spy.rolling(horizon).min().shift(-horizon) / spy - 1  # worst close-to-close drop in (t, t+H]
    if kind == "vol":
        trail_vol = lr.rolling(horizon).std() * ANN                   # trailing realized vol
        thr = trail_vol.expanding(min_periods=252).quantile(VOL_Q)    # leak-free threshold (uses <= t only)
        label = (fwd_vol > thr).astype("float")
    elif kind == "drawdown":
        label = (fwd_trough < DD_THRESH[horizon]).astype("float")
    else:
        raise ValueError(kind)
    label[fwd_vol.isna()] = np.nan                                    # no forward window near the end
    return label, {"fwd_vol": fwd_vol, "fwd_trough": fwd_trough}


# ------------------------------------------------------------------------ splits
def purged_walk_forward(n: int, k_folds: int, horizon: int, embargo: int, init_frac: float = 0.30):
    """Expanding, past-only, purged+embargoed walk-forward over a single time series of length n."""
    start = int(n * init_frac)
    bounds = np.linspace(start, n, k_folds + 1).astype(int)
    out = []
    for i in range(k_folds):
        te = np.arange(bounds[i], bounds[i + 1])
        tr_end = bounds[i] - (horizon + embargo)          # purge: no train label window reaches into test
        if tr_end <= 252:
            continue
        out.append((np.arange(0, tr_end), te))
    return out


def loco_splits(dates: pd.DatetimeIndex, horizon: int, embargo: int):
    """Leave-one-crisis-out: test = the crisis block; train = everything outside [crisis ± purge]."""
    out = []
    purge = pd.Timedelta(days=int((horizon + embargo) * 1.5))
    for name, (s, e) in CRISES.items():
        s, e = pd.Timestamp(s), pd.Timestamp(e)
        te = np.where((dates >= s) & (dates <= e))[0]
        if len(te) == 0:
            continue
        tr = np.where((dates < s - purge) | (dates > e + purge))[0]
        out.append((name, tr, te))
    return out


# ------------------------------------------------------------------------ models
def _lgbm():
    from lightgbm import LGBMClassifier
    return LGBMClassifier(
        n_estimators=300, num_leaves=15, min_child_samples=80, learning_rate=0.03,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
        random_state=0, n_jobs=-1, verbosity=-1,
    )


def _logreg():
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    return Pipeline([
        ("imp", SimpleImputer(strategy="median")),
        ("sc", StandardScaler()),
        ("lr", LogisticRegression(max_iter=2000, C=1.0)),
    ])


def _har_rv_scores(panel, train_idx, test_idx, horizon):
    """HAR-RV (Corsi 2009) baseline: OLS forward-vol ~ RV(1d,5d,22d) on TRAIN, predict on TEST.
    Returns predicted forward vol on test (higher = more 'bad-regime' likely)."""
    import statsmodels.api as sm
    spy = panel["SPY"]
    lr = np.log(spy).diff()
    rv_d = (lr.abs())                                  # |daily| proxy for 1d RV
    rv_w = _rvol(lr, 5) / ANN
    rv_m = _rvol(lr, 22) / ANN
    fwd = lr.rolling(horizon).std().shift(-horizon)    # forward vol (not annualized; scale irrelevant for ranking)
    X = pd.DataFrame({"rv_d": rv_d, "rv_w": rv_w, "rv_m": rv_m})
    df = pd.concat([X, fwd.rename("y")], axis=1)
    tr = df.iloc[train_idx].dropna()
    if len(tr) < 100:
        return np.full(len(test_idx), np.nan)
    model = sm.OLS(tr["y"], sm.add_constant(tr[["rv_d", "rv_w", "rv_m"]])).fit(
        cov_type="HAC", cov_kwds={"maxlags": horizon})
    Xte = sm.add_constant(X.iloc[test_idx][["rv_d", "rv_w", "rv_m"]], has_constant="add")
    return model.predict(Xte).to_numpy()


# ------------------------------------------------------------------------ eval
def _metrics(y, score, proba=None):
    from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
    m = {"n": int(len(y)), "base_rate": float(np.mean(y))}
    ok = (~np.isnan(score)) & (~np.isnan(y))
    y2, s2 = y[ok], score[ok]
    if len(np.unique(y2)) < 2:
        m.update(auc=np.nan, pr=np.nan)
    else:
        m["auc"] = float(roc_auc_score(y2, s2))
        m["pr"] = float(average_precision_score(y2, s2))
    if proba is not None:
        okp = (~np.isnan(proba)) & (~np.isnan(y))
        if okp.sum():
            m["brier"] = float(brier_score_loss(y[okp], np.clip(proba[okp], 0, 1)))
    return m


def run_config(panel, feats, horizon, kind, k_folds, embargo):
    label, extras = build_label(panel, horizon, kind)
    X = feats.to_numpy(dtype=float)
    y = label.to_numpy(dtype=float)
    dates = panel.index
    vix_pct = feats["vix_pct"].to_numpy()
    rv_pct = _expand_pct(feats["SPY_rv22"]).to_numpy()

    # ---- walk-forward (purged) ----
    splits = purged_walk_forward(len(y), k_folds, horizon, embargo)
    rows = {k: [] for k in ("lgbm", "logreg", "vix_pct", "rv_pct", "har")}
    oos_p = np.full(len(y), np.nan)   # stitched OOS LightGBM proba for the overlay plot
    for tr, te in splits:
        ytr, yte = y[tr], y[te]
        keep = ~np.isnan(ytr)
        if keep.sum() < 250 or len(np.unique(ytr[keep])) < 2:
            continue
        lg = _lgbm().fit(X[tr][keep], ytr[keep])
        p_lg = lg.predict_proba(X[te])[:, 1]
        oos_p[te] = p_lg
        rows["lgbm"].append(_metrics(yte, p_lg, p_lg))
        lr = _logreg().fit(X[tr][keep], ytr[keep])
        p_lr = lr.predict_proba(X[te])[:, 1]
        rows["logreg"].append(_metrics(yte, p_lr, p_lr))
        rows["vix_pct"].append(_metrics(yte, vix_pct[te]))
        rows["rv_pct"].append(_metrics(yte, rv_pct[te]))
        rows["har"].append(_metrics(yte, _har_rv_scores(panel, tr, te, horizon)))

    def agg(ms):
        a = np.array([m["auc"] for m in ms if not np.isnan(m.get("auc", np.nan))])
        pr = np.array([m["pr"] for m in ms if not np.isnan(m.get("pr", np.nan))])
        return {"folds": len(a), "auc_mean": float(a.mean()) if len(a) else np.nan,
                "auc_std": float(a.std()) if len(a) else np.nan,
                "auc_min": float(a.min()) if len(a) else np.nan,
                "pr_mean": float(pr.mean()) if len(pr) else np.nan}
    wf = {k: agg(v) for k, v in rows.items()}

    # per-fold delta: LightGBM vs best-of-baselines, fold by fold
    base_keys = ["vix_pct", "rv_pct", "har"]
    deltas = []
    for i in range(len(rows["lgbm"])):
        la = rows["lgbm"][i].get("auc", np.nan)
        ba = np.nanmax([rows[k][i].get("auc", np.nan) for k in base_keys])
        if not (np.isnan(la) or np.isnan(ba)):
            deltas.append(la - ba)
    deltas = np.array(deltas)
    wf_delta = {"per_fold": [round(float(d), 4) for d in deltas],
                "mean": float(deltas.mean()) if len(deltas) else np.nan,
                "win_rate": float((deltas > 0).mean()) if len(deltas) else np.nan}

    # ---- leave-one-crisis-out (transfer to an unseen regime) ----
    loco = {}
    for name, tr, te in loco_splits(dates, horizon, embargo):
        ytr, yte = y[tr], y[te]
        keep = ~np.isnan(ytr)
        tok = ~np.isnan(yte)
        if keep.sum() < 250 or len(np.unique(yte[tok])) < 2:
            loco[name] = {"skip": True, "base_rate": float(np.nanmean(yte))}
            continue
        lg = _lgbm().fit(X[tr][keep], ytr[keep])
        p_lg = lg.predict_proba(X[te])[:, 1]
        m_lg = _metrics(yte, p_lg, p_lg)
        m_vix = _metrics(yte, vix_pct[te])
        m_har = _metrics(yte, _har_rv_scores(panel, tr, te, horizon))
        loco[name] = {"base_rate": round(m_lg["base_rate"], 3), "n": m_lg["n"],
                      "auc_lgbm": round(m_lg.get("auc", np.nan), 3),
                      "auc_vix_pct": round(m_vix.get("auc", np.nan), 3),
                      "auc_har": round(m_har.get("auc", np.nan), 3),
                      "delta_vs_best": round(m_lg.get("auc", np.nan)
                                             - np.nanmax([m_vix.get("auc", np.nan), m_har.get("auc", np.nan)]), 3)}

    # feature importance (full-sample fit, gain) — descriptive only
    keepall = ~np.isnan(y)
    imp = {}
    if len(np.unique(y[keepall])) == 2:
        lg = _lgbm().fit(X[keepall], y[keepall])
        gains = lg.booster_.feature_importance(importance_type="gain")
        imp = dict(sorted(zip(feats.columns, [int(g) for g in gains]), key=lambda kv: -kv[1])[:15])

    return {"horizon": horizon, "label": kind, "base_rate": float(np.nanmean(y)),
            "n_rows": int(keepall.sum()), "walk_forward": wf, "wf_delta": wf_delta,
            "loco": loco, "feature_importance_gain": imp, "_oos_p": oos_p, "_label": y}


# ------------------------------------------------------------------------ report
def fmt(x, d=3):
    return "  n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}"


def print_report(res, panel):
    print("\n" + "=" * 78)
    print(f"METHOD 3 — Tier A decisive experiment   window {panel.index.min().date()}..{panel.index.max().date()}"
          f"  ({len(panel)} trading days)")
    print("=" * 78)
    for r in res:
        print(f"\n### label={r['label']}  horizon={r['horizon']}d   base_rate={r['base_rate']:.1%}  rows={r['n_rows']}")
        wf = r["walk_forward"]
        print(f"  {'method':10}{'OOS AUC':>10}{'(std)':>8}{'(min)':>8}{'PR-AUC':>9}{'folds':>7}")
        for k, lbl in [("lgbm", "LightGBM"), ("logreg", "LogReg"), ("vix_pct", "VIX-pct*"),
                       ("rv_pct", "RVol-pct*"), ("har", "HAR-RV*")]:
            a = wf[k]
            print(f"  {lbl:10}{fmt(a['auc_mean']):>10}{fmt(a['auc_std']):>8}{fmt(a['auc_min']):>8}"
                  f"{fmt(a['pr_mean']):>9}{a['folds']:>7}")
        d = r["wf_delta"]
        print(f"  -> LightGBM ΔAUC over BEST trivial baseline (* = trivial): "
              f"mean={fmt(d['mean'])}  win-rate={fmt(d['win_rate'],2)}  per-fold={d['per_fold']}")
        print(f"  leave-one-crisis-out (transfer to an UNSEEN regime):")
        print(f"    {'crisis':20}{'base':>7}{'AUC_lgbm':>10}{'AUC_VIXpct':>12}{'AUC_HAR':>9}{'Δvs.best':>10}")
        for name, lc in r["loco"].items():
            if lc.get("skip"):
                print(f"    {name:20}{lc['base_rate']:>7.2f}   (skip: one-class test block)")
                continue
            print(f"    {name:20}{lc['base_rate']:>7.2f}{fmt(lc['auc_lgbm']):>10}{fmt(lc['auc_vix_pct']):>12}"
                  f"{fmt(lc['auc_har']):>9}{fmt(lc['delta_vs_best']):>10}")
        if r["feature_importance_gain"]:
            top = list(r["feature_importance_gain"].items())[:8]
            print("  top LightGBM features (gain): " + ", ".join(f"{k}={v}" for k, v in top))


def verdict(res):
    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    for r in res:
        d = r["wf_delta"]
        loco_d = [lc["delta_vs_best"] for lc in r["loco"].values()
                  if not lc.get("skip") and lc.get("delta_vs_best") is not None and not np.isnan(lc["delta_vs_best"])]
        loco_mean = float(np.mean(loco_d)) if loco_d else float("nan")
        loco_pos = float(np.mean([x > 0 for x in loco_d])) if loco_d else float("nan")
        tag = "label={} h={}d".format(r["label"], r["horizon"])
        beats = (not np.isnan(d["mean"])) and d["mean"] > 0.02 and d["win_rate"] >= 0.6 \
            and (not np.isnan(loco_mean)) and loco_mean > 0
        msg = ("BEATS baseline (ΔAUC>+0.02, wins>=60% folds, positive cross-crisis) "
               "-> consider Tier B") if beats else \
              ("NO reliable edge over the trivial VIX/HAR rule (Δ inside fold/crisis spread) "
               "-> STOP, do NOT buy Tier B data")
        print(f"  [{tag}] wf ΔAUC={fmt(d['mean'])} win={fmt(d['win_rate'],2)} | "
              f"crisis ΔAUC={fmt(loco_mean)} pos={fmt(loco_pos,2)}  => {msg}")
    print("\n  Read: trivial baselines (*) are the bar. The decision is the INCREMENTAL ΔAUC, not the")
    print("  absolute AUC (most of which is free volatility persistence). Few crises => wide CIs;")
    print("  trust the per-fold/per-crisis spread over any single number.")


def make_overlay(res, panel):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"[plot] skipped ({type(e).__name__})")
        return
    prim = next((r for r in res if r["label"] == "vol" and r["horizon"] == 60), res[0])
    p = pd.Series(prim["_oos_p"], index=panel.index)
    spy = panel["SPY"]
    dd = spy / spy.cummax() - 1.0
    fig, ax = plt.subplots(2, 1, figsize=(11, 7), sharex=True, height_ratios=[2, 1])
    ax[0].plot(spy.index, spy.values, lw=0.8, color="#185FA5", label="SPY")
    ax[0].set_yscale("log"); ax[0].set_ylabel("SPY (log)")
    axb = ax[0].twinx()
    axb.fill_between(p.index, 0, p.values, color="#E24B4A", alpha=0.25, label="OOS p_bad")
    axb.set_ylim(0, 1); axb.set_ylabel("OOS p_bad", color="#A32D2D")
    ax[0].set_title(f"Method 3 Tier A — OOS p_bad ({prim['label']} h{prim['horizon']}) vs SPY  "
                    f"(walk-forward, purged)")
    ax[1].fill_between(dd.index, dd.values, 0, color="#888780", alpha=0.5)
    ax[1].set_ylabel("SPY drawdown"); ax[1].set_xlabel("date")
    fig.tight_layout()
    DATA.mkdir(exist_ok=True)
    fig.savefig(OVERLAY, dpi=110)
    print(f"[plot] wrote {OVERLAY}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch data (else use cache)")
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--embargo", type=int, default=5)
    a = ap.parse_args(argv)

    raw = load_raw(a.refresh)
    panel = build_panel(raw)
    feats = build_features(panel)
    # restrict to the common window where all required inputs exist (RSP start, OAS, etc.)
    need = ["SPY", "QQQ", "IWM", "RSP", "vix", "baa10y", "t10y2y", "dgs10"]
    valid = panel[need].dropna().index
    panel = panel.loc[valid]
    feats = feats.loc[valid]
    print(f"[panel] modeling window {panel.index.min().date()}..{panel.index.max().date()} "
          f"rows={len(panel)} features={feats.shape[1]}")

    res = []
    for kind in LABELS:
        for h in HORIZONS:
            res.append(run_config(panel, feats, h, kind, a.folds, a.embargo))

    print_report(res, panel)
    verdict(res)
    make_overlay(res, panel)

    out = []
    for r in res:
        rr = {k: v for k, v in r.items() if not k.startswith("_")}
        out.append(rr)
    DATA.mkdir(exist_ok=True)
    json.dump({"window": [str(panel.index.min().date()), str(panel.index.max().date())],
               "rows": len(panel), "configs": out}, open(SUMMARY, "w"), indent=1, default=float)
    print(f"\n[done] summary -> {SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
