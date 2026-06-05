"""M0 acceptance check — sanity-check the DuckDB after a pipeline run (AC-M0, PRD §14).

Usage: python3 compute/check.py [--db data/tickertide.duckdb]

Reads the DB and asserts the M0 invariants (universe present, bars complete with no
NULL close, composite generated with 5 components in [0,1], valuation present with
no lookahead and no negative P/E). Prints a top-by-composite spot check, then a
PASS/FAIL line per check. Exits non-zero if any hard check fails (CI-friendly).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compute import db  # noqa: E402


def run_checks(con) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []

    u = db.count(con, "universe")
    checks.append(("universe present", u >= 1, f"{u} tickers"))

    bt = db.distinct_bar_tickers(con)
    nb = db.count(con, "daily_bars")
    checks.append(("daily_bars present", bt >= 1 and nb > 0, f"{bt} tickers, {nb} bars"))
    null_close = con.execute("SELECT count(*) FROM daily_bars WHERE close IS NULL").fetchone()[0]
    checks.append(("no NULL close (EOD complete)", null_close == 0, f"{null_close} null-close bars"))

    dd = db.count(con, "derived_daily")
    checks.append(("composite generated", dd > 0, f"{dd} derived_daily rows"))
    if dd > 0:
        r = con.execute(
            "SELECT min(c_rs), max(c_rs), min(c_high), max(c_high), min(c_trend), max(c_trend), "
            "min(c_vol), max(c_vol), min(c_accel), max(c_accel) "
            "FROM derived_daily WHERE composite IS NOT NULL"
        ).fetchone()
        in_range = all(
            (r[2 * i] is None) or (r[2 * i] >= -1e-9 and r[2 * i + 1] <= 1 + 1e-9)
            for i in range(5)
        )
        checks.append(("5 components in [0,1]", in_range, "component ranges within [0,1]"))

    vd = db.count(con, "valuation_daily")
    checks.append(("valuation_daily present", vd > 0, f"{vd} rows"))
    if vd > 0:
        la = con.execute("SELECT count(*) FROM valuation_daily WHERE as_of_filed > date").fetchone()[0]
        checks.append(("ASOF point-in-time (no lookahead)", la == 0, f"{la} lookahead rows"))
        neg_pe = con.execute("SELECT count(*) FROM valuation_daily WHERE pe < 0").fetchone()[0]
        checks.append(("no negative P/E (E<=0 -> n.m.)", neg_pe == 0, f"{neg_pe} negative-pe rows"))

    return checks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M0 acceptance check.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    checks = run_checks(con)

    if db.count(con, "derived_daily") > 0:
        latest = con.execute("SELECT max(date) FROM derived_daily").fetchone()[0]
        print(f"spot check — {latest} top 5 by composite:")
        for row in con.execute(
            "SELECT ticker, round(composite,1), round(rs_pct,0), rank_in_universe "
            "FROM derived_daily WHERE date = ? ORDER BY composite DESC LIMIT 5", [latest]
        ).fetchall():
            print(f"  {row[0]:6} composite={row[1]} rs_pct={row[2]} rank={row[3]}")

    print("\nAC-M0 checks:")
    all_ok = True
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} ({detail})")
        all_ok = all_ok and ok
    print(f"\nCHECK_{'OK' if all_ok else 'FAIL'}")
    con.close()
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
