"""Precision pass: do ignition top-decile lights actually continue UP, or fizzle?

The timing back-look (analysis/verify_ignition.py) proved ignition surfaces 4
hand-picked winners early. That says nothing about FALSE POSITIVES. This asks the
honest question on a neutral, non-cherry-picked池: when ignition puts a name in the
universe top decile, what happens NEXT — and is it better than buying a random day?

Method:
  1. Universe = random 800 of the 3571 Nasdaq names in the $0.3B-$100B emerging-leader
     habitat (fixed seed) + the 4 targets + SPY. Not survivorship-clean (yfinance only
     has still-listed names) — see CAVEAT.
  2. ignition: SAME 5 short-window components + cross-sectional top-decile rule as the
     timing back-look (reused verbatim from verify_ignition.ignition_metrics).
  3. Ignition EVENT = the day a name crosses from <90 to >=90 pct (entry, not every day
     it sits there — avoids counting one move many times).
  4. For each event, forward return over 20/60/120 trading days, RELATIVE to SPY.
  5. base rate = the SAME forward-relative return on ALL stock-days (what a random entry
     gets). The signal's value = event return minus base return (the LIFT), not the raw
     hit-rate (a bull-market tide lifts everything).

Output: events table (event vs base: median / mean / hit-rate at +0/+10/+25% rel) and a
JSON of the forward-return distributions for plotting.
"""
from __future__ import annotations

import json
import random
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT / "analysis"))
from verify_ignition import ignition_metrics  # noqa: E402  (reuse the SAME ignition math)
import nasdaq  # noqa: E402

TARGETS = ["ARM", "MRVL", "AAOI", "SNDK"]
BENCH = "SPY"
HAB_LO, HAB_HI = 3e8, 1e11      # emerging-leader market-cap habitat
SAMPLE_N = 800
SEED = 42
START = "2023-01-01"
TOP = 90.0                      # top decile = "lit"
FWD = [20, 60, 120]            # forward windows (trading days)
THRESH = [0.0, 0.10, 0.25]     # success = forward return vs SPY exceeds this
IG_COMPS = ["ig_accel", "ig_expand", "ig_vsurge", "ig_breakout", "ig_rsturn"]
CACHE = ROOT / "data" / "_precision_cache.pkl"
OUT = ROOT / "data" / "precision_ignition_out.json"


def pick_universe() -> list[str]:
    uni = nasdaq.fetch_universe()
    hab = [u["ticker"] for u in uni
           if u.get("mktcap") and HAB_LO <= u["mktcap"] < HAB_HI
           and u["ticker"].isalpha() and len(u["ticker"]) <= 5]
    sample = random.Random(SEED).sample(hab, min(SAMPLE_N, len(hab)))
    return list(dict.fromkeys(TARGETS + sample))


def fetch_many(tickers: list[str]) -> dict[str, pd.DataFrame]:
    import pickle
    if CACHE.exists():
        print("[fetch] cache hit")
        return pickle.load(open(CACHE, "rb"))
    import yfinance as yf
    out, allt, B = {}, tickers + [BENCH], 200
    for i in range(0, len(allt), B):
        batch = allt[i:i + B]
        print(f"[fetch] batch {i//B+1}/{(len(allt)+B-1)//B} ({len(batch)} names) ...")
        try:
            df = yf.download(batch, start=START, auto_adjust=False, progress=False, threads=True)
        except Exception as e:
            print(f"  batch fail: {type(e).__name__}: {str(e)[:80]}")
            continue
        adj, vol = df["Adj Close"], df["Volume"]
        for t in batch:
            if t not in adj:
                continue
            s = pd.DataFrame({"adj_close": adj[t], "volume": vol[t]}).dropna(subset=["adj_close"])
            if len(s) < 260:
                continue
            s = s.reset_index().rename(columns={"Date": "date"})
            s["date"] = pd.to_datetime(s["date"])
            out[t] = s
    pickle.dump(out, open(CACHE, "wb"))
    print(f"[fetch] usable names = {len(out)}")
    return out


def main() -> int:
    tk = pick_universe()
    print(f"[universe] sampled {len(tk)} habitat names (+SPY), seed={SEED}")
    data = fetch_many(tk)
    if BENCH not in data:
        raise RuntimeError("benchmark SPY missing")
    spy_px = data[BENCH].set_index("date")["adj_close"]

    frames = []
    for t, bars in data.items():
        if t == BENCH:
            continue
        b = bars.sort_values("date").reset_index(drop=True)
        px = b["adj_close"].astype(float)
        g = ignition_metrics(b, data[BENCH][["date", "adj_close"]])
        rec = pd.DataFrame({"ticker": t, "date": b["date"].values})
        for c in IG_COMPS:
            rec[c] = g[c].values
        spa = pd.Series(spy_px.reindex(b["date"], method="ffill").to_numpy(), index=b.index)
        for N in FWD:
            fwd_stock = px.shift(-N) / px - 1
            fwd_spy = spa.shift(-N) / spa - 1
            rec[f"fwd{N}"] = (fwd_stock - fwd_spy).values   # forward return RELATIVE to SPY
        frames.append(rec)
    long = pd.concat(frames, ignore_index=True)

    # cross-sectional ignition (same recipe as the timing back-look)
    for c in IG_COMPS:
        long[c + "_p"] = long.groupby("date")[c].rank(pct=True)
    long["ignition"] = long[[c + "_p" for c in IG_COMPS]].mean(axis=1)
    long["ign_pct"] = long.groupby("date")["ignition"].rank(pct=True) * 100

    long = long.sort_values(["ticker", "date"]).reset_index(drop=True)
    for N in FWD:                                   # clip penny-stock split inf (median is robust; this fixes mean)
        long[f"fwd{N}"] = long[f"fwd{N}"].clip(-0.95, 10.0)
    long["prev"] = long.groupby("ticker")["ign_pct"].shift(1)
    long["fut5"] = long.groupby("ticker")["ign_pct"].shift(-5)   # still lit 5 days later?

    # entry events at escalating strength + a persistence filter
    long["e_top10"] = (long["ign_pct"] >= 90) & (long["prev"] < 90)
    long["e_top5"]  = (long["ign_pct"] >= 95) & (long["prev"] < 95)
    long["e_top1"]  = (long["ign_pct"] >= 99) & (long["prev"] < 99)
    long["e_persist"] = long["e_top10"] & (long["fut5"] >= 90)    # crossed in AND stayed in 5d

    VARIANTS = [("top10% entry", "e_top10"), ("top5% entry", "e_top5"),
                ("top1% entry", "e_top1"), ("top10% + persist 5d", "e_persist")]
    n_days = long["date"].nunique()
    print(f"\n[stats] stock-days={len(long):,}  names={long['ticker'].nunique()}  trading-days={n_days}")

    def stat(mask, N):
        e = long.loc[mask, f"fwd{N}"].dropna()
        base = long[f"fwd{N}"].dropna()
        return (int(len(e)), float(e.median()), float(base.median()),
                float(e.median() - base.median()), float((e > 0.10).mean()), float((base > 0.10).mean()))

    print("\n=====  IGNITION forward return vs SPY, by signal strength (median LIFT = the honest read)  =====")
    print(f"{'variant':22} {'win':>4} {'n':>6} | {'EVENT med':>10} {'base med':>9} {'LIFT':>7} | {'evt>+10%':>8} {'base':>6}")
    rows = []
    for name, col in VARIANTS:
        for N in FWD:
            n, em, bm, lift, ep, bp = stat(long[col], N)
            rows.append({"variant": name, "N": N, "n": n, "ev_med": em, "base_med": bm,
                         "lift": lift, "ev_p10": ep, "base_p10": bp})
            print(f"{name if N==FWD[0] else '':22} {N:>3}d {n:>6} | {em*100:>+9.1f}% {bm*100:>+8.1f}% "
                  f"{lift*100:>+6.1f}pp | {ep*100:>7.0f}% {bp*100:>5.0f}%")

    # do the 4 known winners' OWN ignition events actually rip? (recall sanity)
    print("\n=====  the 4 targets' top10% entries (recall:信号能抓到, 即便被假阳性稀释)  =====")
    tgt = long[long["e_top10"] & long["ticker"].isin(TARGETS)]
    for t in TARGETS:
        e = tgt[tgt["ticker"] == t]
        if len(e):
            print(f"  {t:5} events={len(e):2}  60d-fwd median={e['fwd60'].median()*100:+.0f}%  "
                  f"max={e['fwd60'].max()*100:+.0f}%  share>+10%={(e['fwd60']>0.10).mean()*100:.0f}%")

    print("\nCAVEAT: yfinance = still-listed only → survivorship inflates BOTH columns; LIFT survives it.")
    print("2023-26 AI bull → high base; habitat median actually LAGS SPY (few winners carry the mean).")

    base60 = long["fwd60"].dropna()
    dump = {
        "rows": rows, "n_names": int(long["ticker"].nunique()),
        "ev10_fwd60": [round(float(x), 4) for x in long.loc[long["e_top10"], "fwd60"].dropna().tolist()],
        "ev1_fwd60": [round(float(x), 4) for x in long.loc[long["e_top1"], "fwd60"].dropna().tolist()],
        "base_fwd60_sample": [round(float(x), 4) for x in
                              base60.sample(min(8000, len(base60)), random_state=SEED).tolist()],
    }
    OUT.write_text(json.dumps(dump, separators=(",", ":")))
    print(f"\n[out] {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
