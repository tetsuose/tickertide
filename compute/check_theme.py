"""M4.6 acceptance check — AC-M4 invariants on the DuckDB after a pipeline run (PRD §14).

Usage: python3 compute/check_theme.py [--db data/tickertide.duckdb]

Asserts the three AC-M4 properties:
  1. shape  — >=4 themes hold point-in-time membership rows with exposure in (0,1] and a
              non-empty approved_by (C6: every row names who let it in, even 'seed').
  2. C3     — restating a membership at a LATER as_of must not rewrite index history:
              rebuild one theme's index inside a rolled-back transaction after an
              exposure=0 restatement and require the pre-restatement segment to be
              byte-identical (build_theme_index is pure read, so no bucket_bars write).
  3. C4     — realised index weights are exposure-based and cap-bound (max weight <= cap,
              weights sum to 1) — the operational "not market-cap weighted" guarantee.
Plus the wiring check that bucket_bars/bucket_rrg actually carry theme series (>=4), so
a pipeline that silently skipped compute/theme_index.py or rotation --bucket-type theme
fails here instead of shipping an empty Theme toggle.

Empty theme_membership exits 0 with a SKIP line: `make compute` on a bare DB (before
`make themes`) is a supported state, not an error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compute import db  # noqa: E402
from compute.theme_index import build_theme_index, load_caps, theme_weights_asof, DEFAULT_CAP  # noqa: E402

MIN_THEMES = 4  # AC-M4: ">=4 主题有 point-in-time membership"
EPS = 1e-9


def check_shape(con) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    themes = db.theme_keys(con)
    checks.append((f"membership covers >={MIN_THEMES} themes", len(themes) >= MIN_THEMES,
                   f"{len(themes)} themes: {', '.join(themes)}"))

    bad_exp = con.execute(
        "SELECT count(*) FROM theme_membership WHERE exposure < 0 OR exposure > 1"
    ).fetchone()[0]
    checks.append(("exposure within [0,1]", bad_exp == 0, f"{bad_exp} out-of-range rows"))

    no_appr = con.execute(
        "SELECT count(*) FROM theme_membership WHERE approved_by IS NULL OR trim(approved_by) = ''"
    ).fetchone()[0]
    checks.append(("approved_by present on every row (C6)", no_appr == 0, f"{no_appr} unattributed rows"))
    return checks


def _pick_c3_theme(con, caps: dict[str, float]) -> tuple[str, float] | None:
    """A theme whose latest membership has >=2 priced members — dropping one must move
    the index, so the C3 probe can also prove the restatement actually took effect."""
    for th in db.theme_keys(con):
        cap = caps.get(th, DEFAULT_CAP)
        rows = build_theme_index(con, th, cap)
        if len(rows) < 10:
            continue
        if len(theme_weights_asof(con, th, rows[-1][0], cap)) >= 2:
            return th, cap
    return None


def check_c3_no_retro(con, caps: dict[str, float]) -> list[tuple[str, bool, str]]:
    picked = _pick_c3_theme(con, caps)
    if picked is None:
        return [("C3 probe found a multi-member theme", False,
                 "no theme with >=2 priced members and >=10 index days")]
    th, cap = picked

    before = build_theme_index(con, th, cap)
    cut_i = (len(before) * 3) // 4                       # restate ~75% into the series
    cut = before[cut_i][0]
    last_asof = con.execute(
        "SELECT max(CAST(as_of_date AS VARCHAR)) FROM theme_membership WHERE theme = ?", [th]
    ).fetchone()[0]
    if cut <= last_asof:
        cut = before[-2][0]                              # fixture as_ofs sit late: cut later
    victim = max(theme_weights_asof(con, th, before[-1][0], cap).items(), key=lambda kv: kv[1])[0]

    con.execute("BEGIN TRANSACTION")
    try:
        db.upsert_theme_membership(con, [(victim, th, 0.0, cut, "check", "check_theme-c3-probe")])
        after = build_theme_index(con, th, cap)
    finally:
        con.execute("ROLLBACK")

    n_pre = sum(1 for d, _ in before if d < cut)
    history_intact = before[:n_pre] == after[:n_pre]
    tail_moved = before[n_pre:] != after[n_pre:]
    return [
        (f"C3 history immutable under late restatement ({th}, drop {victim} @ {cut})",
         history_intact, f"{n_pre} pre-restatement days byte-identical"),
        ("C3 probe restatement visibly re-weights the tail",
         tail_moved, f"{len(before) - n_pre} post-restatement days diverge"),
    ]


def check_c4_weights(con, caps: dict[str, float]) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    latest = con.execute(
        "SELECT max(CAST(date AS VARCHAR)) FROM bucket_bars WHERE bucket_type='theme'"
    ).fetchone()[0]
    if latest is None:
        return [("C4 weights inspectable", False, "bucket_bars has no theme rows")]
    worst = ""
    ok_cap = ok_sum = True
    for th in db.theme_keys(con):
        cap = caps.get(th, DEFAULT_CAP)
        w = theme_weights_asof(con, th, latest, cap)
        if not w:
            continue
        # cap binds only when feasible (cap*n>1); else capped_weights falls back to equal
        bound = cap if cap * len(w) > 1.0 else (1.0 / len(w))
        mx, s = max(w.values()), sum(w.values())
        if mx > bound + 1e-6:
            ok_cap, worst = False, f"{th}: max weight {mx:.3f} > bound {bound:.3f}"
        if abs(s - 1.0) > 1e-6:
            ok_sum, worst = False, f"{th}: weights sum {s:.6f} != 1"
    checks.append(("C4 single-name weight cap-bound (not mktcap-weighted)", ok_cap,
                   worst or f"all themes <= cap as of {latest}"))
    checks.append(("C4 weights normalised (sum = 1)", ok_sum, worst or "all themes sum to 1"))
    return checks


def check_series_wiring(con) -> list[tuple[str, bool, str]]:
    nb = con.execute(
        "SELECT count(DISTINCT bucket) FROM bucket_bars WHERE bucket_type='theme'"
    ).fetchone()[0]
    nr = con.execute(
        "SELECT count(DISTINCT bucket) FROM bucket_rrg WHERE bucket_type='theme'"
    ).fetchone()[0]
    return [
        (f"theme index landed (>={MIN_THEMES} bucket_bars series)", nb >= MIN_THEMES, f"{nb} themes"),
        (f"theme RS-Ratio landed (>={MIN_THEMES} bucket_rrg series)", nr >= MIN_THEMES, f"{nr} themes"),
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide M4.6 acceptance check (AC-M4).")
    ap.add_argument("--db", default=str(db.DB_PATH), help="DuckDB file path")
    args = ap.parse_args(argv)

    con = db.connect(args.db)
    if db.count(con, "theme_membership") == 0:
        print("[check-theme] SKIP theme_membership empty — run `make themes` (or the fixture) first.")
        con.close()
        return 0

    caps = load_caps()
    checks = (check_shape(con) + check_series_wiring(con)
              + check_c3_no_retro(con, caps) + check_c4_weights(con, caps))

    print("AC-M4 checks:")
    all_ok = True
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} ({detail})")
        all_ok = all_ok and ok
    print(f"\nCHECK_{'OK' if all_ok else 'FAIL'}")
    con.close()
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
