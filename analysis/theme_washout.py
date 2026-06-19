"""Archetype B test: does buying a THEME/industry after a deep WASHOUT + turn-up have real
forward edge — or is the 2025 semiconductor rebound just one lucky V-bottom (n=1)?

The user's chosen direction: the NVDA/SNDK-class rockets are NOT pickable early per-stock
(forward edge ~0, proven); they launch TOGETHER off a shared sector washout (e.g. the April-2025
tariff low). So the real lever is theme/sector timing: "buy the beaten-down theme as it turns."
This script tests that premise rigorously across a CENTURY of industry washout episodes.

SUBSTRATE: Ken French 49-industry value-weighted DAILY returns (1926-2026, survivorship-FREE,
free). Hundreds of independent industry washout episodes across every regime — the only way to
tell a real timing edge from the single 2025 draw.

SIGNAL (causal): industry is "washed out + turning" at date t when
  (a) it had a >= DD_THRESH drawdown-from-trailing-1y-high within the last ~quarter, AND
  (b) it RECLAIMS its 50-day MA today (crossed above from below) — the turn confirmation.
Dedup: >= H days between signals per industry (non-overlapping forward windows).

TEST: forward H-day industry return after the signal vs that industry's UNCONDITIONAL mean
forward H-day return (within-industry baseline, controls for industry drift). LIFT = event - base.
Reported pooled + by decade (regime dependence) with block-bootstrap CIs. Plus a KNIFE diagnostic
(how deep does it still fall AFTER the signal — did we catch a falling knife?) and an ablation:
washout WITHOUT the turn-confirmation (catch-the-knife) vs WITH it.

HONEST PRIORS: "buy the dip" has an oversold-bounce edge but is regime-dependent — it pays in
V-bottoms (2009/2020/2025) and bleeds in grinding bears (2000-02/2008/2022, catching knives).
The century of episodes will show whether the net edge is real and robust or V-bottom-concentrated.

Run: /Users/.../.venv/bin/python analysis/theme_washout.py [--refresh] [--dd 0.35] [--h 126]
Outputs: stdout report + data/theme_washout_summary.json
"""
from __future__ import annotations

import argparse
import io
import json
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "_ff49_daily.pkl"
SUMMARY = DATA / "theme_washout_summary.json"
FF_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/49_Industry_Portfolios_daily_CSV.zip"
RNG = np.random.default_rng(0)
TECHISH = ["Chips", "Hardw", "Softw", "LabEq", "Telcm"]   # for the semis-relevant readout


def load_ff(refresh: bool) -> pd.DataFrame:
    if CACHE.exists() and not refresh:
        return pickle_load(CACHE)
    raw = urllib.request.urlopen(FF_URL, timeout=120).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    txt = z.read(z.namelist()[0]).decode("latin-1").splitlines()
    # locate the Value-Weighted daily block
    start = next(i for i, l in enumerate(txt) if "Average Value Weighted Returns -- Daily" in l)
    hdr = txt[start + 1]
    cols = [c.strip() for c in hdr.split(",")][1:]
    cols = [c for c in cols if c]
    rows, dates = [], []
    for l in txt[start + 2:]:
        cell = l.split(",")
        d = cell[0].strip()
        if not (len(d) == 8 and d.isdigit()):
            break                                   # end of VW block (blank / next header)
        vals = [float(x) for x in cell[1:1 + len(cols)]]
        dates.append(d); rows.append(vals)
    df = pd.DataFrame(rows, columns=cols, index=pd.to_datetime(dates, format="%Y%m%d"))
    df = df.replace([-99.99, -999.0], np.nan)
    DATA.mkdir(exist_ok=True)
    import pickle
    pickle.dump(df, open(CACHE, "wb"))
    return df


def pickle_load(p):
    import pickle
    return pickle.load(open(p, "rb"))


def prices_from_returns(ret: pd.DataFrame) -> pd.DataFrame:
    return (1.0 + ret / 100.0).cumprod()


def signal_and_eval(px: pd.DataFrame, dd_thr: float, h: int, embargo: int, require_turn: bool):
    """Return per-event records: industry, date, fwd_ret, fwd_trough(after signal), industry-baseline fwd."""
    events = []
    base_by_ind = {}
    for ind in px.columns:
        p = px[ind].dropna()
        if len(p) < 252 + h + 5:
            continue
        arr = p.to_numpy(); dts = p.index
        roll_hi = pd.Series(arr).rolling(252, min_periods=200).max().to_numpy()
        dd = arr / roll_hi - 1.0
        ma50 = pd.Series(arr).rolling(50, min_periods=50).mean().to_numpy()
        dd_min_63 = pd.Series(dd).rolling(63, min_periods=20).min().to_numpy()
        fwd = np.concatenate([arr[h:] / arr[:-h] - 1.0, np.full(h, np.nan)])
        # forward trough from t (worst drawdown experienced AFTER buying)
        fwd_trough = np.full(len(arr), np.nan)
        for t in range(len(arr) - h):
            seg = arr[t:t + h + 1]
            fwd_trough[t] = seg.min() / arr[t] - 1.0
        base_by_ind[ind] = np.nanmean(fwd[:len(fwd) - h]) if len(fwd) > h else np.nan
        washed = dd_min_63 <= -dd_thr
        reclaim = (arr > ma50) & (np.concatenate([[False], arr[:-1] <= ma50[:-1]]))
        sig = washed & (reclaim if require_turn else True)
        last = -10 ** 9
        for t in np.where(sig)[0]:
            if t < 252 or t >= len(arr) - h:
                continue
            if t - last < h + embargo:
                continue
            last = t
            events.append({"ind": ind, "date": str(dts[t].date()), "year": int(dts[t].year),
                           "fwd": float(fwd[t]), "fwd_trough": float(fwd_trough[t]),
                           "base": float(base_by_ind[ind]), "dd": float(dd[t])})
    return events


def block_ci(arr, blk=4, nb=2000):
    a = np.array([x for x in arr if not np.isnan(x)])
    if len(a) < 5:
        return (np.nan, np.nan, np.nan)
    nblk = int(np.ceil(len(a) / blk)); hi = max(1, len(a) - blk)
    means = []
    for _ in range(nb):
        s = RNG.integers(0, hi, size=nblk)
        means.append(np.concatenate([a[i:i + blk] for i in s])[:len(a)].mean())
    return (float(a.mean()), float(np.percentile(means, 5)), float(np.percentile(means, 95)))


def summarize(events, label):
    if not events:
        return {"label": label, "n": 0}
    fwd = np.array([e["fwd"] for e in events])
    lift = np.array([e["fwd"] - e["base"] for e in events])
    trough = np.array([e["fwd_trough"] for e in events])
    m, lo, hiq = block_ci(lift)
    return {"label": label, "n": len(events),
            "fwd_mean": float(fwd.mean()), "fwd_med": float(np.median(fwd)),
            "lift_mean": m, "lift_ci": [lo, hiq],
            "p_fwd_gt30": float((fwd > 0.30).mean()), "p_fwd_neg": float((fwd < 0).mean()),
            "knife_med_trough": float(np.median(trough)),
            "knife_p_worse_than_-15": float((trough < -0.15).mean())}


def by_decade(events):
    out = {}
    for e in events:
        dec = (e["year"] // 10) * 10
        out.setdefault(dec, []).append(e["fwd"] - e["base"])
    return {int(d): {"n": len(v), "lift_mean": float(np.mean(v)),
                     "lift_pos_frac": float(np.mean([x > 0 for x in v]))} for d, v in sorted(out.items())}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--dd", type=float, default=0.35)
    ap.add_argument("--h", type=int, default=126)
    ap.add_argument("--embargo", type=int, default=21)
    a = ap.parse_args(argv)
    ret = load_ff(a.refresh)
    px = prices_from_returns(ret)
    print(f"[ff49] {ret.shape[1]} industries  {ret.index.min().date()}..{ret.index.max().date()}  rows={len(ret)}")
    print(f"[def] washout = >= {a.dd:.0%} drawdown in last quarter; signal = +reclaim 50d MA; forward {a.h}d; "
          f"baseline = within-industry unconditional mean fwd")

    ev_turn = signal_and_eval(px, a.dd, a.h, a.embargo, require_turn=True)
    ev_noturn = signal_and_eval(px, a.dd, a.h, a.embargo, require_turn=False)
    s_turn = summarize(ev_turn, "washout+turn(reclaim 50dMA)")
    s_knife = summarize(ev_noturn, "washout only (catch-the-knife)")

    print("\n=== headline (does washout+turn beat the industry's own unconditional forward return?) ===")
    for s in (s_turn, s_knife):
        if s["n"] == 0:
            print(f"  {s['label']}: no events"); continue
        print(f"  {s['label']}: n={s['n']}")
        print(f"     fwd {a.h}d: mean {s['fwd_mean']:+.1%}  median {s['fwd_med']:+.1%}  P(>+30%) {s['p_fwd_gt30']:.0%}  P(<0) {s['p_fwd_neg']:.0%}")
        print(f"     LIFT vs own baseline: mean {s['lift_mean']:+.1%}  [CI {s['lift_ci'][0]:+.1%}, {s['lift_ci'][1]:+.1%}]")
        print(f"     knife: median forward-trough {s['knife_med_trough']:+.1%}  P(still falls >15% after buy) {s['knife_p_worse_than_-15']:.0%}")

    print("\n=== by decade (regime dependence of washout+turn LIFT) ===")
    dec = by_decade(ev_turn)
    print(f"    {'decade':8}{'n':>5}{'liftMean':>10}{'pos%':>7}")
    for d, v in dec.items():
        print(f"    {d:<8}{v['n']:>5}{v['lift_mean']*100:>+9.1f}%{v['lift_pos_frac']*100:>6.0f}%")

    # tech-ish industries readout (the semis-relevant view, incl. the 2025 wave)
    print("\n=== tech-ish industries (Chips/Hardw/Softw/LabEq/Telcm) washout+turn events since 2015 ===")
    techev = [e for e in ev_turn if e["ind"] in TECHISH and e["year"] >= 2015]
    for e in sorted(techev, key=lambda x: x["date"]):
        print(f"    {e['date']} {e['ind']:6} dd@signal {e['dd']:+.0%}  fwd{a.h}d {e['fwd']:+.1%}  (base {e['base']:+.1%}, lift {e['fwd']-e['base']:+.1%})")

    DATA.mkdir(exist_ok=True)
    json.dump({"dd": a.dd, "h": a.h, "turn": s_turn, "knife": s_knife, "by_decade": dec,
               "n_industries": ret.shape[1], "window": [str(ret.index.min().date()), str(ret.index.max().date())]},
              open(SUMMARY, "w"), indent=1, default=float)
    print(f"\n[done] -> {SUMMARY}")

    # verdict
    print("\n=== VERDICT ===")
    t = s_turn
    real = (t["n"] >= 30) and (t["lift_ci"][0] > 0)
    pos_decades = np.mean([1 if v["lift_mean"] > 0 else 0 for v in dec.values()]) if dec else 0
    print(f"  washout+turn LIFT = {t['lift_mean']:+.1%} [CI {t['lift_ci'][0]:+.1%},{t['lift_ci'][1]:+.1%}], "
          f"positive in {pos_decades:.0%} of decades, n={t['n']}")
    if real and pos_decades >= 0.6:
        print("  => REAL & regime-robust edge: 'buy the theme on a post-washout turn' has forward lift across a century.")
    elif t["lift_ci"][0] > 0:
        print("  => Edge present on average but regime-dependent — check which decades carry it (knife risk in grinding bears).")
    else:
        print("  => NO reliable edge (CI crosses 0): the 2025 semi rebound is not a generalizable timing signal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
