"""Synthetic DuckDB fixture for OFFLINE verification (dev tool — not in the nightly pipeline).

WHY this exists
---------------
The real `make pipeline` needs api.nasdaq.com (universe) + Yahoo/yfinance (price
bars) to be reachable. In CI and sandboxed dev environments they frequently are
not (observed: Nasdaq 000, Yahoo 500). But the correctness of compute / export /
web does NOT depend on *real* data — only on a DB shaped like a real one. This
tool fabricates a deterministic universe / daily_bars / spx_daily / fundamentals_q
(numpy, fixed seed) and lands it through the SAME compute/db.py upserts the real
ingest uses, so downstream `make compute` + the exporters read the real engine
code path on reproducible inputs, with no network.

It writes the five byte-stable source tables (universe / daily_bars / spx_daily /
fundamentals_q + bucket_bars for M3 rotation) plus theme_membership (M4.1, point-in-time).
Run `make compute` (run.py + valuation.py) afterwards to fill derived_daily +
valuation_daily with the real engine, then any exporter (export/board.py …).
`make fixture-pipeline` chains fixture -> compute.

Edge cases baked in (so verification actually exercises the branchy paths the web
surfaces care about — see m1-web-export-verification):
  - >=25 tickers x >=260 trading days   -> MA200 / 252d-high / 126d-return all warm
  - loss-making tickers (eps_ttm < 0)   -> P/E n.m. -> P/S fallback (valuation.py)
  - one deep-loss ticker (ebitda < 0)   -> EV/EBITDA n.m. -> EV/S fallback too
  - a stale filer + an overdue filer    -> as-of freshness buckets fresh/stale/overdue
  - one ticker with NO fundamentals     -> valuation coverage < universe count
  - a wide spread of drifts             -> wide composite spread, gap-free ranks
  - sectors/exchanges cycled            -> scope=sector group-by has something to bucket
  - theme_membership over 2 as_of dates -> point-in-time members (M4): many-to-many, an
                                           exposure restatement, a later join, a drop (exp=0)

Determinism: every random draw comes from one numpy Generator seeded by --seed,
consumed in a fixed order, and the calendar is anchored to --end-date (default a
fixed date, NOT today), so a given (seed, tickers, days, end-date) is byte-stable.

Usage:
    python3 compute/fixture.py [--db PATH] [--tickers 30] [--days 320]
                               [--seed 42] [--end-date 2026-06-05]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from compute import db  # noqa: E402

# Defaults sized so the latest snapshot has fully-warm indicators (PRD §10):
# MA200 (200 bars) + 252d high + 126d return all need a long history; 320 trading
# days (~15 months) clears them with headroom. >=25 tickers gives a real cross
# section for the per-date RS percentile + rank.
DEFAULT_TICKERS = 30
DEFAULT_DAYS = 320
DEFAULT_SEED = 42
DEFAULT_END = "2026-06-05"   # fixed anchor (not today) so the DB is reproducible

TRADING_YEAR = 252
QUARTER_DAYS = 91            # spacing between fabricated fiscal quarter-ends
N_QUARTERS = 8              # ~2y of trailing-4Q rows per ticker (YoY growth needs >=5)

SECTORS = [
    "Information Technology", "Health Care", "Financials", "Consumer Discretionary",
    "Communication Services", "Industrials", "Consumer Staples", "Energy",
    "Utilities", "Real Estate", "Materials",
]
EXCHANGES = ["NASDAQ", "NYSE", "AMEX"]

# Deterministic per-index profile so every fixture (when tickers is large enough)
# contains each edge case at a known ticker. Index -> profile:
PROFILES = {
    0: "loss",       # eps_ttm < 0            -> P/E n.m., P/S used
    1: "deep_loss",  # eps_ttm < 0, ebitda<0  -> P/E + EV/EBITDA n.m.
    2: "stale",      # last filing ~130d old  -> freshness "stale"
    3: "overdue",    # last filing ~230d old  -> freshness "overdue"
    4: "none",       # no fundamentals at all -> valuation coverage gap
}


def profile_for(i: int) -> str:
    return PROFILES.get(i, "normal")


def trading_days(end: date, n: int) -> list[date]:
    """`n` weekday dates ending on or before `end` (oldest first). Holidays ignored
    — synthetic; what matters is a dense, monotonic daily calendar."""
    out: list[date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:  # Mon..Fri
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


def price_path(rng: np.random.Generator, n: int, start: float, mu: float, sigma: float) -> np.ndarray:
    """Geometric random walk of `n` daily closes from `start` with annualized drift
    `mu` and vol `sigma`. Always positive (exp of cumulative log-returns)."""
    dt = 1.0 / TRADING_YEAR
    shocks = rng.normal(0.0, 1.0, n)
    rets = mu * dt + sigma * np.sqrt(dt) * shocks
    return start * np.exp(np.cumsum(rets))


def make_bars(rng: np.random.Generator, dates: list[date], closes: np.ndarray) -> list[tuple]:
    """Build OHLCV bar tuples (date, open, high, low, close, adj_close, volume) that
    bracket each close. adj_close == close (no synthetic splits/dividends; the engine
    uses adj_close for all return math). Volume skews up on up-days so the up/down and
    50/200 volume ratios in signals.py have signal."""
    n = len(closes)
    prev = np.empty(n)
    prev[0] = closes[0]
    prev[1:] = closes[:-1]

    opens = prev * (1.0 + rng.normal(0.0, 0.005, n))
    hi_pad = np.abs(rng.normal(0.0, 0.008, n))
    lo_pad = np.abs(rng.normal(0.0, 0.008, n))
    highs = np.maximum(opens, closes) * (1.0 + hi_pad)
    lows = np.minimum(opens, closes) * (1.0 - lo_pad)

    base_vol = rng.uniform(3e5, 3e7)
    vshock = np.exp(rng.normal(0.0, 0.3, n))
    up = closes >= prev
    vols = (base_vol * vshock * np.where(up, 1.10, 0.95)).astype(np.int64)
    vols = np.maximum(vols, 1)

    return [
        (dates[i].isoformat(), float(opens[i]), float(highs[i]), float(lows[i]),
         float(closes[i]), float(closes[i]), int(vols[i]))
        for i in range(n)
    ]


def fundamentals_rows(rng: np.random.Generator, profile: str, end: date,
                      last_close: float, shares: float) -> list[tuple]:
    """Trailing-4Q rows in db.FUNDAMENTALS_COLS order (period_end, filed, effective_eod_date,
    source_type, source_form, revenue_ttm, shares, total_debt, cash, ebitda_ttm, eps_ttm),
    formal-filing PIT (filed >= period_end, filed <= end; effective_eod_date == filed, v1).
    The most-recent period_end's age vs `end` sets the freshness bucket the exporter reports;
    revenue compounds so YoY growth is positive and PEG/Rule-40 compute. Adding the three
    provenance fields draws NO rng, so the other fixture tables stay byte-identical."""
    if profile == "none":
        return []

    last_age = {"stale": 130, "overdue": 230}.get(profile, 50)  # default 50d -> "fresh"
    last_pe = end - timedelta(days=last_age)

    mktcap = shares * last_close
    ps_target = float(rng.uniform(2.5, 14.0))
    rev_latest = mktcap / ps_target
    qoq = float(rng.uniform(0.010, 0.025))       # ~4-10% YoY
    net_margin = float(rng.uniform(0.04, 0.18))
    ebitda_margin = float(rng.uniform(0.12, 0.35))
    debt_ratio = float(rng.uniform(0.10, 0.80))
    cash_ratio = float(rng.uniform(0.05, 0.50))
    if profile in ("loss", "deep_loss"):
        net_margin = -float(rng.uniform(0.05, 0.25))  # negative EPS

    rows: list[tuple] = []
    for k in range(N_QUARTERS):  # k=0 oldest .. N-1 newest
        pe = last_pe - timedelta(days=QUARTER_DAYS * (N_QUARTERS - 1 - k))
        filed = pe + timedelta(days=int(rng.integers(35, 46)))
        if filed > end:
            filed = end
        rev = rev_latest * (1.0 + qoq) ** (k - (N_QUARTERS - 1))  # newest == rev_latest
        ebitda = rev * ebitda_margin
        if profile == "deep_loss":
            ebitda = -abs(rev * float(rng.uniform(0.02, 0.10)))
        eps = (rev * net_margin) / shares
        rows.append((
            pe.isoformat(), filed.isoformat(),
            filed.isoformat(), db.SOURCE_FORMAL_FILING, db.SOURCE_FORM_UNKNOWN,
            float(rev), float(shares),
            float(rev * debt_ratio), float(rev * cash_ratio), float(ebitda), float(eps),
        ))
    return rows


def build_bucket_bars(con, rng: np.random.Generator, dates: list[date], days: int) -> int:
    """Fabricate one synthetic close series per GICS sector into bucket_bars (M3.1).

    Called from build() AFTER all other rng draws, so it never perturbs the universe/
    bars/spx/fundamentals byte stream (the M1/M2 committed fixtures depend on that).
    ETF closes are isolated in bucket_bars and must never reach the universe cross
    section. Sector drifts straddle SPX's drift (0.08) so the downstream RS-Ratio
    (compute/rotation.py, M3.2) has a real spread around the 100 baseline; ETFs are
    diversified, hence lower vol than single names. Safe to retune — trailing draws only."""
    sector_mus = np.linspace(0.28, -0.16, len(SECTORS))  # strong .. weak vs spx mu=0.08
    rng.shuffle(sector_mus)
    n = 0
    for j, sector in enumerate(SECTORS):
        closes = price_path(
            rng, days, start=float(rng.uniform(40.0, 150.0)),
            mu=float(sector_mus[j]), sigma=float(rng.uniform(0.12, 0.22)),
        )
        rows = [(dates[t].isoformat(), float(closes[t])) for t in range(days)]
        n += db.upsert_bucket_bars(con, "sector", sector, rows)
    return n


# M4.1: synthetic theme_membership plan — deterministic (NO rng), so the five source
# tables stay byte-identical. Exercises every point-in-time mechanic AC-M4 checks:
# >=4 themes, two as_of snapshots, a many-to-many ticker, an exposure restatement, a
# member that joins later, and a drop-via-exposure=0. Tuples are
# (ticker_index 0-based, theme, exposure, snapshot) with snapshot in {'early','late'};
# only indices that exist at the chosen --tickers size are emitted.
THEME_AS_OF_EARLY_FRAC = 0.25   # first snapshot ~1/4 into the calendar
THEME_AS_OF_LATE_FRAC = 0.75    # restatement ~3/4 in
THEME_PLAN = [
    (0, "AI", 0.80, "early"),    # TT01 -> AI + SEMI  (many-to-many, never MECE)
    (0, "SEMI", 0.50, "early"),
    (1, "AI", 0.55, "early"),    # TT02 AI, restated UP at 'late'
    (2, "AI", 0.70, "early"),
    (3, "SEMI", 0.65, "early"),  # TT04 SEMI, DROPPED at 'late'
    (4, "SEMI", 0.60, "early"),
    (5, "ROBO", 0.62, "early"),
    (6, "ROBO", 0.58, "early"),
    (7, "CLOUD", 0.66, "early"),
    (8, "CLOUD", 0.60, "early"),
    (1, "AI", 0.85, "late"),     # TT02 exposure 0.55 -> 0.85 (pre-'late' history keeps 0.55)
    (9, "AI", 0.72, "late"),     # TT10 joins AI only at 'late' (not a member before)
    (3, "SEMI", 0.00, "late"),   # TT04 dropped: exposure=0 at 'late', pre-'late' still 0.65
]


def build_theme_membership(con, dates: list[date], tickers: int) -> dict:
    """Land deterministic synthetic theme_membership (M4.1) from THEME_PLAN.

    Called from build() AFTER every rng draw so it never perturbs the universe/bars/spx/
    fundamentals/bucket byte stream. No rng of its own — fully deterministic from the
    calendar + ticker count. The two as_of snapshots are real trading dates inside the
    price history so the theme index (M4.2) can compose member closes at each. Returns a
    summary dict."""
    width = max(2, len(str(tickers)))
    i_early = max(1, int(len(dates) * THEME_AS_OF_EARLY_FRAC))
    i_late = min(len(dates) - 1, int(len(dates) * THEME_AS_OF_LATE_FRAC))
    as_of = {"early": dates[i_early].isoformat(), "late": dates[i_late].isoformat()}
    rows = [
        (f"TT{idx + 1:0{width}d}", theme, float(exposure), as_of[snap], "seed", "fixture")
        for idx, theme, exposure, snap in THEME_PLAN
        if idx < tickers
    ]
    n = db.upsert_theme_membership(con, rows)
    return {"rows": n, "themes": sorted({r[1] for r in rows}), "as_of": [as_of["early"], as_of["late"]]}


def build(con, *, tickers: int, days: int, seed: int, end: date) -> dict:
    """Populate the source tables on `con` (5 byte-stable + theme_membership). Summary dict."""
    rng = np.random.default_rng(seed)
    dates = trading_days(end, days)

    # Benchmark first (modest positive drift) so RS = excess return has winners and
    # losers around it. spx_daily takes only date + adj_close (db.upsert_spx).
    spx_closes = price_path(rng, days, start=4500.0, mu=0.08, sigma=0.16)
    spx_bars = make_bars(rng, dates, spx_closes)

    # Guaranteed momentum spread across the cross section, shuffled so ticker order
    # is not identical to momentum order.
    mus = np.linspace(0.40, -0.20, tickers)
    rng.shuffle(mus)

    universe_rows: list[dict] = []
    bars_by_ticker: list[tuple[str, list[tuple]]] = []
    funda_by_ticker: list[tuple[str, list[tuple]]] = []
    profile_map: dict[str, list[str]] = {}

    width = max(2, len(str(tickers)))
    for i in range(tickers):
        sym = f"TT{i + 1:0{width}d}"
        start_price = float(rng.uniform(15.0, 500.0))
        sigma = float(rng.uniform(0.25, 0.60))
        shares = float(rng.uniform(1e8, 4e9))

        closes = price_path(rng, days, start_price, float(mus[i]), sigma)
        bars = make_bars(rng, dates, closes)
        last_close = float(closes[-1])
        mktcap = shares * last_close

        profile = profile_for(i)
        profile_map.setdefault(profile, []).append(sym)

        sector = SECTORS[i % len(SECTORS)]
        universe_rows.append({
            "ticker": sym,
            "name": f"Synthetic {sym} Corp",
            "exchange": EXCHANGES[i % len(EXCHANGES)],
            "sector": sector,
            "industry": f"{sector} — Synthetic",
            "country": "United States",
            "mktcap": mktcap,
        })
        bars_by_ticker.append((sym, bars))
        funda_by_ticker.append((sym, fundamentals_rows(rng, profile, end, last_close, shares)))

    # Land through the production upserts (same path the real ingest uses).
    db.upsert_universe(con, universe_rows, end.isoformat())
    n_bars = sum(db.upsert_bars(con, sym, bars) for sym, bars in bars_by_ticker)
    db.upsert_spx(con, spx_bars)
    n_funda = sum(db.upsert_fundamentals(con, sym, rows) for sym, rows in funda_by_ticker if rows)

    # M3.1: synthetic sector ETF series -> bucket_bars. Drawn LAST among rng consumers so
    # the four tables above stay byte-identical; isolated from the universe cross-section.
    n_bucket = build_bucket_bars(con, rng, dates, days)

    # M4.1: synthetic theme_membership — deterministic (no rng), so ALL five tables above
    # stay byte-identical. Point-in-time multi-as_of membership for the offline M4 chain.
    theme = build_theme_membership(con, dates, tickers)

    return {
        "tickers": tickers,
        "days": days,
        "date_range": (dates[0].isoformat(), dates[-1].isoformat()),
        "bars": n_bars,
        "spx": len(spx_bars),
        "fundamentals": n_funda,
        "bucket_bars": n_bucket,
        "buckets": len(SECTORS),
        "theme_membership": theme["rows"],
        "themes": theme["themes"],
        "theme_as_of": theme["as_of"],
        "profiles": profile_map,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide synthetic fixture for offline verification.")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path (rebuilt from scratch)")
    ap.add_argument("--tickers", type=int, default=DEFAULT_TICKERS, help=f"ticker count (default {DEFAULT_TICKERS}, min 25 recommended)")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS, help=f"trading days (default {DEFAULT_DAYS}, min 260 recommended)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="numpy seed for reproducibility")
    ap.add_argument("--end-date", default=DEFAULT_END, help="latest trading date (ISO; default a fixed anchor, not today)")
    args = ap.parse_args(argv)

    if args.tickers < 2:
        print("[fixture] --tickers must be >= 2 (cross-sectional RS needs a cohort).", file=sys.stderr)
        return 2
    end = date.fromisoformat(args.end_date)

    # Fresh build: a fixture is only-synthetic by definition, so drop any prior DB
    # (real or stale-synthetic) at the target path. data/ is gitignored + derived.
    target = Path(args.db)
    for p in (target, target.with_suffix(target.suffix + ".wal")):
        if p.exists():
            p.unlink()
    print(f"[fixture] rebuilding {args.db} from scratch (synthetic; overwrites any prior DB)")

    con = db.connect(args.db)
    s = build(con, tickers=args.tickers, days=args.days, seed=args.seed, end=end)
    con.close()

    lo, hi = s["date_range"]
    print(f"[fixture] seed={args.seed} tickers={s['tickers']} days={s['days']} ({lo} .. {hi})")
    print(f"[fixture] rows: daily_bars={s['bars']} spx_daily={s['spx']} "
          f"fundamentals_q={s['fundamentals']} bucket_bars={s['bucket_bars']} ({s['buckets']} sectors)")
    print(f"[fixture] theme_membership={s['theme_membership']} "
          f"({len(s['themes'])} themes: {', '.join(s['themes'])}; as_of {s['theme_as_of'][0]} .. {s['theme_as_of'][1]})")
    for prof in ("normal", "loss", "deep_loss", "stale", "overdue", "none"):
        syms = s["profiles"].get(prof, [])
        if syms:
            shown = ", ".join(syms[:6]) + (" …" if len(syms) > 6 else "")
            print(f"    {prof:9} ({len(syms):2}): {shown}")
    print("[fixture] next: make compute  (or)  python3 compute/run.py && python3 compute/valuation.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
