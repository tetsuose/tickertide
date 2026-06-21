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


def pick_bars_tickers(universe: list[dict], limit: int, seed: list[str],
                      min_mktcap: float | None = None) -> list[str]:
    """Which tickers to pull bars for. Two modes:
      - FLOOR (M6, --min-mktcap set): every name with mktcap >= floor. This is the
        scale-out selection — it does NOT cap out at the largest N, so small/mid-caps
        (where the big surprise run-ups live) are included. Sorted by mktcap desc so
        the heaviest paint/compute first.
      - TOP-N (M0 default): the top `limit` by mktcap (bars are the slow part). Kept for
        narrow/dev runs.
    Both UNION the theme seed list first (reps guaranteed in), dedup preserving order."""
    ranked = sorted((u for u in universe if u.get("mktcap")), key=lambda u: -u["mktcap"])
    if min_mktcap is not None:
        picked = [u["ticker"] for u in ranked if u["mktcap"] >= min_mktcap]
    else:
        picked = [u["ticker"] for u in ranked[:limit]]
    return list(dict.fromkeys(seed + picked))


def main() -> int:
    ap = argparse.ArgumentParser(description="TickerTide M0 ingest: universe + price bars.")
    ap.add_argument("--provider", default="yfinance", help="yfinance (default) | stooq")
    ap.add_argument("--limit", type=int, default=500, help="top-N by mktcap (when --min-mktcap unset)")
    ap.add_argument("--min-mktcap", type=float, default=None,
                    help="M6 floor mode: pull bars for ALL names with mktcap >= this (USD). "
                         "e.g. 5e8 = $500M floor (~3.3k names). Overrides --limit.")
    ap.add_argument("--lookback-days", type=int, default=760, help="~3y of calendar days")
    ap.add_argument("--no-batch", action="store_true",
                    help="force per-ticker fetch even if the provider supports batch")
    ap.add_argument("--skip-splits", action="store_true",
                    help="skip per-ticker splits fetch (faster scale-out; split-alignment "
                         "degrades to factor 1.0 — fine for price-only Breakouts detection)")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    args = ap.parse_args()

    today = date.today().isoformat()
    con = db.connect(args.db)

    print(f"[universe] fetching Nasdaq screener ({', '.join(nasdaq.EXCHANGES)}) ...")
    uni = nasdaq.fetch_universe()
    n_uni = db.upsert_universe(con, uni, today)
    print(f"[universe] stored {n_uni} US-listed tickers")

    seed = load_seed()
    tickers = pick_bars_tickers(uni, args.limit, seed, args.min_mktcap)
    sel = f"mktcap>=${args.min_mktcap:,.0f}" if args.min_mktcap else f"top {args.limit}"
    print(f"[bars] provider={args.provider} targets={len(tickers)} (seed={len(seed)} + {sel})")

    provider = prices.get_provider(args.provider)
    use_batch = (not args.no_batch) and hasattr(provider, "get_bars_batch")
    ok = skipped = n_splits = 0

    if use_batch:
        # Scale path (M6): one threaded HTTP batch per chunk instead of one per ticker.
        print(f"[bars] batch mode ({args.provider}.get_bars_batch) ...", flush=True)
        bars_by = provider.get_bars_batch(tickers, args.lookback_days)
        for t in tickers:
            bars = bars_by.get(t)
            if bars:
                db.upsert_bars(con, t, bars)
                ok += 1
            else:
                skipped += 1
        print(f"[bars] batch fetched ok={ok} skipped={skipped}")
        if not args.skip_splits:
            # Splits keep EDGAR per-share fundamentals in the SAME split basis as the
            # (split-adjusted) bars (PRD §10.5). Still per-ticker (Yahoo has no batch
            # splits); only for names we actually stored bars for. Skippable for a fast
            # price-only first cut (degrades to factor 1.0).
            for i, t in enumerate(t for t in tickers if bars_by.get(t)):
                try:
                    sp = provider.get_splits(t)
                    if sp:
                        n_splits += db.upsert_splits(con, t, sp)
                except Exception as e:
                    print(f"  [splits skip] {t}: {type(e).__name__}: {str(e)[:60]}")
                if (i + 1) % 200 == 0:
                    print(f"  ... splits {i+1} (n_splits={n_splits})", flush=True)
            print(f"[splits] done n_splits={n_splits}")
    else:
        for i, t in enumerate(tickers, 1):
            try:
                bars = provider.get_bars(t, args.lookback_days)
                if bars:
                    db.upsert_bars(con, t, bars)
                    ok += 1
                    if not args.skip_splits:
                        try:
                            sp = provider.get_splits(t)
                            if sp:
                                n_splits += db.upsert_splits(con, t, sp)
                        except Exception as e:
                            print(f"  [splits skip] {t}: {type(e).__name__}: {str(e)[:60]}")
                else:
                    skipped += 1
            except Exception as e:  # provider/network flakiness is expected (esp. yfinance)
                skipped += 1
                print(f"  [skip] {t}: {type(e).__name__}: {str(e)[:80]}")
            if i % 50 == 0:
                print(f"  ... {i}/{len(tickers)} (ok={ok} skip={skipped} splits={n_splits})")
        print(f"[bars] done ok={ok} skipped={skipped} splits={n_splits}")

    try:
        spx = provider.get_bars(BENCHMARK, args.lookback_days)
        n_spx = db.upsert_spx(con, spx)
        print(f"[spx] {BENCHMARK} stored {n_spx} rows")
    except Exception as e:
        print(f"[spx] failed: {type(e).__name__}: {str(e)[:80]}")

    print(
        f"[summary] universe={db.count(con,'universe')} "
        f"bar_tickers={db.distinct_bar_tickers(con)} "
        f"bars={db.count(con,'daily_bars')} spx={db.count(con,'spx_daily')} "
        f"splits={db.count(con,'splits')}"
    )
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
