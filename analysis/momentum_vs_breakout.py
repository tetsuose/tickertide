"""Head-to-head: the validated "stable momentum" axis vs the production base→breakout engine.
Does stable-momentum COMPLEMENT (adds forward info on top of breakout), REPLACE (dominates at
matched selectivity), or is it REDUNDANT inside breakout's universe?

v2 — rebuilt after an adversarial methodology critique that caught a fatal apples-to-oranges
flaw in v1: breakout zeroes ~80% of names (admissibility gate), so taking the same COUNT from
its ~20% eligible pool = ~top-50%-of-its-pool while stable_mom = true top-10%-of-all, AND the
gate itself pre-excludes the choppy/extended names that drive deep drawdowns. So "breakout rides
smoother" in v1 was a gate + selection-depth artifact, not a ranking win. Fixes here:

  PRIMARY (decisive) — WITHIN the breakout-eligible pool (brk_strength>0), matched selectivity:
    rank that identical ~20% admissible cross-section by stable_mom, by breakout, and by a 2D
    z(stable)+z(brk) combo; take top-decile-OF-ELIGIBLE for each; compare forward ret/vol/trough
    vs the eligible-pool mean. This kills the gate + depth confounds. The real question becomes:
    does stable_mom's RANK add forward information ON TOP of breakout?  -> CONDITIONAL IC inside
    the eligible pool (stable_mom vs breakout on the SAME population, now comparable).
  Block-bootstrap CIs (contiguous date blocks, len≈h/STEP) on the stable−breakout gaps so the
  overlapping-window autocorrelation at h=63 doesn't fake significance. Regime split. h=21 is
  clean (non-overlapping at STEP=21); h=63 windows overlap ~3x -> treat its t/CI as overlap-aware.

  REFERENCE — full universe (UNEQUAL selectivity, labeled): stable_mom true top-decile vs the
  production rule brk_strength_pct>=90 (run.py:72) vs ret_5 gainers vs universe. Overlap reported
  AGAINST the random-Jaccard null (E≈k²/N): observed/null>1 => MORE aligned than chance.

DECISION RULE (per the critique): REPLACE only if stable_mom beats breakout on trough AND ret/vol
at matched selectivity across regimes with CIs excluding 0; STACK/complement only if stable_mom
has positive significant CONDITIONAL IC inside the eligible pool (or the 2D combo beats both 1D);
else REDUNDANT -> keep breakout alone.

CAVEATS: survivorship is ASYMMETRIC here (yfinance still-listed; the engines' picks differ in
prior-return profile, so the missing delisted blow-ups bias the RELATIVE gap by an unknown sign)
— trust rank-based conditional IC + within-pool excess, not absolute levels. brk_strength is
price-only (volume only feeds the unused vcp/vsurge). Research-only (analysis/), parameter-free.

Run: /Users/.../.venv/bin/python analysis/momentum_vs_breakout.py [--refresh] [--start 2005-01-01]
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from compute import breakout                # noqa: E402
import stable_momentum as sm                 # noqa: E402

DATA = ROOT / "data"
SUMMARY = DATA / "momentum_vs_breakout_summary.json"
TOPQ = 0.10
STEP = sm.STEP
MIN_HIST = sm.MIN_HIST
MIN_NAMES = sm.MIN_NAMES
MIN_ELIG = 40                                # need this many breakout-eligible names/date
ANN = sm.ANN
HORIZONS = [21, 63]
BRK_MINSEG = breakout.MINSEG + breakout.REC_LO + 5
RNG = np.random.default_rng(0)


def brk_matrix(px, start, refresh):
    cache = DATA / f"_brk_matrix_{start}.pkl"
    if cache.exists() and not refresh:
        return pickle.load(open(cache, "rb")).reindex(index=px.index, columns=px.columns)
    print(f"[brk] computing production brk_strength for {px.shape[1]} tickers ...", flush=True)
    cols = {}; t0 = time.time()
    for j, t in enumerate(px.columns):
        s = px[t].dropna()
        if len(s) < BRK_MINSEG + 5:
            continue
        g = breakout.compute_breakout(pd.DataFrame({"date": s.index, "adj_close": s.values, "volume": 0.0}))
        cols[t] = pd.Series(g["brk_strength"].values, index=pd.DatetimeIndex(g["date"]))
        if (j + 1) % 100 == 0:
            print(f"  brk {j+1}/{px.shape[1]}  {time.time()-t0:.0f}s", flush=True)
    B = pd.DataFrame(cols).reindex(px.index)
    DATA.mkdir(exist_ok=True); pickle.dump(B, open(cache, "wb"))
    print(f"[brk] done {time.time()-t0:.0f}s -> {cache.name}")
    return B


def _z(s):
    sd = s.std()
    return (s - s.mean()) / sd if sd > 0 else s * 0.0


def _block_ci(arr, blk, n_boot=2000):
    arr = np.asarray([x for x in arr if not np.isnan(x)])
    if len(arr) < 5:
        return (np.nan, np.nan, np.nan)
    blk = max(1, int(blk)); nb = int(np.ceil(len(arr) / blk))
    starts_max = len(arr) - blk
    means = []
    for _ in range(n_boot):
        if starts_max <= 0:
            means.append(arr.mean()); continue
        s = RNG.integers(0, starts_max + 1, size=nb)
        samp = np.concatenate([arr[i:i + blk] for i in s])[:len(arr)]
        means.append(samp.mean())
    return (float(arr.mean()), float(np.percentile(means, 5)), float(np.percentile(means, 95)))


def _regime(y):
    if y <= 2019:
        return "pre-2020"
    if y == 2020:
        return "2020-COVID"
    if y <= 2022:
        return "2021-22"
    return "2023-25"


def run_horizon(px, sig, B, h):
    from scipy.stats import spearmanr
    fwd = sm.build_forward(px, h)
    Bpct_all = B.rank(axis=1, pct=True) * 100.0
    dates = px.index
    form = [di for di in range(MIN_HIST, len(dates) - h - 1, STEP) if dates[di].year <= 2025]
    parts = ["slope_r2", "ker_63", "sharpe_63"]

    elig = {e: [] for e in ["stable_e", "breakout_e", "combo_e", "pool"]}
    gap_tr, gap_rv, gap_ret = [], [], []        # SM_e - BK_e per date
    cic_sm, cic_bk = [], []                      # conditional IC within eligible pool (same pop)
    full = {e: [] for e in ["stable_all", "breakout_prod", "ret_5", "universe"]}
    jacc, jnull = [], []
    reg = {}                                     # regime -> list of dicts

    for di in form:
        d = dates[di]
        fr, fv, ft = fwd["ret"].iloc[di], fwd["vol"].iloc[di], fwd["trough"].iloc[di]
        valid = fr.notna() & fv.notna()
        cur = pd.DataFrame({p: sig[p].iloc[di] for p in parts})
        cur["ret_5"] = sig["ret_5"].iloc[di]
        cur["brk_raw"] = B.iloc[di]
        cur["brk_pct"] = Bpct_all.iloc[di]
        cur = cur[valid.reindex(cur.index, fill_value=False)].dropna(subset=parts, how="all")
        if len(cur) < MIN_NAMES:
            continue
        cur["stable_mom"] = cur[parts].rank(pct=True).mean(axis=1)
        frd, fvd, ftd = fr.reindex(cur.index), fv.reindex(cur.index), ft.reindex(cur.index)

        def metr(idx):
            idx = list(idx)
            return None if not idx else {"ret": float(frd.reindex(idx).mean()),
                                         "vol": float(fvd.reindex(idx).mean()),
                                         "trough": float(ftd.reindex(idx).mean()), "n": len(idx)}

        # ---- FULL-UNIVERSE reference (UNEQUAL selectivity) ----
        n = len(cur); ntop = max(5, int(n * TOPQ))
        sm_all = set(cur["stable_mom"].sort_values(ascending=False).head(ntop).index)
        bk_prod = set(cur.index[cur["brk_pct"] >= 90])                 # production rule run.py:72
        r5 = set(cur["ret_5"].sort_values(ascending=False).head(ntop).index)
        for key, s in [("stable_all", sm_all), ("breakout_prod", bk_prod), ("ret_5", r5)]:
            m = metr(s)
            if m:
                full[key].append(m)
        full["universe"].append({"ret": float(frd.mean()), "vol": float(fvd.mean()), "trough": float(ftd.mean()), "n": n})
        if sm_all and bk_prod:
            inter = len(sm_all & bk_prod); union = len(sm_all | bk_prod)
            jacc.append(inter / union)
            e_in = len(sm_all) * len(bk_prod) / n                      # chance-expected intersection
            jnull.append(e_in / (len(sm_all) + len(bk_prod) - e_in))

        # ---- PRIMARY: within breakout-eligible pool, matched selectivity ----
        P = cur[cur["brk_raw"] > 0]
        if len(P) < MIN_ELIG:
            continue
        nE = len(P); ntopE = max(5, int(nE * TOPQ))
        frP = frd.reindex(P.index)
        sm_e = set(P["stable_mom"].sort_values(ascending=False).head(ntopE).index)
        bk_e = set(P["brk_raw"].sort_values(ascending=False).head(ntopE).index)
        combo = (_z(P["stable_mom"].rank()) + _z(P["brk_raw"].rank()))
        cb_e = set(combo.sort_values(ascending=False).head(ntopE).index)
        for key, s in [("stable_e", sm_e), ("breakout_e", bk_e), ("combo_e", cb_e)]:
            m = metr(s)
            if m:
                elig[key].append(m)
        elig["pool"].append({"ret": float(frP.mean()), "vol": float(fvd.reindex(P.index).mean()),
                             "trough": float(ftd.reindex(P.index).mean()), "n": nE})
        msm, mbk = metr(sm_e), metr(bk_e)
        if msm and mbk:
            gap_tr.append(msm["trough"] - mbk["trough"])
            gap_rv.append((msm["ret"] / msm["vol"] if msm["vol"] else np.nan) - (mbk["ret"] / mbk["vol"] if mbk["vol"] else np.nan))
            gap_ret.append(msm["ret"] - mbk["ret"])
        ok = frP.notna()
        if ok.sum() >= MIN_ELIG:
            cic_sm.append(spearmanr(P["stable_mom"][ok], frP[ok]).statistic)
            cic_bk.append(spearmanr(P["brk_raw"][ok], frP[ok]).statistic)
        rk = _regime(d.year); reg.setdefault(rk, [])
        if msm and mbk:
            reg[rk].append({"sm_tr": msm["trough"], "bk_tr": mbk["trough"], "sm_ret": msm["ret"], "bk_ret": mbk["ret"]})

    def agg(ms, k):
        a = np.array([m[k] for m in ms if m and not np.isnan(m[k])])
        return float(a.mean()) if len(a) else np.nan

    def pack(rows):
        return {e: {"ret": agg(rows[e], "ret"), "vol": agg(rows[e], "vol"), "trough": agg(rows[e], "trough"),
                    "ret_over_vol": (agg(rows[e], "ret") / agg(rows[e], "vol")) if agg(rows[e], "vol") else np.nan,
                    "n": agg(rows[e], "n"), "dates": len(rows[e])} for e in rows}

    blk = max(1, int(np.ceil(h / STEP)))
    cic_sm_a = np.array([x for x in cic_sm if not np.isnan(x)])
    cic_bk_a = np.array([x for x in cic_bk if not np.isnan(x)])
    out = {
        "horizon": h, "n_form": len(elig["pool"]), "block": blk,
        "eligible": pack(elig), "full": pack(full),
        "cond_ic": {
            "stable_mom": _block_ci(cic_sm, blk) if cic_sm else (np.nan,) * 3,
            "breakout": _block_ci(cic_bk, blk) if cic_bk else (np.nan,) * 3,
        },
        "gap_sm_minus_bk": {"trough": _block_ci(gap_tr, blk), "ret_over_vol": _block_ci(gap_rv, blk),
                            "ret": _block_ci(gap_ret, blk)},
        "overlap_full": {"jaccard": float(np.nanmean(jacc)) if jacc else np.nan,
                         "null": float(np.nanmean(jnull)) if jnull else np.nan,
                         "ratio": (float(np.nanmean(jacc)) / float(np.nanmean(jnull))) if jnull and np.nanmean(jnull) else np.nan},
        "regimes": {r: {"sm_trough": float(np.mean([x["sm_tr"] for x in v])),
                        "bk_trough": float(np.mean([x["bk_tr"] for x in v])),
                        "sm_ret": float(np.mean([x["sm_ret"] for x in v])),
                        "bk_ret": float(np.mean([x["bk_ret"] for x in v])), "dates": len(v)}
                    for r, v in sorted(reg.items()) if v},
    }
    return out


def fmt(x, d=3, pct=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "  n/a"
    return f"{x*100:+.1f}%" if pct else f"{x:+.{d}f}"


def ci(t):
    return f"{fmt(t[0])} [{fmt(t[1])},{fmt(t[2])}]"


def report(res, px, start):
    print("\n" + "=" * 96)
    print(f"STABLE-MOMENTUM vs base→breakout (v2, fair)   universe={px.shape[1]}  {start}..{px.index.max().date()}")
    print("=" * 96)
    for r in res:
        h = r["horizon"]
        print(f"\n### forward {h}d  ({r['n_form']} dates, block={r['block']}{' — h>STEP: overlap-aware CIs' if r['block']>1 else ' — clean, non-overlapping'})")
        print(f"  PRIMARY — within breakout-ELIGIBLE pool, matched selectivity (top-decile-of-eligible):")
        print(f"    {'engine':12}{'topRet':>9}{'topVol':>9}{'topTrough':>11}{'ret/vol':>9}{'exRet(vs pool)':>15}")
        E = r["eligible"]; pool = E["pool"]
        for e, lbl in [("stable_e", "stable_mom"), ("breakout_e", "breakout"), ("combo_e", "z+z combo")]:
            g = E[e]
            print(f"    {lbl:12}{fmt(g['ret'],pct=True):>9}{fmt(g['vol'],pct=True):>9}{fmt(g['trough'],pct=True):>11}"
                  f"{fmt(g['ret_over_vol'],2):>9}{fmt(g['ret']-pool['ret'],pct=True):>15}")
        print(f"    {'[pool mean]':12}{fmt(pool['ret'],pct=True):>9}{fmt(pool['vol'],pct=True):>9}{fmt(pool['trough'],pct=True):>11}"
              f"{fmt(pool['ret_over_vol'],2):>9}{'--':>15}   (eligible≈{int(pool['n'])}/date)")
        ic = r["cond_ic"]
        print(f"  CONDITIONAL IC inside eligible pool (same population => comparable):")
        print(f"    stable_mom: {ci(ic['stable_mom'])}    breakout: {ci(ic['breakout'])}   [mean, 5%, 95%] block-bootstrap")
        g = r["gap_sm_minus_bk"]
        print(f"  GAP stable_mom − breakout (matched selectivity): trough {ci(g['trough'])}  "
              f"ret/vol {ci(g['ret_over_vol'])}  ret {ci(g['ret'])}")
        o = r["overlap_full"]
        print(f"  OVERLAP (full-universe, production rule): Jaccard={fmt(o['jaccard'],2)} vs random-null {fmt(o['null'],2)}"
              f" => ratio {fmt(o['ratio'],1)}x  ({'MORE aligned than chance=redundant-leaning' if (o['ratio'] or 0)>1.3 else 'near-independent'})")
        print(f"  per-regime (within-eligible top-decile): trough & ret  stable | breakout")
        for rk, v in r["regimes"].items():
            print(f"    {rk:12} trough {fmt(v['sm_trough'],pct=True)} | {fmt(v['bk_trough'],pct=True)}   "
                  f"ret {fmt(v['sm_ret'],pct=True)} | {fmt(v['bk_ret'],pct=True)}  ({v['dates']}d)")
        F = r["full"]
        print(f"  REFERENCE — full universe (UNEQUAL selectivity): "
              f"stable_all ret {fmt(F['stable_all']['ret'],pct=True)}/trough {fmt(F['stable_all']['trough'],pct=True)} | "
              f"breakout(pct≥90) ret {fmt(F['breakout_prod']['ret'],pct=True)}/trough {fmt(F['breakout_prod']['trough'],pct=True)} | "
              f"ret_5 ret {fmt(F['ret_5']['ret'],pct=True)}/trough {fmt(F['ret_5']['trough'],pct=True)} | "
              f"universe ret {fmt(F['universe']['ret'],pct=True)}")


def verdict(res):
    print("\n" + "=" * 96)
    print("VERDICT  (decision rule: REPLACE if stable beats breakout on trough AND ret/vol at matched")
    print("selectivity, CIs exclude 0, across regimes; STACK if stable has + significant CONDITIONAL IC;")
    print("else REDUNDANT inside breakout's pool.)")
    print("=" * 96)
    for r in res:
        h = r["horizon"]; ic = r["cond_ic"]; g = r["gap_sm_minus_bk"]
        sm_ic = ic["stable_mom"]; bk_ic = ic["breakout"]
        stack = (not np.isnan(sm_ic[1])) and sm_ic[1] > 0          # 5% CI above 0
        gap_tr_pos = (not np.isnan(g["trough"][1])) and g["trough"][1] > 0   # stable shallower trough, CI>0
        gap_rv_pos = (not np.isnan(g["ret_over_vol"][1])) and g["ret_over_vol"][1] > 0
        replace = gap_tr_pos and gap_rv_pos
        cond = "STACK/complement (stable adds conditional info)" if stack else \
               ("REPLACE (stable dominates at matched selectivity)" if replace else
                "REDUNDANT inside breakout's pool — keep breakout alone")
        print(f"\n  [h={h}d] conditional IC  stable={fmt(sm_ic[0])}[{fmt(sm_ic[1])},{fmt(sm_ic[2])}]  "
              f"breakout={fmt(bk_ic[0])}[{fmt(bk_ic[1])},{fmt(bk_ic[2])}]")
        print(f"          gap(stable−breakout) trough {fmt(g['trough'][0])}[CI {fmt(g['trough'][1])},{fmt(g['trough'][2])}]"
              f"  ret/vol {fmt(g['ret_over_vol'][0],3)}[CI {fmt(g['ret_over_vol'][1],3)},{fmt(g['ret_over_vol'][2],3)}]")
        print(f"          => {cond}")
    print("\n  Read h=21 as the clean panel (non-overlapping); h=63 CIs are block-bootstrap (overlap-aware).")
    print("  Absolute levels are survivor-inflated & asymmetric — trust the conditional IC + within-pool gaps.")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--start", default="2005-01-01")
    a = ap.parse_args(argv)
    px = sm.load_prices(False)
    px = px.loc[px.index >= pd.Timestamp(a.start)]
    print(f"[panel] {px.shape[1]} names  {px.index.min().date()}..{px.index.max().date()}  rows={len(px)}")
    sig = sm.build_signals(px)
    B = brk_matrix(px, a.start, a.refresh)
    res = [run_horizon(px, sig, B, h) for h in HORIZONS]
    report(res, px, a.start)
    verdict(res)
    DATA.mkdir(exist_ok=True)
    json.dump({"universe_n": px.shape[1], "start": a.start,
               "window": [str(px.index.min().date()), str(px.index.max().date())], "results": res},
              open(SUMMARY, "w"), indent=1, default=float)
    print(f"\n[done] summary -> {SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
