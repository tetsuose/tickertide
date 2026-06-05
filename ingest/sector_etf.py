"""M3.1 ingest: SPDR sector ETF daily bars -> bucket_bars (the RS-Ratio numerator).

Reads ingest/sector_etf_map.txt (GICS sector -> SPDR ETF), pulls each ETF's EOD bars
through the SAME price provider as M0 (ingest/prices.py), and lands them in bucket_bars
via compute/db.upsert_bucket_bars. bucket = GICS sector name (== universe.sector) so
compute/rotation.py (M3.2) joins league aggregates to members by name.

HARD ISOLATION: ETF prices go to bucket_bars, NEVER daily_bars — the universe cross
section (rs_pct / rank_in_universe) must not see ETF/index prices, or per-date
percentiles drift (PRD §16, ROADMAP M3). This script never touches daily_bars/universe.

Offline note: real ETF bars need Yahoo/yfinance (often unreachable in CI/sandbox). For
offline verification, compute/fixture.py fabricates 11 synthetic sector ETF series into
the same bucket_bars table (no network); both paths write bucket = GICS sector name.

Usage:
    python3 ingest/sector_etf.py [--provider yfinance|stooq] [--lookback-days 760]
                                 [--db data/tickertide.duckdb] [--map ingest/sector_etf_map.txt]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT))

import prices  # noqa: E402
from compute import db  # noqa: E402

MAP_FILE = ROOT / "ingest" / "sector_etf_map.txt"
BUCKET_TYPE = "sector"


def load_map(path: Path) -> list[tuple[str, str]]:
    """Parse the sector->ETF map. Each line: '<GICS sector name>  <ETF>' ('#' comments).
    ETF = the last whitespace token; everything before it = the sector (bucket) name."""
    out: list[tuple[str, str]] = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.rsplit(maxsplit=1)
        if len(parts) != 2:
            print(f"  [skip] malformed map line: {line!r}", file=sys.stderr)
            continue
        out.append((parts[0].strip(), parts[1].strip().upper()))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M3.1 ingest: SPDR sector ETF bars -> bucket_bars.")
    ap.add_argument("--provider", default="yfinance", help="yfinance (default) | stooq")
    ap.add_argument("--lookback-days", type=int, default=760, help="~2y calendar days (RS-Ratio needs >=52 weeks)")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--map", default=str(MAP_FILE), help="sector->ETF map file")
    args = ap.parse_args(argv)

    mapping = load_map(Path(args.map))
    if not mapping:
        print(f"[sector-etf] no sectors parsed from {args.map}", file=sys.stderr)
        return 2

    con = db.connect(args.db)
    provider = prices.get_provider(args.provider)
    print(f"[sector-etf] provider={args.provider} sectors={len(mapping)}")

    ok = skipped = total_rows = 0
    for sector, etf in mapping:
        try:
            bars = provider.get_bars(etf, args.lookback_days)
            # provider bars = (date, o, h, l, close, adj_close, volume); take date + adj_close
            # (total-return basis, consistent with spx_daily / db.upsert_spx).
            rows = [(b[0], b[5] if len(b) > 5 and b[5] is not None else b[4]) for b in bars]
            if rows:
                total_rows += db.upsert_bucket_bars(con, BUCKET_TYPE, sector, rows)
                ok += 1
            else:
                skipped += 1
                print(f"  [skip] {etf} ({sector}): no bars")
        except Exception as e:  # provider/network flakiness expected (esp. yfinance)
            skipped += 1
            print(f"  [skip] {etf} ({sector}): {type(e).__name__}: {str(e)[:80]}")

    n_sectors = con.execute(
        "SELECT count(DISTINCT bucket) FROM bucket_bars WHERE bucket_type = ?", [BUCKET_TYPE]
    ).fetchone()[0]
    con.close()
    print(f"[sector-etf] done ok={ok} skipped={skipped} rows={total_rows} sectors_in_db={n_sectors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
