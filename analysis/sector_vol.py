"""Per-sector "VIX" (realized-volatility index) for the 11 GICS sector ETFs.

A TRUE VIX is option-implied and needs an options-chain history we don't have free. The honest,
computable analog is REALIZED volatility per sector (VIX ~= realized vol + variance risk premium),
which is exactly the right input for the established uses: position SIZING / vol-targeting, and
high-vol-regime CONTEXT (NOT direction — see analysis/vix_riskoff.py).

For each SPDR sector ETF: annualized realized vol (21d & 63d), its causal EXPANDING percentile
(where today sits vs the sector's own history), its ratio to SPY's vol (relative turbulence), and
a sanity corr against the market VIX. Survivorship-immune (ETFs reconstitute). Daily, full history.

Run: /Users/.../.venv/bin/python analysis/sector_vol.py
Outputs: stdout table + data/sector_vol_summary.json (current sector-vol snapshot for the UI)
"""
from __future__ import annotations
import io, json, urllib.request
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]; DATA = ROOT / "data"
ANN = np.sqrt(252.0)
SECTORS = {"XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Health Care",
           "XLY": "Cons Disc", "XLP": "Cons Staples", "XLI": "Industrials", "XLB": "Materials",
           "XLU": "Utilities", "XLRE": "Real Estate", "XLC": "Comm Svcs"}


def fred(series):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd=1990-01-01"
    df = pd.read_csv(io.StringIO(urllib.request.urlopen(url, timeout=60).read().decode()))
    df.columns = ["date", series]; df["date"] = pd.to_datetime(df["date"])
    s = pd.to_numeric(df[series], errors="coerce"); s.index = df["date"]; return s.dropna()


def rvol(close: pd.Series, k: int) -> pd.Series:
    return np.log(close).diff().rolling(k).std() * ANN


def expand_pct(s: pd.Series, minp=252) -> pd.Series:
    return s.expanding(min_periods=minp).apply(lambda a: (a[-1] >= a).mean(), raw=True)


def main():
    import yfinance as yf
    tks = list(SECTORS) + ["SPY"]
    px = yf.download(tks, period="max", auto_adjust=True, progress=False, threads=True)["Close"]
    px.index = pd.DatetimeIndex(px.index).tz_localize(None)
    vix = fred("VIXCLS").reindex(px.index).ffill(limit=3)
    spy_rv21 = rvol(px["SPY"], 21)

    rows = []
    asof = px.dropna(how="all").index.max()
    for etf, name in SECTORS.items():
        s = px[etf].dropna()
        if len(s) < 300:
            continue
        rv21 = rvol(s, 21); rv63 = rvol(s, 63)
        pct = expand_pct(rv21)
        cur = float(rv21.reindex([asof]).iloc[0]) if asof in rv21.index else float(rv21.dropna().iloc[-1])
        cur_pct = float(pct.dropna().iloc[-1])
        # ratio to SPY vol now; corr of sector rv with VIX over common history
        ratio = cur / float(spy_rv21.reindex([asof]).ffill().iloc[0])
        common = pd.DataFrame({"rv": rv21, "vix": vix}).dropna()
        c = float(np.corrcoef(common["rv"], common["vix"])[0, 1]) if len(common) > 100 else np.nan
        lo1y = float(rv21.iloc[-252:].min()); hi1y = float(rv21.iloc[-252:].max())
        rows.append({"etf": etf, "name": name, "rv21": cur, "rv21_pct": cur_pct,
                     "rv63": float(rv63.dropna().iloc[-1]), "ratio_spy": ratio,
                     "corr_vix": c, "lo1y": lo1y, "hi1y": hi1y, "start": str(s.index.min().date())})
    rows.sort(key=lambda r: -r["rv21_pct"])

    spy_now = float(spy_rv21.dropna().iloc[-1]); vix_now = float(vix.dropna().iloc[-1])
    print(f"[asof] {asof.date()}   market: SPY realized-vol(21d) {spy_now:.0%}   VIX {vix_now:.1f}")
    print("[note] realized-vol 'sector VIX' (option-implied VIX needs options history we lack). corr_vix = "
          "how well each sector's realized vol tracks the market VIX.\n")
    print(f"  {'sector':14}{'ETF':5}{'rvol21(ann)':>12}{'vs own hist':>12}{'rvol63':>9}{'vs SPY':>8}{'1y range':>14}{'corrVIX':>9}")
    for r in rows:
        print(f"  {r['name']:14}{r['etf']:5}{r['rv21']*100:>11.0f}%{r['rv21_pct']*100:>11.0f}%{r['rv63']*100:>8.0f}%"
              f"{r['ratio_spy']:>7.2f}x{(str(round(r['lo1y']*100))+'-'+str(round(r['hi1y']*100))+'%'):>14}{r['corr_vix']:>8.2f}")

    DATA.mkdir(exist_ok=True)
    json.dump({"asof": str(asof.date()), "spy_rv21": spy_now, "vix": vix_now, "sectors": rows},
              open(DATA / "sector_vol_summary.json", "w"), indent=1, default=float)
    print(f"\n[done] -> {DATA / 'sector_vol_summary.json'}")
    print("\n[use] per the VIX finding: read these as TURBULENCE / position-SIZING context, NOT direction.")
    print("  high sector vol pct = expect bigger swings there (size smaller); it does NOT mean 'sell that sector'")
    print("  (high vol -> flat-to-higher forward returns). Same recipe works on a THEME basket's index returns.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
