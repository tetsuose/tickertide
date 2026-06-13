"""M4.5 landing: themes/approved/*.json -> theme_membership rows (every pipeline run).

The committed approved files are the durable source of truth for human-reviewed
membership (the DB is rebuilt nightly). Runs in `make themes` AFTER themes/seed.py:
seed clears the whole table and re-lands bootstrap rows, then this re-lands approved
rows. Point-in-time resolution (compute/db.theme_membership_asof) then prefers the
approved row wherever its as_of_date is later than the seed baseline — seed stays as
coarse coverage for un-reviewed tickers, approval wins per (ticker, theme) (C3).

Usage: python3 themes/land.py [--db PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compute import db  # noqa: E402
from themes.seed import load_themes  # noqa: E402

APPROVED_DIR = ROOT / "themes" / "approved"


def load_approved_rows() -> list[tuple]:
    """All approved files -> theme_membership row tuples. Validates theme keys and
    exposure range so a hand-edited file fails loudly here, not downstream."""
    valid = {t["key"] for t in load_themes()}
    rows: list[tuple] = []
    for p in sorted(APPROVED_DIR.glob("*.json")):
        doc = json.loads(p.read_text())
        ticker, by, as_of = doc["ticker"], doc["approved_by"], doc["as_of_date"]
        if not by or not str(by).strip():
            raise SystemExit(f"[land] {p.name}: approved_by is empty (C6)")
        for r in doc["rows"]:
            if r["theme"] not in valid:
                raise SystemExit(f"[land] {p.name}: unknown theme key {r['theme']}")
            exp = float(r["exposure"])
            if not (0 <= exp <= 1):
                raise SystemExit(f"[land] {p.name}: {r['theme']} exposure {exp} outside [0,1]")
            rows.append((ticker, r["theme"], exp, as_of, doc.get("source", "llm"), by))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M4.5: land approved membership files into the DB.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--dry-run", action="store_true", help="print rows, do not write")
    args = ap.parse_args(argv)

    rows = load_approved_rows()
    if not rows:
        print("[land] no approved files under themes/approved/ — nothing to land.")
        return 0
    for t, th, exp, as_of, src, by in rows:
        print(f"    {t:6} {th:6} exposure={exp:.2f} as_of={as_of} source={src} approved_by={by}")
    if args.dry_run:
        print(f"[land] --dry-run: {len(rows)} row(s), no DB write.")
        return 0

    con = db.connect(args.db)
    n = db.upsert_theme_membership(con, rows)
    con.close()
    print(f"[land] wrote {n} approved theme_membership row(s) to {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
