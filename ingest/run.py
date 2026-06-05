"""M0 ingest orchestrator: universe (Nasdaq) -> daily_bars (price provider) -> spx_daily.

Usage:
    python3 ingest/run.py [--provider yfinance|stooq] [--limit 500]
                          [--lookback-days 760] [--db data/tickertide.duckdb]

M0 "go narrow": store the full universe (cheap, one JSON), but pull bars only for
the top-N by mktcap UNION the theme seed list (bars are the slow part). Scale to
the full universe is M6.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT))

import nasdaq  # noqa: E402
import prices  # noqa: E402
from compute import db  # noqa: E402

SEED_FILE = ROOT / "ingest" / "universe_seed.txt"
BENCHMARK = "^GSPC"


def load_seed() -> list[str]:
    if not SEED_FILE.exists():
        return []
    out = []
    for line in SEED_FILE.read_text().splitlines():
        line = line.split("#", 1)[0].strip().upper()
        if line:
            out.append(line)
    return out


def pick_bars_tickers(universe: list[dict], limit: int, seed: list[str]) -> list[str]:
    ranked = sorted((u for u in universe if u.get("mktcap")), key=lambda u: -u["mktcap"])
    top = [u["ticker"] for u in ranked[:limit]]
    # Seed first so theme reps are guaranteed in; dedup preserving order.
    return list(dict.fromkeys(seed + top))


def main() -> int:
    ap = argparse.ArgumentParser(description="TickerTide M0 ingest: universe + price bars.")
    ap.add_argument("--provider", default="yfinance", help="yfinance (default) | stooq")
    ap.add_argument("--limit", type=int, default=500, help="top-N by mktcap to pull bars for")
    ap.add_argument("--lookback-days", type=int, default=760, help="~3y of calendar days")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    args = ap.parse_args()

    today = date.today().isoformat()
    con = db.connect(args.db)

    print(f"[universe] fetching Nasdaq screener ({', '.join(nasdaq.EXCHANGES)}) ...")
    uni = nasdaq.fetch_universe()
    n_uni = db.upsert_universe(con, uni, today)
    print(f"[universe] stored {n_uni} US-listed tickers")

    seed = load_seed()
    tickers = pick_bars_tickers(uni, args.limit, seed)
    print(f"[bars] provider={args.provider} targets={len(tickers)} (seed={len(seed)} + top {args.limit})")

    provider = prices.get_provider(args.provider)
    ok = skipped = 0
    for i, t in enumerate(tickers, 1):
        try:
            bars = provider.get_bars(t, args.lookback_days)
            if bars:
                db.upsert_bars(con, t, bars)
                ok += 1
            else:
                skipped += 1
        except Exception as e:  # provider/network flakiness is expected (esp. yfinance)
            skipped += 1
            print(f"  [skip] {t}: {type(e).__name__}: {str(e)[:80]}")
        if i % 50 == 0:
            print(f"  ... {i}/{len(tickers)} (ok={ok} skip={skipped})")

    print(f"[bars] done ok={ok} skipped={skipped}")

    try:
        spx = provider.get_bars(BENCHMARK, args.lookback_days)
        n_spx = db.upsert_spx(con, spx)
        print(f"[spx] {BENCHMARK} stored {n_spx} rows")
    except Exception as e:
        print(f"[spx] failed: {type(e).__name__}: {str(e)[:80]}")

    print(
        f"[summary] universe={db.count(con,'universe')} "
        f"bar_tickers={db.distinct_bar_tickers(con)} "
        f"bars={db.count(con,'daily_bars')} spx={db.count(con,'spx_daily')}"
    )
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
