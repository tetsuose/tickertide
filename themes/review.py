"""M4.5 human-in-loop review: candidates -> themes/approved/<TICKER>.json (the durable SoT).

WHY a committed file and not a DB write (zero-backend spine)
------------------------------------------------------------
The nightly pipeline rebuilds data/tickertide.duckdb from scratch on a fresh runner, so
anything written only to the DB dies overnight. Human-approved membership is curated
data -> it lives IN GIT (themes/approved/*.json) and themes/land.py re-lands it into
theme_membership on every pipeline run (after themes/seed.py, which clears + reseeds).

The human is the authority (C6): approval may freely OVERRIDE the LLM's exposure values,
drop candidates, or add a theme the LLM missed. approved_by is required and names the
person, never a bot. Point-in-time (C3): the row's as_of_date defaults to the candidate's
FILING date — when the theme info became public — NOT the approval-operation day. PIT means
"as-of when this was knowable"; a today-dated approval also wouldn't resolve on the latest
EOD board (whose as_of is the prior trading day) until the next session. A later re-review
writes a NEW approved file state with a new date, never edits history (git keeps the old).

Usage:
    python3 themes/review.py --ticker NVDA                     # show candidates
    python3 themes/review.py --ticker NVDA \
        --approve "AI=0.55,SEMI=0.30" --by sejonep [--as-of 2026-06-13] [--note "..."]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from themes.seed import load_themes  # noqa: E402

CANDIDATES_DIR = ROOT / "themes" / "candidates"
APPROVED_DIR = ROOT / "themes" / "approved"


def load_candidates(ticker: str) -> dict:
    p = CANDIDATES_DIR / f"{ticker}.json"
    if not p.exists():
        raise SystemExit(f"[review] no candidates for {ticker}: run python3 themes/extract.py --ticker {ticker}")
    return json.loads(p.read_text())


def show(doc: dict) -> None:
    f = doc["filing"]
    print(f"[review] {doc['ticker']} candidates from {f['form']} filed {f['filed']} "
          f"(model {doc['model']}, generated {doc['generated_on']}):")
    for c in doc["candidates"]:
        print(f"    {c['theme']:6} exposure={c['exposure']:.2f} [{c['confidence']}]")
        print(f"           basis: {c['basis']}")
        print(f"           rationale: {c['rationale']}")
    if doc.get("notes"):
        print(f"    notes: {doc['notes']}")
    print(f"[review] approve with: python3 themes/review.py --ticker {doc['ticker']} "
          f"--approve \"KEY=0.x,KEY=0.x\" --by <your-name>")


def parse_approvals(spec: str, valid_keys: set[str]) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise SystemExit(f"[review] bad --approve item '{part}' (want KEY=0.x)")
        k, v = part.split("=", 1)
        k = k.strip().upper()
        if k not in valid_keys:
            raise SystemExit(f"[review] unknown theme key '{k}' (valid: {', '.join(sorted(valid_keys))})")
        exp = float(v)
        if not (0 <= exp <= 1):
            raise SystemExit(f"[review] {k}: exposure {exp} outside [0,1]")
        rows.append((k, exp))
    if not rows:
        raise SystemExit("[review] --approve parsed to zero rows")
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M4.5 human review: candidates -> approved membership.")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--approve", default=None,
                    help='comma list "AI=0.55,SEMI=0.30" — human may override LLM values (C6)')
    ap.add_argument("--by", default=None, help="approver name (REQUIRED with --approve; a person, not a bot)")
    ap.add_argument("--as-of", default=None,
                    help="as_of_date for the rows (default = candidate's 10-K filing date, the PIT "
                         "info-available day; C3)")
    ap.add_argument("--note", default="", help="free-text review note kept in the approved file")
    args = ap.parse_args(argv)
    ticker = args.ticker.upper()

    doc = load_candidates(ticker)
    if not args.approve:
        show(doc)
        return 0

    if not args.by or not args.by.strip():
        raise SystemExit("[review] --by <approver> is required with --approve (C6: human-in-loop)")
    themes = load_themes()
    rows = parse_approvals(args.approve, {t["key"] for t in themes})
    # Default to the FILING date (when the theme info became public), not today's approval
    # day: PIT = "as-of when knowable" (C3), and a today-dated approval wouldn't resolve on
    # the latest EOD board (as_of = prior trading day) until next session. --as-of overrides.
    as_of = args.as_of or doc.get("filing", {}).get("filed") or date.today().isoformat()

    by_key = {c["theme"]: c for c in doc["candidates"]}
    out = {
        "ticker": ticker,
        "approved_by": args.by.strip(),
        "as_of_date": as_of,
        "source": "llm",
        "note": args.note,
        "provenance": {"candidates_generated_on": doc["generated_on"], "model": doc["model"],
                       "filing": doc["filing"]},
        "rows": [
            {"theme": k, "exposure": exp,
             "llm_exposure": by_key.get(k, {}).get("exposure"),
             "confidence": by_key.get(k, {}).get("confidence", "n/a"),
             "basis": by_key.get(k, {}).get("basis", "(added by reviewer, not LLM-proposed)")}
            for k, exp in rows
        ],
    }
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    p = APPROVED_DIR / f"{ticker}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")

    print(f"[review] APPROVED {ticker} by {out['approved_by']} as_of {as_of} -> {p}")
    for r in out["rows"]:
        delta = "" if r["llm_exposure"] in (None, r["exposure"]) else f" (LLM proposed {r['llm_exposure']:.2f})"
        print(f"    {r['theme']:6} exposure={r['exposure']:.2f}{delta}")
    print("[review] commit this file; `make themes` (themes/land.py) lands it into the DB each run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
