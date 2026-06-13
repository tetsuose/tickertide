"""M4.5 orchestration: extract -> review -> land, per ticker.

Thin glue over the three steps so the operator flow is one entrypoint. The review step
stays interactive BY DESIGN (C6 — a human must look at the candidates before anything
reaches theme_membership), so this script never auto-approves: without --approve it runs
extraction and prints the candidates + the approval command; with --approve/--by it
forwards to review.py and then lands into the local DB.

Usage:
    python3 themes/run.py --ticker NVDA                          # extract + show
    python3 themes/run.py --ticker NVDA --skip-extract           # show existing candidates
    python3 themes/run.py --ticker NVDA --approve "AI=0.5" --by sejonep   # review + land
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from themes import extract, land, review  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M4.5: extract -> review -> land for one ticker.")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--model", default=None, help="claude CLI model override for extraction")
    ap.add_argument("--skip-extract", action="store_true", help="reuse existing candidates file")
    ap.add_argument("--approve", default=None, help='forwarded to review.py, e.g. "AI=0.55,SEMI=0.30"')
    ap.add_argument("--by", default=None, help="approver name (required with --approve)")
    ap.add_argument("--as-of", default=None, help="approval as_of_date (default today)")
    ap.add_argument("--note", default="", help="review note")
    args = ap.parse_args(argv)
    ticker = args.ticker.upper()

    if not args.skip_extract and not args.approve:
        rc = extract.main(["--ticker", ticker] + (["--model", args.model] if args.model else []))
        if rc:
            return rc

    review_args = ["--ticker", ticker]
    if args.approve:
        review_args += ["--approve", args.approve, "--by", args.by or "", "--note", args.note]
        if args.as_of:
            review_args += ["--as-of", args.as_of]
    rc = review.main(review_args)
    if rc or not args.approve:
        return rc

    return land.main([])


if __name__ == "__main__":
    raise SystemExit(main())
