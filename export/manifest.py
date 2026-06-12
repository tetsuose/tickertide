"""D.4 freshness manifest: web/public/data/*.json -> manifest.json.

A tiny freshness/health descriptor (latest as_of + per-surface counts) so the web client
shows an as_of badge + data age WITHOUT loading a full surface JSON, and so D.3's deploy
can gate on freshness (don't publish stale). Reads the exports board/ocean/rotation
already wrote; run AFTER them (Makefile `export` wires this last).

Output (gitignored, derived nightly): web/public/data/manifest.json.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "web" / "public" / "data"
SCHEMA_VERSION = 1
SURFACES = ("board", "ocean", "rotation", "rotation.theme")


def build_manifest(data_dir: Path, generated_at: str | None = None) -> dict:
    """Latest as_of + per-surface counts from the exported JSONs. Missing surface -> None
    (so a partial export is visible, not silently treated as complete)."""
    surfaces: dict[str, int | None] = {}
    as_ofs: list[str] = []
    for name in SURFACES:
        p = data_dir / f"{name}.json"
        if not p.exists():
            surfaces[name] = None
            continue
        d = json.loads(p.read_text())
        surfaces[name] = d.get("count")
        if d.get("as_of_date"):
            as_ofs.append(d["as_of_date"])
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": max(as_ofs) if as_ofs else None,  # latest across surfaces
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "surfaces": surfaces,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TickerTide D.4 export: freshness manifest.json.")
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA))
    ap.add_argument("--out", default=str(DEFAULT_DATA / "manifest.json"))
    args = ap.parse_args(argv)

    m = build_manifest(Path(args.data_dir))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(m, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"[manifest] {args.out}  as_of={m['as_of_date']}  surfaces={m['surfaces']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
