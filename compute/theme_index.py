"""M4.2 theme index: theme_membership (point-in-time) + daily_bars -> bucket_bars(theme).

Builds one daily price series per concept theme so themes reuse the WHOLE M3 bucket
framework: the series lands in bucket_bars(bucket_type='theme') exactly like a sector
ETF, and compute/rotation.py (bucket_type='theme', M4.3) turns it into the RS-Ratio line
— no new surface, no RS-Ratio rewrite (the point-in-time work is HERE, in index construction).

Two hard constraints shape the construction (PRD §7, kickoff M4):

  C4 — NOT market-cap weighted. Weights come from `exposure` (revenue share), then are
  water-filled-capped per themes.yaml so no single member exceeds `cap`. "AI" must not
  collapse to NVDA alone. (Below ceil(1/cap) members the cap can't bind and we fall back
  to equal weight — still exposure-agnostic-of-mktcap, still anti-domination.)

  C3 — point-in-time, no retroactive rewrite, continuous across rebalances. The index is a
  CHAINED RETURN series, not a weighted price level: each day's return uses the membership
  as-of the PRIOR day (members@t = db.theme_membership_asof), and level[t] = level[t-1]·
  (1+ret). Consequences: (1) editing a later as_of changes weights only from that date
  forward, so every earlier index value is byte-identical (no fiction in theme RS-Ratio
  lines / Ocean trails); (2) the level never jumps when membership changes (chaining), so
  rebalance doesn't break the price series; (3) returns (not price levels) make the index
  scale-invariant — a $500 and a $20 member contribute by weight, not by price.

The index starts at a theme's FIRST as_of date — before that we have no membership info,
and using today's membership to backfill history would be lookahead (the very thing C3
forbids). So a single-as_of seed (themes/seed.py) yields almost no history; real
point-in-time history comes from membership stamped at each historical filing (M4.5).

Reads daily_bars (member adj_close) + theme_membership only; never touches the universe
cross-section (derived_daily.rs_pct/rank) — same isolation as sector ETFs (PRD §16).

Usage:
    python3 compute/theme_index.py [--db data/tickertide.duckdb] [--base 100]
"""
from __future__ import annotations

import argparse
import bisect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from compute import db  # noqa: E402

THEMES_YAML = ROOT / "themes" / "themes.yaml"
DEFAULT_CAP = 0.30          # fallback when a theme has no cap in themes.yaml
BUCKET_TYPE = "theme"
BASE_LEVEL = 100.0          # index base at the first as_of (RS uses ratios, scale is free)


def load_caps(path: Path = THEMES_YAML) -> dict[str, float]:
    """theme key -> index weight cap, from themes.yaml (the theme-definition SoT)."""
    doc = yaml.safe_load(path.read_text()) or {}
    return {t["key"]: float(t.get("cap", DEFAULT_CAP)) for t in doc.get("themes", [])}


def capped_weights(exposures: dict[str, float], cap: float) -> dict[str, float]:
    """Exposure-weighted portfolio weights summing to 1, with each member <= cap (C4).

    Normalise exposures, then water-fill: repeatedly clamp any weight over `cap` to `cap`
    and redistribute the freed weight across the still-uncapped members in proportion. If
    `cap` is too tight for the member count (cap*n <= 1, so even equal weight breaches it),
    fall back to equal weight — the most-spread feasible vector. Pure (no I/O), so it is
    the single place the weighting rule lives and is unit-checkable."""
    pos = {t: float(e) for t, e in exposures.items() if e and e > 0}
    if not pos:
        return {}
    n = len(pos)
    if cap * n <= 1.0 + 1e-12:            # cap can't bind for this few members
        return {t: 1.0 / n for t in pos}
    s = sum(pos.values())
    w = {t: v / s for t, v in pos.items()}
    capped: set[str] = set()
    for _ in range(n):
        over = [t for t, val in w.items() if t not in capped and val > cap + 1e-12]
        if not over:
            break
        for t in over:
            w[t] = cap
            capped.add(t)
        free = {t: w[t] for t in w if t not in capped}
        remaining = 1.0 - cap * len(capped)
        fs = sum(free.values())
        if fs <= 0:
            break
        for t in free:
            w[t] = remaining * w[t] / fs
    return w


def theme_weights_asof(con, theme: str, as_of, cap: float) -> dict[str, float]:
    """Public: realised index weights for `theme` as-of `as_of` (capped-normalised
    exposure). The index uses these internally; exposed so verification can assert the
    non-market-cap / cap-bound property (C4) directly."""
    m = db.theme_membership_asof(con, as_of, theme=theme)
    return capped_weights({r.ticker: r.exposure for r in m.itertuples()}, cap)


def _member_prices(con, tickers: set[str]) -> dict[str, dict[str, float]]:
    """{ticker: {iso_date: adj_close}} for the given members (one query)."""
    if not tickers:
        return {}
    qs = ",".join("?" * len(tickers))
    df = con.execute(
        f"SELECT ticker, CAST(date AS VARCHAR) d, adj_close FROM daily_bars "
        f"WHERE ticker IN ({qs}) ORDER BY ticker, date",
        list(tickers),
    ).df()
    out: dict[str, dict[str, float]] = {}
    for t, sub in df.groupby("ticker"):
        out[t] = dict(zip(sub["d"].tolist(), sub["adj_close"].astype(float).tolist()))
    return out


def build_theme_index(con, theme: str, cap: float, base: float = BASE_LEVEL) -> list[tuple]:
    """Chained-return daily index for `theme` -> [(iso_date, level)] from its first as_of.
    Returns [] if the theme has no membership or <2 priced days."""
    as_ofs = [str(r[0]) for r in con.execute(
        "SELECT DISTINCT CAST(as_of_date AS VARCHAR) FROM theme_membership WHERE theme = ? "
        "ORDER BY 1", [theme]
    ).fetchall()]
    if not as_ofs:
        return []

    seg_w: dict[str, dict[str, float]] = {}
    members: set[str] = set()
    for a in as_ofs:
        w = theme_weights_asof(con, theme, a, cap)
        seg_w[a] = w
        members |= set(w)
    if not members:
        return []

    px = _member_prices(con, members)
    first = as_ofs[0]
    axis = sorted({d for s in px.values() for d in s} | {first})
    axis = [d for d in axis if d >= first]
    if len(axis) < 2:
        return []

    rows = [(axis[0], base)]
    level = base
    for i in range(1, len(axis)):
        prior, cur = axis[i - 1], axis[i]
        j = bisect.bisect_right(as_ofs, prior) - 1          # latest as_of <= prior (PIT)
        w = seg_w[as_ofs[j]] if j >= 0 else {}
        avail = {t: wt for t, wt in w.items()
                 if t in px and prior in px[t] and cur in px[t]}
        sw = sum(avail.values())
        if sw > 0:
            ret = sum((wt / sw) * (px[t][cur] / px[t][prior] - 1.0) for t, wt in avail.items())
            level *= (1.0 + ret)
        rows.append((cur, level))
    return rows


def compute_theme_index(con, caps: dict[str, float] | None = None, base: float = BASE_LEVEL) -> dict:
    """Rebuild bucket_bars(bucket_type='theme') for every theme in theme_membership.
    Clears only theme rows (sector ETF rows untouched). Returns a summary dict."""
    caps = load_caps() if caps is None else caps
    themes = db.theme_keys(con)
    db.clear_bucket_bars(con, BUCKET_TYPE)
    detail, n_themes, n_rows, skipped = {}, 0, 0, 0
    for th in themes:
        cap = caps.get(th, DEFAULT_CAP)
        rows = build_theme_index(con, th, cap, base)
        if len(rows) < 2:
            skipped += 1
            continue
        n_rows += db.upsert_bucket_bars(con, BUCKET_TYPE, th, rows)
        n_themes += 1
        detail[th] = {"days": len(rows), "first": rows[0][0], "last": rows[-1][0],
                      "cap": cap, "members": len(theme_weights_asof(con, th, rows[-1][0], cap))}
    return {"themes": n_themes, "rows": n_rows, "skipped": skipped, "detail": detail}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M4.2 theme index -> bucket_bars(theme).")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    ap.add_argument("--base", type=float, default=BASE_LEVEL, help="index base level at first as_of")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    if db.count(con, "theme_membership") == 0:
        print("[theme-index] theme_membership is empty — run themes/seed.py or the fixture first.")
        con.close()
        return 0
    s = compute_theme_index(con, base=args.base)
    print(f"[theme-index] themes={s['themes']} rows={s['rows']} skipped={s['skipped']} "
          f"(bucket_bars bucket_type='theme'; non-cap-weighted, point-in-time)")
    for th in sorted(s["detail"]):
        d = s["detail"][th]
        print(f"    {th:6} days={d['days']:4} members@last={d['members']:2} cap={d['cap']:.2f} "
              f"({d['first']} .. {d['last']})")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
