"""M4.5 acceptance — land + point-in-time precedence of approved membership (C3, C6).

Self-contained (builds its own temp DuckDB via db.connect, which applies the schema), so
it runs in CI with no network and no prior pipeline. For EACH row in themes/approved/*.json
it asserts the invariants that make the human-approved layer correct on top of the seed
baseline:

  C6  approved_by is a non-empty human name (never blank, never a bot sentinel).
  C3  forward:  at the approval's as_of_date the PIT query resolves the APPROVED exposure,
                even when an earlier coarse seed row exists for the same (ticker, theme).
      backward: one day BEFORE the approval the PIT query still resolves the OLD seed value
                — approving must not retroactively rewrite history.

This guards themes/land.py + compute/db.theme_membership_asof against regressions; the
demo data (themes/approved/NVDA.json) doubles as the fixture.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compute import db  # noqa: E402
from themes import land  # noqa: E402

SEED_SENTINEL = 0.111  # an obviously-distinct earlier value so a precedence bug is visible


def run_checks() -> list[tuple[str, bool, str]]:
    rows = land.load_approved_rows()
    checks: list[tuple[str, bool, str]] = []
    checks.append(("approved files present", bool(rows), f"{len(rows)} approved row(s)"))
    if not rows:
        return checks

    tmp = Path(tempfile.mkdtemp()) / "check_land.duckdb"
    con = db.connect(tmp)
    db.clear_theme_membership(con)

    for ticker, theme, exp, as_of, src, by in rows:
        checks.append((f"{ticker}/{theme} approved_by present (C6)",
                       bool(str(by).strip()) and src != "seed", f"by={by} source={src}"))
        earlier = (date.fromisoformat(as_of) - timedelta(days=1)).isoformat()
        # earlier coarse seed row for the SAME (ticker, theme), distinct exposure
        db.upsert_theme_membership(con, [(ticker, theme, SEED_SENTINEL, earlier, "seed", "seed")])
        db.upsert_theme_membership(con, [(ticker, theme, exp, as_of, src, by)])

        fwd = db.theme_membership_asof(con, as_of, ticker=ticker, theme=theme)
        fwd_ok = len(fwd) == 1 and abs(float(fwd.iloc[0].exposure) - exp) < 1e-9 \
            and fwd.iloc[0].approved_by == by
        checks.append((f"{ticker}/{theme} C3 forward: approved wins @ {as_of}",
                       fwd_ok, f"resolved exposure={float(fwd.iloc[0].exposure):.2f} by={fwd.iloc[0].approved_by}"
                       if len(fwd) else "no row resolved"))

        bwd = db.theme_membership_asof(con, earlier, ticker=ticker, theme=theme)
        bwd_ok = len(bwd) == 1 and abs(float(bwd.iloc[0].exposure) - SEED_SENTINEL) < 1e-9
        checks.append((f"{ticker}/{theme} C3 backward: pre-approval intact @ {earlier}",
                       bwd_ok, f"resolved exposure={float(bwd.iloc[0].exposure):.3f} (want {SEED_SENTINEL})"
                       if len(bwd) else "no row resolved"))
        db.clear_theme_membership(con)  # isolate each row's probe

    con.close()
    return checks


def main(argv: list[str] | None = None) -> int:
    checks = run_checks()
    print("M4.5 land/PIT checks:")
    all_ok = True
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} ({detail})")
        all_ok = all_ok and ok
    print(f"\nCHECK_{'OK' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
