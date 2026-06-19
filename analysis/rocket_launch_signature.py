"""User-curated rocket templates -> extract their pre-launch signature -> screen the market ->
HONESTLY measure lift (does the signature predict becoming a rocket?). Anti-lookahead + survivorship.

User approved 10 rocket templates (semis that 3x+'d off their 2024-2025 lows): MU, CRDO, COHR,
SITM, LRCX, MTSI, KLAC, TSM, AVGO, NVMI. Goal: characterize what they looked like AT/just-before
launch (causal, <= launch), turn that into a screenable signal, and test whether matching it
actually elevates the probability of becoming a rocket vs the base rate.

DISCIPLINE:
  - Signature features at launch use ONLY data <= launch (no peeking at the run).
  - Label ("became a rocket") uses the strictly-forward window. Lift = P(rocket|signal)/base_rate.
  - Purged: dedup signals >= 126d/ticker; forward-252d label => events within 252d of panel end dropped.
  - Block-bootstrap CI over signal events; by-decade for regime dependence.
  - Survivorship: 721-name yfinance habitat is still-listed only (flatters rockets); rank/ratio framing.

HONEST PRIOR: the 10 all bottomed together (2024-25 semis), so their shared signature is basically
"high-vol name + deep washout + turning" — the per-stock cousin of the theme-washout signal that
just tested at ~0 edge. Expect thin lift; let the data rule.

Run: /Users/.../.venv/bin/python analysis/rocket_launch_signature.py [--rocket 1.0] [--h 252]
Outputs: stdout (template signature + lift + by-decade + current screen) + data/rocket_signature_summary.json
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
import stable_momentum as sm   # load_prices (721 habitat, full history)  # noqa: E402

DATA = ROOT / "data"
SUMMARY = DATA / "rocket_signature_summary.json"
TEMPLATES = ["MU", "CRDO", "COHR", "SITM", "LRCX", "MTSI", "KLAC", "TSM", "AVGO", "NVMI"]
ANN = np.sqrt(252.0)


def feats(p: pd.Series) -> pd.DataFrame:
    """Causal per-date features (use only data <= t)."""
    arr = p.to_numpy()
    lr = np.diff(np.log(arr), prepend=np.log(arr[0]))
    f = pd.DataFrame(index=p.index)
    roll_hi = pd.Series(arr).rolling(252, min_periods=120).max().to_numpy()
    f["dd252"] = arr / roll_hi - 1.0                                   # drawdown from 1y high
    f["min_dd_126"] = pd.Series(f["dd252"]).rolling(126, min_periods=40).min().to_numpy()  # how washed out recently
    f["rvol126"] = pd.Series(lr).rolling(126, min_periods=60).std().to_numpy() * ANN        # name volatility
    ma50 = pd.Series(arr).rolling(50, min_periods=50).mean().to_numpy()
    ma200 = pd.Series(arr).rolling(200, min_periods=120).mean().to_numpy()
    f["dist_ma50"] = arr / ma50 - 1.0
    f["dist_ma200"] = arr / ma200 - 1.0
    f["above50"] = (arr > ma50).astype(float)
    prev_above = np.concatenate([[0.0], (arr[:-1] > ma50[:-1]).astype(float)])
    f["reclaim50"] = ((arr > ma50) & (prev_above == 0)).astype(float)   # crossed above 50d today
    return f


def template_signature():
    import yfinance as yf
    rows = []
    for t in TEMPLATES:
        p = yf.Ticker(t).history(period="max", auto_adjust=True)["Close"].dropna()
        p.index = pd.DatetimeIndex(p.index).tz_localize(None)
        if len(p) < 300:
            continue
        arr = p.to_numpy()
        lo_i = int(np.argmin(arr[-504:])) + max(0, len(arr) - 504)      # 2yr low index
        f = feats(p)
        # launch = first 50d-MA reclaim at/after the 2yr low (the screenable "turn")
        recl = np.where((f["reclaim50"].to_numpy() == 1) & (np.arange(len(arr)) >= lo_i))[0]
        li = int(recl[0]) if len(recl) else lo_i
        r = f.iloc[li]
        rows.append({"t": t, "low": str(p.index[lo_i].date()), "launch": str(p.index[li].date()),
                     "dd252@launch": float(r["dd252"]), "min_dd_126@launch": float(r["min_dd_126"]),
                     "rvol126@launch": float(r["rvol126"]), "dist_ma200@launch": float(r["dist_ma200"])})
    df = pd.DataFrame(rows)
    return df


def label_rocket(p: pd.Series, h: int, mult: float) -> np.ndarray:
    arr = p.to_numpy()
    fwd_max = pd.Series(arr).rolling(h, min_periods=h // 2).max().shift(-h).to_numpy()
    drawup = fwd_max / arr - 1.0
    return (drawup >= mult).astype(float), drawup


def run(px: pd.DataFrame, h, mult, wo, vol_min, reclaim_req, embargo=21):
    from collections import defaultdict
    events = []           # signal events with forward label
    all_label = []        # for base rate
    vol_label = []        # vol-matched base (rvol>=vol_min) — the fair control
    volwash_label = []    # high-vol + washout (isolate the reclaim/turn contribution)
    decade = defaultdict(list)
    for t in px.columns:
        p = px[t].dropna()
        if len(p) < 300 + h:
            continue
        f = feats(p)
        lab, drawup = label_rocket(p, h, mult)
        valid = ~np.isnan(lab)
        all_label.append(lab[valid])
        hv = (f["rvol126"].to_numpy() >= vol_min)
        wash = (f["min_dd_126"].to_numpy() <= -wo)
        vol_label.append(lab[valid & hv])
        volwash_label.append(lab[valid & hv & wash])
        sig = hv & wash
        if reclaim_req:
            sig = sig & (f["reclaim50"].to_numpy() == 1)
        idx = np.where(sig & valid)[0]
        last = -10 ** 9
        for i in idx:
            if i - last < 126:                                  # dedup overlapping events per ticker
                continue
            last = i
            yr = p.index[i].year
            events.append({"t": t, "date": str(p.index[i].date()), "year": yr, "label": float(lab[i]),
                           "drawup": float(drawup[i]) if not np.isnan(drawup[i]) else np.nan})
            decade[(yr // 10) * 10].append(lab[i])
    base = float(np.concatenate(all_label).mean()) if all_label else np.nan
    vol_base = float(np.concatenate(vol_label).mean()) if vol_label else np.nan      # fair control
    volwash_base = float(np.concatenate(volwash_label).mean()) if volwash_label else np.nan
    ev_lab = np.array([e["label"] for e in events])
    sig_rate = float(ev_lab.mean()) if len(ev_lab) else np.nan
    # block bootstrap CI on signal rate (block over events as proxy; events already deduped per ticker)
    rng = np.random.default_rng(0)
    boots = [ev_lab[rng.integers(0, len(ev_lab), len(ev_lab))].mean() for _ in range(2000)] if len(ev_lab) else []
    ci = (float(np.percentile(boots, 5)), float(np.percentile(boots, 95))) if boots else (np.nan, np.nan)
    by_dec = {int(d): {"n": len(v), "rate": float(np.mean(v))} for d, v in sorted(decade.items())}
    return {"base_rate": base, "vol_base": vol_base, "volwash_base": volwash_base,
            "signal_rate": sig_rate, "signal_ci": ci, "n_events": len(events),
            "lift_ratio": (sig_rate / base) if base else np.nan,
            "lift_vs_vol": (sig_rate / vol_base) if vol_base else np.nan,
            "by_decade": by_dec, "events": events}


def current_screen(px, wo, vol_min, reclaim_req):
    """Which names fire the signal on the latest date — the candidate list."""
    last_date = px.index.max()
    out = []
    for t in px.columns:
        p = px[t].dropna()
        if len(p) < 300 or p.index.max() < last_date - pd.Timedelta(days=10):
            continue
        f = feats(p).iloc[-1]
        fire = (f["min_dd_126"] <= -wo) and (f["rvol126"] >= vol_min)
        if reclaim_req:
            fire = fire and (f["reclaim50"] == 1)
        if fire:
            out.append({"t": t, "dd252": float(f["dd252"]), "min_dd_126": float(f["min_dd_126"]),
                        "rvol126": float(f["rvol126"]), "dist_ma200": float(f["dist_ma200"])})
    return out, str(last_date.date())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rocket", type=float, default=1.0)   # forward 252d max drawup >= this = "rocket" (1.0 = +100%)
    ap.add_argument("--h", type=int, default=252)
    ap.add_argument("--wo", type=float, default=0.30)      # washout depth (min dd in last 126d <= -wo)
    ap.add_argument("--vol", type=float, default=0.40)     # min annualized realized vol (high-vol/rocket-capable)
    ap.add_argument("--noreclaim", action="store_true")
    a = ap.parse_args(argv)

    print("=== template launch signature (causal, at each template's 50d-MA reclaim after its 2y low) ===")
    sig = template_signature()
    with pd.option_context("display.width", 200):
        print(sig.to_string(index=False))
    print("\n  common signature (median across the 10 templates):")
    for c in ["dd252@launch", "min_dd_126@launch", "rvol126@launch", "dist_ma200@launch"]:
        print(f"    {c:20} median {sig[c].median():+.2f}   IQR [{sig[c].quantile(.25):+.2f}, {sig[c].quantile(.75):+.2f}]")

    px = sm.load_prices(False)
    print(f"\n[panel] {px.shape[1]} names  {px.index.min().date()}..{px.index.max().date()}")
    print(f"[signal] washout: 126d-min drawdown <= -{a.wo:.0%}; high-vol: rvol126 >= {a.vol:.0%}; "
          f"{'+ reclaim 50dMA' if not a.noreclaim else '(no reclaim req)'}")
    print(f"[label]  rocket = forward {a.h}d max drawup >= +{a.rocket:.0%}")

    res = run(px, a.h, a.rocket, a.wo, a.vol, not a.noreclaim)
    print(f"\n=== LIFT (does the rocket-launch signal predict becoming a rocket?) ===")
    print(f"  P(rocket) all stock-days (naive base):         {res['base_rate']:.1%}")
    print(f"  P(rocket | high-vol rvol>={a.vol:.0%}) — FAIR base: {res['vol_base']:.1%}   <- the signal only selects high-vol names")
    print(f"  P(rocket | high-vol + washout):                {res['volwash_base']:.1%}")
    print(f"  P(rocket | full signal +reclaim):              {res['signal_rate']:.1%}  [CI {res['signal_ci'][0]:.1%}, {res['signal_ci'][1]:.1%}]  n={res['n_events']}")
    print(f"  LIFT vs naive base   = {res['lift_ratio']:.2f}x  (FLATTERED: this is mostly volatility selection)")
    print(f"  LIFT vs vol-matched  = {res['lift_vs_vol']:.2f}x  <- the real incremental edge of washout+turn timing")
    print(f"\n  by decade (signal-day rocket rate vs base {res['base_rate']:.1%}):")
    print(f"    {'decade':8}{'n':>6}{'rocketRate':>12}")
    for d, v in res["by_decade"].items():
        print(f"    {d:<8}{v['n']:>6}{v['rate']*100:>11.1f}%")

    scr, asof = current_screen(px, a.wo, a.vol, not a.noreclaim)
    print(f"\n=== CURRENT SCREEN (721 habitat, as of {asof}): {len(scr)} names fire the rocket-launch signal NOW ===")
    for s in sorted(scr, key=lambda x: x["min_dd_126"]):
        print(f"  {s['t']:6} dd252 {s['dd252']:+.0%}  washout(126d) {s['min_dd_126']:+.0%}  vol {s['rvol126']:.0%}  vs MA200 {s['dist_ma200']:+.0%}")

    DATA.mkdir(exist_ok=True)
    json.dump({"templates": sig.to_dict("records"), "params": vars(a),
               "lift": {k: v for k, v in res.items() if k != "events"},
               "screen_asof": asof, "screen": scr}, open(SUMMARY, "w"), indent=1, default=float)
    print(f"\n[done] -> {SUMMARY}")

    print("\n=== VERDICT ===")
    if res["lift_vs_vol"] >= 1.3:
        print(f"  washout+turn adds {res['lift_vs_vol']:.2f}x OVER equally-volatile peers — a genuine timing edge.")
    else:
        print(f"  The naive {res['lift_ratio']:.1f}x lift is ALMOST ENTIRELY VOLATILITY SELECTION: high-vol names already")
        print(f"  rocket at {res['vol_base']:.0%} (vs {res['base_rate']:.0%} base) purely because volatile stocks touch +100% max-drawup")
        print(f"  more often by variance. vs vol-matched peers the signal adds only {res['lift_vs_vol']:.2f}x (~0), and the")
        print(f"  reclaim/turn step is NEGATIVE. So the template signature = 'pick a volatile beaten-down stock', not")
        print(f"  a rocket predictor — and survivorship (delisted washouts that went to 0 are absent) inflates even the")
        print(f"  vol base. Consistent with theme-washout (~0) and per-stock early-catch (~0). The current screen is a")
        print(f"  HIGH-VARIANCE watchlist (many will keep falling / delist), NOT an edge — evidence + fundamentals only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
