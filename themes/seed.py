"""Bootstrap theme_membership from the universe_seed.txt coverage groups (M4.1).

WHY this exists
---------------
M4 membership is meant to be EDGAR-revenue-anchored + LLM-proposed + human-approved
(themes/extract.py + review.py, M4.5). That path needs an API / filings / a human in
the loop and is not deterministically runnable offline. This script is the cheap,
deterministic bootstrap: ingest/universe_seed.txt already groups the theme-rep tickers
under section headers ("# Semiconductors" -> SEMI ...), so we structure those groups into
an initial point-in-time theme_membership snapshot. It is a COARSE starting point, not
authority: source='seed', approved_by='seed', a single baseline as_of_date, and one flat
SEED_EXPOSURE per row (real per-ticker exposure = revenue share, filled later, M4.5).

Data-driven mapping (no opinion in code): each theme's `seed_header` in themes/themes.yaml
names the universe_seed.txt section it owns. A seed ticker therefore lands in exactly the
theme whose section it sits under — many-to-many is fully supported (a ticker listed under
two sections yields two rows) but the current seed file lists each rep once, so real theme
overlaps (NVDA in AI *and* SEMI) are deferred to the revenue-anchored M4.5 path by design.

Usage:
    python3 themes/seed.py [--db PATH] [--as-of 2026-06-06] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import yaml  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - environment hint
    sys.exit("[seed] PyYAML is required: pip install -r requirements.txt (pyyaml)")

from compute import db  # noqa: E402

THEMES_YAML = ROOT / "themes" / "themes.yaml"
SEED_FILE = ROOT / "ingest" / "universe_seed.txt"

# Bootstrap constants (deliberately coarse — real values come from M4.5):
SEED_EXPOSURE = 0.6          # flat revenue-share placeholder for every seeded membership
SEED_AS_OF = "2024-01-01"    # fallback baseline when the DB has no bars to anchor to
SEED_SOURCE = "seed"
SEED_APPROVED_BY = "seed"    # sentinel: auto-seeded, NOT human-reviewed (C6)


def baseline_as_of(con) -> str:
    """The seed membership's point-in-time as_of. The theme index (compute/theme_index.py)
    is built FORWARD from a theme's first as_of, so a seed sitting at a recent date yields
    only a few days of index — far too short for the weekly RS-Ratio (theme Rotation comes
    up empty). The seed is a COARSE long-standing baseline ("these reps have long been in
    these themes"), so anchor it at the earliest available price bar: the index then spans
    the full ~2y of history and RS-Ratio emits. PIT is preserved — a later M4.5 approval at
    its own as_of still wins forward. Falls back to SEED_AS_OF on a bars-less DB."""
    r = con.execute("SELECT CAST(min(date) AS VARCHAR) FROM daily_bars").fetchone()
    return (r[0] if r and r[0] else None) or SEED_AS_OF


def load_themes(path: Path = THEMES_YAML) -> list[dict]:
    """Parse themes.yaml -> list of theme dicts (key/name/color_var/cap/seed_header/...)."""
    doc = yaml.safe_load(path.read_text())
    themes = doc.get("themes") if isinstance(doc, dict) else None
    if not themes:
        raise ValueError(f"{path} has no `themes:` list")
    return themes


def header_to_key(themes: list[dict]) -> dict[str, str]:
    """Map each theme's seed_header (lowercased) -> theme key. The data-driven bridge
    from universe_seed.txt section prose to a theme key."""
    out: dict[str, str] = {}
    for t in themes:
        hdr = (t.get("seed_header") or "").strip().lower()
        if hdr:
            out[hdr] = t["key"]
    return out


def parse_seed_groups(seed_text: str, hdr2key: dict[str, str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Walk universe_seed.txt tracking the current section. A comment line resets the
    section, then (re)sets it if its text matches a known seed_header — so an UNRECOGNISED
    header leaves following tickers unmapped (reported) instead of silently mis-assigned.
    Returns (memberships=[(ticker, theme_key)...] deduped by (ticker,theme), unmapped[])."""
    current: str | None = None
    seen: set[tuple[str, str]] = set()
    memberships: list[tuple[str, str]] = []
    unmapped: list[str] = []
    for raw in seed_text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            text = stripped.lstrip("#").strip().lower()
            current = hdr2key.get(text)   # None for doc/comment lines and unknown headers
            continue
        ticker = stripped.split("#", 1)[0].strip().upper()
        if not ticker:
            continue
        if current is None:
            unmapped.append(ticker)
            continue
        key = (ticker, current)
        if key not in seen:
            seen.add(key)
            memberships.append(key)
    return memberships, unmapped


def build_rows(memberships: list[tuple[str, str]], as_of: str) -> list[tuple]:
    """(ticker, theme) -> full theme_membership row tuples (bootstrap constants)."""
    return [
        (ticker, theme, SEED_EXPOSURE, as_of, SEED_SOURCE, SEED_APPROVED_BY)
        for ticker, theme in memberships
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Seed theme_membership from universe_seed.txt groups.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--as-of", default=None,
                    help="baseline as_of_date (ISO); default = earliest daily_bars date so the theme "
                         f"index spans full history (fallback {SEED_AS_OF} on a bars-less DB)")
    ap.add_argument("--dry-run", action="store_true", help="print rows, do not write the DB")
    args = ap.parse_args(argv)

    themes = load_themes()
    hdr2key = header_to_key(themes)
    valid = {t["key"] for t in themes}

    memberships, unmapped = parse_seed_groups(SEED_FILE.read_text(), hdr2key)

    con = db.connect(args.db)
    as_of = args.as_of or baseline_as_of(con)
    rows = build_rows(memberships, as_of)

    # Per-theme tally for a legible summary + an at-a-glance coverage check.
    by_theme: dict[str, int] = {}
    for _, theme in memberships:
        by_theme[theme] = by_theme.get(theme, 0) + 1

    print(f"[seed] themes.yaml: {len(valid)} themes; universe_seed groups -> {len(rows)} memberships "
          f"as_of={as_of} exposure={SEED_EXPOSURE} source={SEED_SOURCE}")
    for key in sorted(by_theme):
        print(f"    {key:6} {by_theme[key]:3}")
    if unmapped:
        print(f"[seed] WARNING {len(unmapped)} ticker(s) under no known seed_header (check themes.yaml): "
              + ", ".join(unmapped[:12]) + (" …" if len(unmapped) > 12 else ""))

    if args.dry_run:
        con.close()
        print("[seed] --dry-run: no DB write.")
        return 0

    db.clear_theme_membership(con)   # idempotent reseed (source='seed' is fully derived)
    n = db.upsert_theme_membership(con, rows)
    con.close()
    print(f"[seed] wrote {n} theme_membership rows to {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
