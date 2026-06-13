"""M5.1 valuation cross-section -> web/public/data/valuation.parquet (+ .meta.json).

The FULL-universe latest valuation snapshot for the M5 Valuation screener (PRD §9.5,
wide explore). One row per universe ticker carrying its latest as-of valuation multiples
plus as-of freshness, written as Parquet so the browser's duckdb-wasm queries it directly
(sort / scope filter / common-vintage percentile run client-side over this file — M5.2).

Why Parquet, not board.json: board.json is the top-N-by-composite shortlist (bounded
decide, PRD §9.3); Valuation is the whole cross-section (wide explore). Same engine, one
snapshot (C9) — valuation.parquet and board.json read the same valuation_daily, so a
ticker in both shows identical multiples. peg/margin come straight from valuation_daily
(computed since M0; board.json simply never exported them — M5 adds the two columns).

The snapshot date lives once inside the SQL (a `snap` CTE), so the freshness buckets and
the as-of age all measure against the same latest trading day. Output is gitignored
(derived nightly); a tiny .meta.json sidecar carries as_of + row count for the manifest
(D.4) and the client's header without parsing the Parquet.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compute import db  # noqa: E402

SCHEMA_VERSION = 1
DATA_DIR = ROOT / "web" / "public" / "data"
FRESH_DAYS = 95   # <=95d fresh, <=160d stale, else overdue (PRD §9.5/§10.5; matches board.py)
STALE_DAYS = 160

# Full-universe latest-as-of cross-section. `snap` (the latest derived_daily date — the
# engine snapshot board.json also uses) is bound as a literal so it can't correlate across
# the LEFT JOINs (DuckDB rejects correlated columns under an outer join). latest_val picks
# each ticker's most recent valuation row on or before snap; freshness/age measure
# period_end -> snap so every row shares one ruler. snap is a DB-derived DATE, not user input.
def cross_section_sql(snap: str) -> str:
    return f"""
WITH latest_val AS (
  SELECT v.ticker, v.pe, v.ps, v.evs, v.ev_ebitda, v.peg, v.growth, v.margin, v.rule40,
         v.as_of_period_end, v.as_of_filed,
         row_number() OVER (PARTITION BY v.ticker ORDER BY v.date DESC) AS rn
  FROM valuation_daily v WHERE v.date <= DATE '{snap}'
)
SELECT
  d.ticker,
  u.name,
  u.sector,
  u.mktcap,
  v.pe, v.ps, v.evs, v.ev_ebitda, v.peg, v.growth, v.margin, v.rule40,
  v.as_of_period_end,
  v.as_of_filed,
  CASE WHEN v.as_of_period_end IS NULL THEN NULL
       ELSE date_diff('day', v.as_of_period_end, DATE '{snap}') END AS as_of_age_days,
  CASE WHEN v.as_of_period_end IS NULL THEN NULL
       WHEN date_diff('day', v.as_of_period_end, DATE '{snap}') <= {FRESH_DAYS} THEN 'fresh'
       WHEN date_diff('day', v.as_of_period_end, DATE '{snap}') <= {STALE_DAYS} THEN 'stale'
       ELSE 'overdue' END AS freshness
FROM derived_daily d
LEFT JOIN universe u ON u.ticker = d.ticker
LEFT JOIN latest_val v ON v.ticker = d.ticker AND v.rn = 1
WHERE d.date = DATE '{snap}'
ORDER BY d.ticker
"""


def export_valuation(con, out: Path) -> dict:
    """Write the cross-section Parquet, return {as_of_date, count} meta."""
    out.parent.mkdir(parents=True, exist_ok=True)
    snap = con.execute("SELECT max(date) FROM derived_daily").fetchone()[0]
    sql = cross_section_sql(str(snap))
    con.execute(f"COPY ({sql}) TO '{out.as_posix()}' (FORMAT PARQUET)")
    # Read back the snapshot facts for the sidecar (COPY doesn't return them).
    n = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
    n_val = con.execute(f"SELECT count(*) FROM ({sql}) WHERE pe IS NOT NULL OR ps IS NOT NULL").fetchone()[0]
    return {"as_of_date": str(snap) if snap else None, "count": int(n), "valuation_coverage": int(n_val)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M5.1 export: valuation cross-section Parquet.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--out", default=str(DATA_DIR / "valuation.parquet"))
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    if con.execute("SELECT count(*) FROM derived_daily").fetchone()[0] == 0:
        con.close()
        raise SystemExit("[valuation-parquet] derived_daily empty — run `make compute` first.")

    out = Path(args.out)
    meta = export_valuation(con, out)
    con.close()

    meta_doc = {"schema_version": SCHEMA_VERSION, **meta}
    meta_path = out.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta_doc, ensure_ascii=False, separators=(",", ":")) + "\n")

    kb = out.stat().st_size / 1024
    print(f"[valuation-parquet] {out}  as_of={meta['as_of_date']}  rows={meta['count']}  "
          f"valuation={meta['valuation_coverage']}  size={kb:.1f}KB  (+ {meta_path.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
