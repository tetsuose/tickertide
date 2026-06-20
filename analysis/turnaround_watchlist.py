"""Turnaround watchlist — an HONEST evidence-first recall funnel (NOT an edge).

This session's empirical verdict (docs/research/2026-06-edge-research.md; memories
theme-washout-no-edge / stable-momentum-beats-gainers / breakout-selection-trailing-return):
US EOD forward timing has **no robust edge** at the stock / theme / market layers.
`analysis/rocket_launch_signature.py` proved the "deep washout + high vol + reclaim 50dMA"
form is naive-1.97x but **0.97x once vol-matched** = pure volatility selection + survivorship.

So this is deliberately NOT a buy signal. It is a *recall funnel*: pull the deep-fall /
high-variance / turning names out of a broad REAL US universe as **high-variance candidates**,
expose the raw evidence as sortable columns (no single composite score that would imply edge),
and label the honest base rate loudly. Precision is the user's fundamental judgment, not the screen.
Spine-compatible: evidence-first, recall-first, never a buy/target, claims no edge (CLAUDE.md §1).

UNIVERSE (per user, 2026-06-20): broad real US equities from the Nasdaq screener with a
mktcap FLOOR + dollar-volume FLOOR (NOT top-N-by-mktcap — that caps at mega-cap land and would
have filtered the very turnaround templates, e.g. CRDO/SITM were ~$1-4B at their pre-launch washout).

CONTEXT (three-layer turbulence, for SIZING/expectation NOT direction — high vol empirically →
flat-to-HIGHER forward returns, see analysis/vix_riskoff.py):
  - market: VIX level+pct AND **VIX term structure** (VIX vs VIX3M, FRED VIXCLS/VXVCLS) — backwardation
    (VIX>VIX3M) = acute fear, historically followed by flat-to-HIGHER forward SPX (a contrarian/sizing read,
    NOT a bottom call); contango = stress fading. A better regime scalar than level.
    Honest caveat: SPX-framed, does NOT frame the small/mid turnaround names this list skews toward.
  - sector: each candidate's GICS sector realized-vol + own-history percentile (analysis/sector_vol.py recipe, ~3y window).
  - stock: the name's own realized-vol percentile (over the ~3y price lookback, not full history — see HONESTY).

Run: /Users/.../.venv/bin/python analysis/turnaround_watchlist.py [--sample N] [--probe-vix]
Outputs: stdout evidence table + honest banner; data/turnaround_watchlist.json (web-ready, gitignored).
Network required (yfinance + FRED) — run with the Bash sandbox disabled.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ingest"))
import nasdaq  # noqa: E402  (ingest/nasdaq.py — stdlib-only universe fetch)

DATA = ROOT / "data"
CACHE = DATA / "_turnaround_cache.pkl"
OUT = DATA / "turnaround_watchlist.json"
ANN = np.sqrt(252.0)


def _num(x, d: int = 3):
    """Round for JSON, mapping None/NaN/inf -> None so the artifact stays valid JSON (web consumer uses JSON.parse)."""
    return None if x is None or not np.isfinite(x) else round(float(x), d)


def load_sector_etf_map() -> dict:
    """{GICS sector name: SPDR ETF} from the canonical ingest/sector_etf_map.txt (the rotation SoT).
    fetch_universe already normalizes screener sectors to these GICS names via nasdaq._gics_sector."""
    m = {}
    for line in (ROOT / "ingest" / "sector_etf_map.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        m[" ".join(parts[:-1])] = parts[-1]
    return m


# 11 SPDR sector ETFs — the realized-vol "sector VIX" proxy (analysis/sector_vol.py recipe), GICS name → ETF.
SECTOR_ETF = load_sector_etf_map()

# Established honest base rate for this form — from analysis/rocket_launch_signature.py (full history,
# merged to main, PR #86). Regime-robust conclusions, not point estimates to trust to 0.1%.
HONESTY = {
    "headline": "This is a HIGH-VARIANCE CANDIDATE LIST, not a buy signal. It claims NO edge.",
    "real_base_rate": ("The 'deep washout + high vol + reclaim 50dMA' form's 1-year +100% rate is ~1.97x the "
                       "naive base BUT ~0.97x once vol-matched = pure volatility selection, not prediction "
                       "(high-vol names hit +100% more often by variance alone)."),
    "knife_risk": "~46% of signals keep falling >15% afterward (catch-the-knife).",
    "survivorship": "yfinance is still-listed only → the apparent hit rate is inflated (deep-fallers that went to zero are absent).",
    "form_caveat": ("The base_rate/knife figures were measured on the closest STUDIED form (min_dd_126 deepest-126d "
                    "drawdown + a STRICT same-day 50dMA reclaim, rocket_launch_signature.py). This screen's gate is a "
                    "deliberately looser RECALL net: washout keyed to dd252 (still below the 52w high now) + turn = "
                    "above-or-recently-reclaimed 50dMA. Treat them as an order-of-magnitude anchor, not an exact rate for this gate."),
    "history_bias": ("The screen also requires ~10.5 months of price history (>=220 bars) and computes the own-vol / "
                     "sector-vol percentiles over only the ~3y lookback (vs VIX's full 1990+ history) — so recently-listed "
                     "names are excluded and those percentiles are 3y-relative, compounding the still-listed survivorship skew."),
    "edge_source": "Edge comes from YOUR fundamental judgment on these names, not from the screen.",
    "source": "analysis/rocket_launch_signature.py · docs/research/2026-06-edge-research.md",
}


def fred(series: str) -> pd.Series:
    """Daily FRED series as a date-indexed float Series (no API key). Reused from analysis/sector_vol.py."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd=1990-01-01"
    df = pd.read_csv(io.StringIO(urllib.request.urlopen(url, timeout=60).read().decode()))
    df.columns = ["date", series]
    df["date"] = pd.to_datetime(df["date"])
    s = pd.to_numeric(df[series], errors="coerce")
    s.index = df["date"]
    return s.dropna()


def expand_pct(s: pd.Series, minp: int = 200) -> pd.Series:
    """Causal expanding percentile: where today's value sits vs its own NON-NaN history so far (no lookahead).
    Strips warm-up NaN inside the window so a rolling-std lead-in doesn't get counted as 'below today' and
    deflate the rank (the raw=True window otherwise includes the input series' leading NaN)."""
    def pct(a):
        cur = a[-1]
        h = a[~np.isnan(a)]
        return float((cur >= h).mean()) if (len(h) and cur == cur) else float("nan")
    return s.expanding(min_periods=minp).apply(pct, raw=True)


def rvol(close: pd.Series, k: int) -> pd.Series:
    return np.log(close).diff().rolling(k).std() * ANN


# ----------------------------------------------------------------- universe + prices

def build_universe(mktcap_floor: float) -> dict:
    """Real US equities from the Nasdaq screener with mktcap >= floor. Returns {ticker: {sector, mktcap, name}}."""
    rows = nasdaq.fetch_universe()
    uni = {}
    for r in rows:
        t, mc = r.get("ticker"), r.get("mktcap")
        if not t or mc is None or mc < mktcap_floor:
            continue
        # nasdaq.fetch_universe already drops '^'/'/' symbols upstream and dedups by max-mktcap; here we
        # additionally skip dotted/units symbols. NB: class shares (BRK/B) are excluded upstream, not recovered.
        if "." in t or any(c in t for c in "^$ "):
            continue
        uni[t] = {"sector": r.get("sector"), "mktcap": float(mc), "name": r.get("name")}
    return uni


def load_prices(tickers: list[str], lookback: str, refresh: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chunked yfinance download → (close_wide, dollarvol_wide). Cached; resilient to per-chunk failures."""
    if CACHE.exists() and not refresh:
        import pickle
        close, dv = pickle.load(open(CACHE, "rb"))
        keep = [t for t in tickers if t in close.columns]
        missing = len(tickers) - len(keep)
        if missing:
            print(f"[cache] STALE: {missing}/{len(tickers)} requested tickers absent from cache "
                  f"(built for a different/smaller run) — re-run with --refresh for the full set", flush=True)
        return close[keep], dv[keep]
    import pickle

    import yfinance as yf
    print(f"[fetch] {len(tickers)} tickers × {lookback} via yfinance (chunked) ...", flush=True)
    close_frames, dv_frames = {}, {}
    chunk = 100
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        try:
            raw = yf.download(part, period=lookback, auto_adjust=True, progress=False, threads=True)
        except Exception as e:  # noqa: BLE001 — fragile source, keep partial
            print(f"  chunk {i}: FAIL {type(e).__name__}", flush=True)
            continue
        if raw is None or len(raw) == 0:
            continue
        c = raw["Close"] if "Close" in raw else None
        v = raw["Volume"] if "Volume" in raw else None
        if isinstance(c, pd.Series):  # single-ticker chunk
            c = c.to_frame(part[0])
            v = v.to_frame(part[0]) if v is not None else None
        for t in c.columns:
            s = c[t].dropna()
            if len(s) < 220:  # need enough for dd252 / MA200
                continue
            close_frames[t] = s
            if v is not None and t in v.columns:
                # split-approximate liquidity proxy: auto_adjust close (split-adjusted) × raw volume; fine for a floor
                dv_frames[t] = (c[t] * v[t]).dropna()
        print(f"  fetched {min(i + chunk, len(tickers))}/{len(tickers)}  kept={len(close_frames)}", flush=True)
    close = pd.DataFrame(close_frames)
    dv = pd.DataFrame(dv_frames)
    for df in (close, dv):
        df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
        df.sort_index(inplace=True)
    DATA.mkdir(exist_ok=True)
    pickle.dump((close, dv), open(CACHE, "wb"))
    return close, dv


# ----------------------------------------------------------------- features

def feats(p: pd.Series) -> pd.DataFrame:
    """Causal per-date evidence features (use only data <= t). Mirrors analysis/rocket_launch_signature.py."""
    arr = p.to_numpy(dtype=float)
    n = len(arr)
    lr = np.diff(np.log(arr), prepend=np.log(arr[0]))
    f = pd.DataFrame(index=p.index)
    roll_hi = pd.Series(arr).rolling(252, min_periods=120).max().to_numpy()
    f["dd252"] = arr / roll_hi - 1.0                                              # distance from 52w high
    f["min_dd_126"] = pd.Series(f["dd252"].to_numpy()).rolling(126, min_periods=40).min().to_numpy()
    rv = pd.Series(lr).rolling(126, min_periods=60).std().to_numpy() * ANN
    f["rvol126"] = rv
    f["rvol_pct"] = expand_pct(pd.Series(rv, index=p.index)).to_numpy()           # own-vol history percentile
    ma50 = pd.Series(arr).rolling(50, min_periods=50).mean().to_numpy()
    ma200 = pd.Series(arr).rolling(200, min_periods=120).mean().to_numpy()
    f["dist_ma50"] = arr / ma50 - 1.0
    f["dist_ma200"] = arr / ma200 - 1.0
    above = arr > ma50
    f["above50"] = above.astype(float)
    f["above200"] = (arr > ma200).astype(float)
    reclaim = above & ~np.concatenate([[False], above[:-1]])                      # crossed above 50dMA today
    f["reclaim50_20d"] = pd.Series(reclaim.astype(float)).rolling(20, min_periods=1).max().to_numpy()

    def trail(h: int) -> np.ndarray:
        out = np.full(n, np.nan)
        if n > h:
            out[h:] = arr[h:] / arr[:-h] - 1.0
        return out

    f["ret_63d"], f["ret_126d"], f["ret_252d"] = trail(63), trail(126), trail(252)
    return f


# ----------------------------------------------------------------- context layers

def market_context() -> dict:
    """VIX level+pct AND VIX term structure (VIX vs VIX3M). Regime scalar for sizing/context, NOT direction.
    Degrades to a note (never raises) so a FRED hiccup can't drop the recall output after prices are fetched."""
    try:
        vix, vix3m = fred("VIXCLS"), fred("VXVCLS")
        df = pd.concat({"vix": vix, "vix3m": vix3m}, axis=1, sort=True).dropna()    # common-date (VIX3M can lag VIX)
        if df.empty:
            raise ValueError("no overlapping VIXCLS/VXVCLS dates")
        tr = df["vix"] / df["vix3m"]                                                # >1 backwardation, <1 contango
        return {
            "asof": str(df.index.max().date()),
            "vix": _num(df["vix"].iloc[-1], 2),
            "vix_pct": _num(float(expand_pct(df["vix"]).iloc[-1])),                 # percentile on the same asof-aligned series
            "vix3m": _num(df["vix3m"].iloc[-1], 2),
            "term_ratio": _num(tr.iloc[-1]),
            "term_state": "backwardation" if tr.iloc[-1] > 1.0 else "contango",
            "term_pct": _num(float(expand_pct(tr).iloc[-1])),
            "note": ("term structure (VIX/VIX3M): backwardation=acute fear, historically followed by flat-to-higher "
                     "forward SPX (contrarian/sizing read, NOT a bottom call); contango=stress fading. "
                     "Regime/sizing context, NOT a direction signal. SPX-framed — does not frame small/mid turnaround names."),
        }
    except Exception as e:  # noqa: BLE001 — context layer must never drop the recall output
        return {"asof": None, "note": f"market context unavailable ({type(e).__name__})"}


def sector_context(lookback: str) -> dict:
    """Realized-vol 'sector VIX' per SPDR ETF: annualized rv21 + own-history percentile + ratio to SPY.
    Keyed by GICS sector NAME (== candidates[*].sector) so the JSON is directly joinnable; each entry carries its etf.
    Degrades to {} (never raises) so a flaky ETF fetch can't drop the recall output."""
    import yfinance as yf
    try:
        tks = sorted(set(SECTOR_ETF.values()) | {"SPY"})
        px = yf.download(tks, period=lookback, auto_adjust=True, progress=False, threads=True)["Close"]
    except Exception:  # noqa: BLE001 — context layer must never drop the recall output
        return {}
    spy = px["SPY"].dropna() if "SPY" in px else pd.Series(dtype=float)
    spy_now = float(rvol(spy, 21).iloc[-1]) if len(spy) >= 220 else None
    out = {}
    for gics, etf in SECTOR_ETF.items():
        s = px[etf].dropna() if etf in px else pd.Series(dtype=float)
        if len(s) < 220:
            continue                              # flaky/missing ETF fetch — leave it out rather than emit nan
        rv = rvol(s, 21)
        last = float(rv.iloc[-1])
        if last != last:                          # nan guard
            continue
        out[gics] = {"etf": etf, "rv21": _num(last), "rv_pct": _num(float(expand_pct(rv).iloc[-1])),
                     "vs_spy": _num(last / spy_now, 2) if spy_now else None}
    return out


def probe_vix_term_forward() -> None:
    """Part B sanity: does VIX term structure (VIX/VIX3M) carry FORWARD content? Bucket forward SPX return by regime."""
    import yfinance as yf
    vix, vix3m = fred("VIXCLS"), fred("VXVCLS")
    spx = yf.Ticker("^GSPC").history(period="max", auto_adjust=True)["Close"].dropna()
    spx.index = pd.DatetimeIndex(spx.index).tz_localize(None).normalize()
    df = pd.concat({"vix": vix, "vix3m": vix3m, "spx": spx}, axis=1, sort=True).dropna()
    tr = (df["vix"] / df["vix3m"]).to_numpy()
    p = df["spx"].to_numpy()

    def fwd(h):
        out = np.full(len(p), np.nan)
        out[:-h] = p[h:] / p[:-h] - 1.0
        return out

    f21, f63 = fwd(21), fwd(63)
    print("\n=== part B: VIX term structure (VIX/VIX3M) forward content — context or direction? ===")
    print(f"  [data] {df.index.min().date()}..{df.index.max().date()}  n={len(df)}  current ratio={tr[-1]:.3f} "
          f"({'backwardation' if tr[-1] > 1 else 'contango'})")
    print(f"  {'regime':22}{'n':>7}{'fwd21d(ann)':>13}{'fwd63d(ann)':>13}")
    edges = [(-1, 0.90, "deep contango <0.90"), (0.90, 0.97, "contango 0.90-0.97"),
             (0.97, 1.00, "flat 0.97-1.00"), (1.00, 1.05, "backwardation 1.00-1.05"),
             (1.05, 9, "deep backwardation >1.05")]
    for lo, hi, lab in edges:
        m = (tr > lo) & (tr <= hi) & ~np.isnan(f21)
        if m.sum() < 30:
            continue
        a21 = (1 + np.nanmean(f21[m])) ** (252 / 21) - 1
        a63 = (1 + np.nanmean(f63[m])) ** (252 / 63) - 1
        print(f"  {lab:22}{int(m.sum()):>7}{a21:>12.1%}{a63:>12.1%}")
    valid = ~np.isnan(f21)
    c = np.corrcoef(tr[valid], f21[valid])[0, 1]
    print(f"  corr(term_ratio_t, forward 21d return) = {c:+.2f}  "
          f"(>0 ⇒ backwardation/fear → HIGHER forward = contrarian, same as VIX level; NOT a sell signal)")
    print("  [caveat] DESCRIPTIVE only: 21d/63d forward windows OVERLAP (autocorrelated) → effective N << printed n; "
          "no significance test/CI, bucket edges are illustrative. fwd63d(ann) averages over ~42 fewer obs than its 21d-based n.")
    print("  verdict: a regime/sizing scalar, not a direction signal for the individual turnaround names.")


# ----------------------------------------------------------------- screen

def screen(close, dv, uni, args) -> tuple[list, dict]:
    """Build the evidence rows for names passing the liquidity floor + recall gate (washout+highvol+turn)."""
    last = close.index.max()
    rows, n_liq, n_hist = [], 0, 0
    for t in close.columns:
        p = close[t].dropna()
        if len(p) < 220 or p.index.max() < last - pd.Timedelta(days=7):
            continue
        n_hist += 1
        dvol = float(dv[t].dropna().iloc[-63:].median()) if t in dv and len(dv[t].dropna()) else 0.0
        if dvol < args.dv_floor:
            continue
        n_liq += 1
        f = feats(p).iloc[-1]
        washout = f["dd252"] <= -args.wo          # STILL deeply down from 52w high (not a recovered transient dip)
        highvol = f["rvol126"] >= args.vol
        turning = (f["above50"] == 1) or (f["reclaim50_20d"] == 1)
        if not (washout and highvol and (turning or args.no_turn)):
            continue
        m = uni.get(t, {})
        rows.append({
            "ticker": t, "name": m.get("name"), "sector": m.get("sector"),
            "mktcap": m.get("mktcap"), "px": _num(p.iloc[-1], 2),
            # rvol_pct is None for sub-~259-bar names (percentile undefined) — kept in the funnel (recall-first),
            # _num maps any NaN/inf -> None so the JSON stays valid for these recent-listing turnarounds.
            "dd252": _num(f["dd252"]), "min_dd_126": _num(f["min_dd_126"]),
            "rvol126": _num(f["rvol126"]), "rvol_pct": _num(f["rvol_pct"]),
            "dist_ma50": _num(f["dist_ma50"]), "dist_ma200": _num(f["dist_ma200"]),
            "above50": bool(f["above50"]), "above200": bool(f["above200"]),
            "reclaim50_20d": bool(f["reclaim50_20d"]),
            "ret_63d": _num(f["ret_63d"]), "ret_126d": _num(f["ret_126d"]), "ret_252d": _num(f["ret_252d"]),
            "dollar_vol": int(dvol),
        })
    meta = {"universe_after_mktcap_floor": len(uni), "sampled": (getattr(args, "sample", 0) or None),
            "with_history": n_hist, "after_liquidity_floor": n_liq, "fired": len(rows),
            "params": {"mktcap_floor": args.mktcap_floor, "dv_floor": args.dv_floor,
                       "wo": args.wo, "vol": args.vol, "turn_required": not args.no_turn,
                       "lookback": args.lookback}}
    return rows, meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="Honest evidence-first turnaround recall funnel (claims no edge).")
    ap.add_argument("--mktcap-floor", type=float, default=500e6, dest="mktcap_floor",
                    help="drop names below this market cap (default $500M — avoid micro-cap garbage/bad data)")
    ap.add_argument("--dv-floor", type=float, default=3e6, dest="dv_floor",
                    help="drop names below this median 63d dollar volume (default $3M/day liquidity floor)")
    ap.add_argument("--wo", type=float, default=0.40,
                    help="washout: STILL >= wo below 52w high (dd252 <= -wo, default 40%% — anchors the studied form)")
    ap.add_argument("--vol", type=float, default=0.40, help="high-vol: annualized realized vol >= vol (default 40%%)")
    ap.add_argument("--no-turn", action="store_true", dest="no_turn",
                    help="drop the turn gate (show the full washout+highvol pool, not just turning names)")
    ap.add_argument("--lookback", default="3y", help="yfinance price history window (default 3y)")
    ap.add_argument("--sample", type=int, default=0, help="random-sample N floor-passing names (testing plumbing)")
    ap.add_argument("--refresh", action="store_true", help="ignore the price cache and re-fetch")
    ap.add_argument("--probe-vix", action="store_true", dest="probe_vix",
                    help="also run the part-B VIX term-structure forward-content probe")
    a = ap.parse_args(argv)

    uni = build_universe(a.mktcap_floor)
    print(f"[universe] {len(uni)} US names with mktcap >= ${a.mktcap_floor/1e6:.0f}M (Nasdaq screener)", flush=True)
    tickers = sorted(uni)
    if a.sample and a.sample < len(tickers):
        rng = np.random.default_rng(42)
        tickers = sorted(rng.choice(tickers, a.sample, replace=False).tolist())
        print(f"[sample] testing on {len(tickers)} random names (seed 42)", flush=True)

    close, dv = load_prices(tickers, a.lookback, a.refresh)
    if close.shape[1] == 0 or pd.isna(close.index.max()):
        print("[fatal] no usable price history fetched (empty universe or total fetch failure) — nothing written")
        return
    print(f"[prices] {close.shape[1]} names with usable history  {close.index.min().date()}..{close.index.max().date()}")

    mkt = market_context()
    sec = sector_context(a.lookback)
    rows, meta = screen(close, dv, uni, a)

    # attach each candidate's sector turbulence context (sec is keyed by GICS sector name == r["sector"])
    for r in rows:
        r["sector_ctx"] = sec.get(r["sector"]) if r["sector"] else None

    rows.sort(key=lambda r: r["dd252"])  # default sort: most washed-out first (recall intent; re-sort any column downstream)

    if mkt.get("vix") is not None:
        print(f"\n[market] VIX {mkt['vix']} (pct {mkt['vix_pct']:.0%})  VIX3M {mkt['vix3m']}  "
              f"term {mkt['term_ratio']} = {mkt['term_state']} (pct {mkt['term_pct']:.0%})")
    else:
        print(f"\n[market] {mkt.get('note')}")
    print(f"[funnel] {meta['universe_after_mktcap_floor']} → history {meta['with_history']} → "
          f"liquid {meta['after_liquidity_floor']} → fired {meta['fired']}")
    print("\n!!! HIGH-VARIANCE CANDIDATE LIST — NOT a buy signal, claims NO edge !!!")
    print(f"    {HONESTY['real_base_rate']}")
    print(f"    {HONESTY['knife_risk']}  {HONESTY['survivorship']}")
    print(f"    {HONESTY['form_caveat']}")
    print(f"    {HONESTY['history_bias']}")
    print(f"    {HONESTY['edge_source']}\n")

    hdr = f"  {'ticker':7}{'sector':16}{'mktcap$B':>9}{'dd252':>8}{'wash126':>9}{'rvol':>7}{'volPct':>8}{'vsMA50':>8}{'vsMA200':>9}{'ret126':>8}{'turn':>6}{'secRVpct':>9}"
    print(hdr)
    nz = lambda x: x if x is not None else float("nan")            # None -> nan for cosmetic %-formatting (JSON keeps null)
    for r in rows[:60]:
        turn = ("A50" if r["above50"] else "") + ("/A200" if r["above200"] else "") + ("/rc" if r["reclaim50_20d"] else "")
        scp = r["sector_ctx"]["rv_pct"] if r["sector_ctx"] else None
        print(f"  {r['ticker']:7}{(r['sector'] or '')[:15]:16}{(r['mktcap'] or 0)/1e9:>8.1f}"
              f"{r['dd252']:>+8.0%}{r['min_dd_126']:>+9.0%}{r['rvol126']:>7.0%}{nz(r['rvol_pct']):>8.0%}"
              f"{r['dist_ma50']:>+8.0%}{r['dist_ma200']:>+9.0%}{nz(r['ret_126d']):>+8.0%}{turn or '-':>6}{nz(scp):>9.0%}")
    if len(rows) > 60:
        print(f"  ... +{len(rows) - 60} more (full set in JSON)")

    DATA.mkdir(exist_ok=True)
    payload = {"asof": str(close.index.max().date()), "meta": meta, "honesty": HONESTY,
               "market_context": mkt, "sector_context": sec, "candidates": rows}
    text = json.dumps(payload, indent=1, default=float, allow_nan=False)  # allow_nan=False: surface any stray NaN, never write invalid JSON
    OUT.write_text(text)                                                  # write only after a clean serialize (old artifact survives a raise)
    print(f"\n[done] {len(rows)} candidates -> {OUT}")

    if a.probe_vix:
        probe_vix_term_forward()


if __name__ == "__main__":
    main()
