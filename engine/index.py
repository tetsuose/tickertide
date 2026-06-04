#!/usr/bin/env python3
"""DevTopology: Development topology for AI coding agents.

Provides: Mirror (file inventory) / Atlas (module aggregation) / File-Contracts
(per-file purpose/invariants/verification) / Writeback (drift detection+fix) /
Enforce-Fill (module scope gate) / Gate Report (structured pass/fail parsing).

Intentionally uses only Python stdlib -- no pip install required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def find_repo_root() -> Path:
    """Walk up from CWD to find the git root."""
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    return Path.cwd()


def load_config(repo_root: Path) -> dict[str, Any]:
    """Load devtopology.yaml from repo root, with sane defaults."""
    defaults: dict[str, Any] = {
        "ledger": "docs/runtime/File-Contracts.json",
        "index_dir": ".index",
        "exclude": ["vendor/", "node_modules/", ".cache/", "dist/", "build/"],
        "fill_allowed_stages": ["planned", "implemented", "verified", "done"],
        "fill_exempt": ["docs/runtime/File-Contracts.json"],
    }
    config_path = repo_root / "devtopology.yaml"
    if not config_path.exists():
        return defaults

    # Minimal YAML parser -- avoids PyYAML dependency.
    # Handles flat keys and simple lists only.
    try:
        raw = config_path.read_text(encoding="utf-8")
        parsed = _parse_simple_yaml(raw)
        for key in defaults:
            if key in parsed:
                defaults[key] = parsed[key]
    except Exception:
        pass
    return defaults


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse a minimal subset of YAML (flat keys + simple lists)."""
    result: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] | None = None

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Detect list item
        if stripped.startswith("- "):
            value = stripped[2:].strip().strip('"').strip("'")
            if current_list is not None:
                current_list.append(value)
            continue

        # Detect key: value
        if ":" in stripped:
            if current_key and current_list is not None:
                result[current_key] = current_list
                current_list = None

            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")

            if val:
                result[key] = val
                current_key = key
                current_list = None
            else:
                # Next lines may be a list
                current_key = key
                current_list = []

    if current_key and current_list is not None:
        result[current_key] = current_list

    return result


# ---------------------------------------------------------------------------
# Globals -- set by main() after config load
# ---------------------------------------------------------------------------

REPO_ROOT: Path = Path(".")
INDEX_DIR: Path = Path(".index")
MIRROR_PATH: Path = Path(".index/mirror/project-mirror-latest.json")
ATLAS_PATH: Path = Path(".index/atlas/repo-atlas-latest.json")
CONTRACT_SNAPSHOT_PATH: Path = Path(".index/contracts/file-contracts-latest.json")
ATLAS_PACK_PATH: Path = Path(".index/context/atlas-pack-latest.md")
WRITEBACK_DIR: Path = Path(".index/writeback")
HEALTH_DIR: Path = Path(".index/health")
FILL_SCOPE_REPORT_PATH: Path = Path(".index/health/fill-scope-latest.json")
SEMANTIC_GATE_REPORT_PATH: Path = Path(".index/health/changed-file-contract-semantic-latest.json")
LEDGER_PATH: Path = Path("docs/runtime/File-Contracts.json")

CONFIG: dict[str, Any] = {}


def init_paths(repo_root: Path, config: dict[str, Any]) -> None:
    """Set global paths from config."""
    global REPO_ROOT, INDEX_DIR, MIRROR_PATH, ATLAS_PATH, CONTRACT_SNAPSHOT_PATH
    global ATLAS_PACK_PATH, WRITEBACK_DIR, HEALTH_DIR, FILL_SCOPE_REPORT_PATH
    global SEMANTIC_GATE_REPORT_PATH, LEDGER_PATH, CONFIG

    REPO_ROOT = repo_root
    CONFIG = config
    INDEX_DIR = repo_root / config["index_dir"]
    MIRROR_PATH = INDEX_DIR / "mirror" / "project-mirror-latest.json"
    ATLAS_PATH = INDEX_DIR / "atlas" / "repo-atlas-latest.json"
    CONTRACT_SNAPSHOT_PATH = INDEX_DIR / "contracts" / "file-contracts-latest.json"
    ATLAS_PACK_PATH = INDEX_DIR / "context" / "atlas-pack-latest.md"
    WRITEBACK_DIR = INDEX_DIR / "writeback"
    HEALTH_DIR = INDEX_DIR / "health"
    FILL_SCOPE_REPORT_PATH = HEALTH_DIR / "fill-scope-latest.json"
    SEMANTIC_GATE_REPORT_PATH = HEALTH_DIR / "changed-file-contract-semantic-latest.json"
    LEDGER_PATH = repo_root / config["ledger"]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALWAYS_EXCLUDED_PREFIXES = (".git/", ".index/")
ALWAYS_EXCLUDED_NAMES = {".DS_Store"}

CODE_EXTS = {
    ".go", ".php", ".js", ".ts", ".tsx", ".jsx", ".vue", ".css", ".scss",
    ".html", ".sql", ".c", ".cc", ".cpp", ".h", ".hpp", ".java", ".rs",
    ".rb", ".swift", ".kt", ".scala", ".lua", ".zig", ".ex", ".exs",
}
SCRIPT_EXTS = {".sh", ".py", ".zsh", ".bash"}
CONFIG_EXTS = {
    ".yaml", ".yml", ".json", ".toml", ".ini", ".env", ".conf",
    ".service", ".cfg", ".properties", ".xml",
}
DOC_EXTS = {".md", ".txt", ".rst"}

POLICY_STAGE_VALUES = [
    "scaffolded", "baseline", "planned", "implemented",
    "verified", "done", "deprecated",
]

REQUIRED_CONTRACT_FIELDS = ("purpose", "invariants", "verification")
PLACEHOLDER_EXACT_VALUES = {"", "n/a", "na", "none", "null", "placeholder", "tbd", "todo"}
PLACEHOLDER_PREFIXES = ("placeholder", "tbd", "to be defined", "to be filled", "todo")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return deepcopy(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(fallback)


def run_git_lines(args: list[str]) -> list[str]:
    proc = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# File discovery & classification
# ---------------------------------------------------------------------------

def _excluded_prefixes() -> tuple[str, ...]:
    """Merge always-excluded with user-configured exclude globs."""
    extras = tuple(
        p if p.endswith("/") else p + "/"
        for p in CONFIG.get("exclude", [])
    )
    return ALWAYS_EXCLUDED_PREFIXES + extras


def is_excluded(path: str) -> bool:
    prefixes = _excluded_prefixes()
    if any(path.startswith(p) for p in prefixes):
        return True
    if "/__pycache__/" in f"/{path}/":
        return True
    base = Path(path).name
    if base in ALWAYS_EXCLUDED_NAMES or base.endswith(".pyc"):
        return True
    return False


def list_repo_files() -> list[str]:
    tracked = run_git_lines(["ls-files"])
    untracked = run_git_lines(["ls-files", "--others", "--exclude-standard"])
    combined = sorted(set(tracked + untracked))
    files: list[str] = []
    for rel in combined:
        if is_excluded(rel):
            continue
        full = REPO_ROOT / rel
        if not full.exists() or not full.is_file():
            continue
        files.append(rel)
    return files


def guess_module(path: str) -> str:
    parts = path.split("/")
    return parts[0] if len(parts) > 1 else "."


def detect_binary(path: str) -> bool:
    full = REPO_ROOT / path
    try:
        with full.open("rb") as f:
            return b"\x00" in f.read(4096)
    except Exception:
        return False


def guess_kind(path: str) -> str:
    p = Path(path)
    ext = p.suffix.lower()
    lower = path.lower()

    if p.name.startswith(".env"):
        return "config"
    if path.startswith("docs/") or ext in DOC_EXTS:
        return "doc"
    if path.startswith("tests/") or "/tests/" in lower or lower.endswith("_test.go") or lower.endswith("_test.py"):
        return "test"
    if p.name in {"Makefile", "Dockerfile", "Containerfile"}:
        return "script"
    if ext in SCRIPT_EXTS:
        return "script"
    if ext in CONFIG_EXTS or p.name in {".gitignore", ".gitattributes", ".editorconfig"}:
        return "config"
    if ext in CODE_EXTS:
        return "code"
    if detect_binary(path):
        return "asset_binary"
    return "asset"


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

def observe_file(path: str) -> dict[str, Any]:
    full = REPO_ROOT / path
    digest = hashlib.sha256()
    line_count = 0
    with full.open("rb") as f:
        while True:
            chunk = f.read(128 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            line_count += chunk.count(b"\n")
    stat = full.stat()
    return {"bytes": int(stat.st_size), "lines": line_count, "sha256": digest.hexdigest()}


def structure_digest(files: list[str], observed: dict[str, dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for rel in files:
        h.update(f"{rel}:{observed[rel]['sha256']}\n".encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Ledger (File-Contracts.json)
# ---------------------------------------------------------------------------

def default_contract(kind: str) -> dict[str, str]:
    purpose_map = {
        "code": "TODO: define behavior and boundaries",
        "doc": "TODO: define documentation contract",
        "test": "TODO: define assertions and coverage intent",
        "config": "TODO: define knobs and compatibility contract",
        "script": "TODO: define operator workflow and side effects",
        "asset": "TODO: define asset usage contract",
        "asset_binary": "TODO: define binary provenance and usage contract",
    }
    return {
        "purpose": purpose_map.get(kind, "TODO: define purpose"),
        "invariants": "TODO",
        "verification": "TODO",
    }


def default_ledger() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": now_iso(),
        "policy": {
            "stage_values": POLICY_STAGE_VALUES,
            "replan_rule": "When repo structure changes, run `make writeback-apply WRITE=1` before continuing.",
        },
        "entries": [],
        "retired_entries": [],
    }


def normalize_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = deepcopy(ledger) if isinstance(ledger, dict) else {}
    defaults = default_ledger()
    out.setdefault("version", defaults["version"])
    out.setdefault("updated_at", defaults["updated_at"])
    out.setdefault("policy", deepcopy(defaults["policy"]))
    out.setdefault("entries", [])
    out.setdefault("retired_entries", [])
    if not isinstance(out.get("policy"), dict):
        out["policy"] = deepcopy(defaults["policy"])
    if not isinstance(out.get("entries"), list):
        out["entries"] = []
    if not isinstance(out.get("retired_entries"), list):
        out["retired_entries"] = []
    return out


def normalize_contract_payload(value: Any, kind: str) -> dict[str, str]:
    payload = default_contract(kind)
    if isinstance(value, dict):
        for key in payload:
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                payload[key] = raw.strip()
    return payload


def default_stage(line_count: int) -> str:
    return "scaffolded" if line_count == 0 else "baseline"


def merge_ledger_entries(
    files: list[str],
    observed: dict[str, dict[str, Any]],
    ledger: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str], list[dict[str, Any]]]:
    policy_stage_set = set(POLICY_STAGE_VALUES)
    existing_map: dict[str, dict[str, Any]] = {}
    for row in ledger.get("entries", []):
        if isinstance(row, dict):
            path = row.get("path")
            if isinstance(path, str) and path:
                existing_map[path] = row

    merged: list[dict[str, Any]] = []
    added_paths: list[str] = []

    for rel in files:
        existing = existing_map.get(rel, {})
        kind = guess_kind(rel)
        module = guess_module(rel)
        stage = existing.get("stage") if isinstance(existing.get("stage"), str) else None
        if stage not in policy_stage_set:
            stage = default_stage(observed[rel]["lines"])
        contract = normalize_contract_payload(existing.get("contract"), kind)

        entry: dict[str, Any] = {}
        if isinstance(existing, dict):
            for key, value in existing.items():
                if key not in {"path", "kind", "module", "stage", "contract"}:
                    entry[key] = value
        entry.update({"path": rel, "kind": kind, "module": module, "stage": stage, "contract": contract})
        entry.setdefault("notes", "")
        merged.append(entry)
        if rel not in existing_map:
            added_paths.append(rel)

    file_set = set(files)
    stale_paths = sorted(p for p in existing_map if p not in file_set)

    retired_map: dict[str, dict[str, Any]] = {}
    for retired in ledger.get("retired_entries", []):
        if isinstance(retired, dict):
            path = retired.get("path")
            if isinstance(path, str) and path:
                retired_map[path] = retired
    for path in stale_paths:
        if path not in retired_map:
            snapshot = deepcopy(existing_map[path])
            snapshot["removed_at"] = now_iso()
            retired_map[path] = snapshot
    retired_entries = [retired_map[p] for p in sorted(retired_map)]

    return merged, added_paths, stale_paths, retired_entries


def compute_drift(ledger: dict[str, Any], files: list[str]) -> dict[str, list[str]]:
    ledger_paths: set[str] = set()
    for row in ledger.get("entries", []):
        if isinstance(row, dict):
            path = row.get("path")
            if isinstance(path, str) and path:
                ledger_paths.add(path)
    file_set = set(files)
    return {"missing": sorted(file_set - ledger_paths), "stale": sorted(ledger_paths - file_set)}


# ---------------------------------------------------------------------------
# Index builders
# ---------------------------------------------------------------------------

def build_directory_index(files: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    dirs = {"."}
    edges: set[tuple[str, str]] = set()
    for rel in files:
        parts = rel.split("/")
        if len(parts) == 1:
            edges.add(("dir:.", f"file:{rel}"))
            continue
        parent = "."
        prefix_parts: list[str] = []
        for piece in parts[:-1]:
            prefix_parts.append(piece)
            cur = "/".join(prefix_parts)
            dirs.add(cur)
            edges.add((f"dir:{parent}", f"dir:{cur}"))
            parent = cur
        edges.add((f"dir:{parent}", f"file:{rel}"))
    return sorted(dirs), [{"from": f, "to": t, "type": "contains"} for f, t in sorted(edges)]


def build_mirror(
    files: list[str], observed: dict[str, dict[str, Any]],
    entries: list[dict[str, Any]], drift: dict[str, list[str]], digest: str,
) -> dict[str, Any]:
    entry_map = {row["path"]: row for row in entries}
    dirs, edges = build_directory_index(files)
    file_nodes = []
    for rel in files:
        row = entry_map[rel]
        obs = observed[rel]
        file_nodes.append({
            "id": f"file:{rel}", "path": rel, "kind": row["kind"],
            "module": row["module"], "stage": row["stage"],
            "lines": obs["lines"], "bytes": obs["bytes"], "sha256": obs["sha256"],
        })
    warnings = []
    if drift["missing"]:
        warnings.append(f"missing_contract_entries={len(drift['missing'])}")
    if drift["stale"]:
        warnings.append(f"stale_contract_entries={len(drift['stale'])}")
    return {
        "version": 1, "generated_at": now_iso(), "source": "devtopology",
        "structure_digest": digest,
        "meta": {"warnings": warnings, "drift": {
            "missing_contract_entries": len(drift["missing"]),
            "stale_contract_entries": len(drift["stale"]),
        }},
        "stats": {"files": len(files), "directories": len(dirs), "edges": len(edges)},
        "nodes": {
            "directories": [{"id": f"dir:{p}", "path": p, "type": "directory"} for p in dirs],
            "files": file_nodes,
        },
        "edges": edges,
    }


def build_atlas(
    files: list[str], observed: dict[str, dict[str, Any]],
    entries: list[dict[str, Any]], drift: dict[str, list[str]], digest: str,
) -> dict[str, Any]:
    by_module: dict[str, dict[str, Any]] = {}
    by_kind: Counter[str] = Counter()
    by_stage: Counter[str] = Counter()
    by_ext: Counter[str] = Counter()

    for row in entries:
        rel, mod, kind, stage = row["path"], row["module"], row["kind"], row["stage"]
        ext = Path(rel).suffix.lower() or "(none)"
        by_kind[kind] += 1
        by_stage[stage] += 1
        by_ext[ext] += 1
        if mod not in by_module:
            by_module[mod] = {"file_count": 0, "kinds": Counter(), "stages": Counter(), "sample_paths": []}
        slot = by_module[mod]
        slot["file_count"] += 1
        slot["kinds"][kind] += 1
        slot["stages"][stage] += 1
        if len(slot["sample_paths"]) < 12:
            slot["sample_paths"].append(rel)

    module_payload = {}
    for mod in sorted(by_module):
        slot = by_module[mod]
        module_payload[mod] = {
            "file_count": slot["file_count"],
            "kinds": dict(sorted(slot["kinds"].items())),
            "stages": dict(sorted(slot["stages"].items())),
            "sample_paths": slot["sample_paths"],
        }

    total_bytes = sum(observed[p]["bytes"] for p in files)
    total_lines = sum(observed[p]["lines"] for p in files)
    return {
        "version": 1, "generated_at": now_iso(), "source": "devtopology",
        "structure_digest": digest,
        "overview": {
            "file_count": len(files), "total_bytes": total_bytes, "total_lines": total_lines,
            "module_count": len(module_payload),
            "contract_drift": {"missing_entries": len(drift["missing"]), "stale_entries": len(drift["stale"])},
        },
        "breakdown": {
            "kinds": dict(sorted(by_kind.items())),
            "stages": dict(sorted(by_stage.items())),
            "extensions": dict(sorted(by_ext.items(), key=lambda x: (-x[1], x[0]))[:40]),
        },
        "modules": module_payload,
    }


def build_contract_snapshot(
    entries: list[dict[str, Any]], observed: dict[str, dict[str, Any]],
    drift: dict[str, list[str]], digest: str,
) -> dict[str, Any]:
    rows = []
    for row in entries:
        item = deepcopy(row)
        obs = observed[row["path"]]
        item["observed"] = {"lines": obs["lines"], "bytes": obs["bytes"], "sha256": obs["sha256"]}
        rows.append(item)
    return {
        "version": 1, "generated_at": now_iso(), "source": "devtopology",
        "structure_digest": digest,
        "summary": {
            "entry_count": len(rows),
            "missing_contract_entries": len(drift["missing"]),
            "stale_contract_entries": len(drift["stale"]),
        },
        "entries": rows,
    }


def build_atlas_pack(query: str, drift: dict[str, list[str]], atlas: dict[str, Any], digest: str) -> str:
    lines = [
        "# Atlas Pack (latest)", "",
        f"- generated_at: {now_iso()}",
        f"- query: {query or '(none)'}",
        f"- structure_digest: {digest}",
        "",
        "## Structure summary",
        f"- files: {atlas['overview']['file_count']}",
        f"- modules: {atlas['overview']['module_count']}",
        f"- missing contract entries: {len(drift['missing'])}",
        f"- stale contract entries: {len(drift['stale'])}",
        "",
        "## Operator notes",
        "- If structure changed, run `make writeback-preview` then `make writeback-apply WRITE=1`.",
        "- Fill-in workflow: update `File-Contracts.json` stage + contract fields as implementation advances.",
    ]
    if drift["missing"] or drift["stale"]:
        lines.extend(["", "## Drift warnings",
            f"- missing entries: {len(drift['missing'])}",
            f"- stale entries: {len(drift['stale'])}"])
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Sync state (orchestrator)
# ---------------------------------------------------------------------------

def sync_state(query: str, write_ledger: bool) -> dict[str, Any]:
    files = list_repo_files()
    observed = {rel: observe_file(rel) for rel in files}
    digest = structure_digest(files, observed)
    ledger = normalize_ledger(read_json(LEDGER_PATH, default_ledger()))
    drift_before = compute_drift(ledger, files)
    merged_entries, added_paths, stale_paths, retired_entries = merge_ledger_entries(files, observed, ledger)

    if write_ledger:
        ledger["entries"] = merged_entries
        ledger["retired_entries"] = retired_entries
        ledger["updated_at"] = now_iso()
        ledger["last_structure_digest"] = digest
        ensure_parent(LEDGER_PATH)
        LEDGER_PATH.write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        drift = {"missing": [], "stale": []}
    else:
        drift = drift_before

    mirror = build_mirror(files, observed, merged_entries, drift, digest)
    atlas = build_atlas(files, observed, merged_entries, drift, digest)
    contracts = build_contract_snapshot(merged_entries, observed, drift, digest)
    atlas_pack = build_atlas_pack(query, drift, atlas, digest)

    write_json(MIRROR_PATH, mirror)
    write_json(ATLAS_PATH, atlas)
    write_json(CONTRACT_SNAPSHOT_PATH, contracts)
    ensure_parent(ATLAS_PACK_PATH)
    ATLAS_PACK_PATH.write_text(atlas_pack, encoding="utf-8")

    return {
        "files": files, "drift": drift, "added_paths": added_paths,
        "stale_paths": stale_paths, "mirror": mirror, "atlas": atlas,
        "contracts": contracts, "digest": digest, "ledger_written": write_ledger,
    }


# ---------------------------------------------------------------------------
# Writeback reports
# ---------------------------------------------------------------------------

def write_writeback_reports(state: dict[str, Any]) -> dict[str, str]:
    WRITEBACK_DIR.mkdir(parents=True, exist_ok=True)
    missing, stale = state["drift"]["missing"], state["drift"]["stale"]
    summary = {
        "generated_at": now_iso(), "structure_digest": state["digest"],
        "missing_count": len(missing), "stale_count": len(stale),
        "missing_paths": missing, "stale_paths": stale,
        "fix": "make writeback-apply WRITE=1",
    }

    summary_path = WRITEBACK_DIR / "summary-latest.json"
    missing_path = WRITEBACK_DIR / "missing-files-latest.txt"
    stale_path = WRITEBACK_DIR / "stale-files-latest.txt"
    patch_path = WRITEBACK_DIR / "patch-report-latest.md"

    write_json(summary_path, summary)
    missing_path.write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")
    stale_path.write_text("\n".join(stale) + ("\n" if stale else ""), encoding="utf-8")
    patch_lines = [
        "# Writeback Patch Report", "",
        f"- generated_at: {summary['generated_at']}",
        f"- missing_count: {summary['missing_count']}",
        f"- stale_count: {summary['stale_count']}",
        "", "## Fix", "```bash", "make writeback-apply WRITE=1", "```",
    ]
    patch_path.write_text("\n".join(patch_lines).rstrip() + "\n", encoding="utf-8")

    return {
        "summary_report": str(summary_path.relative_to(REPO_ROOT)),
        "missing_report": str(missing_path.relative_to(REPO_ROOT)),
        "stale_report": str(stale_path.relative_to(REPO_ROOT)),
        "patch_report": str(patch_path.relative_to(REPO_ROOT)),
    }


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def gate_line(success: bool, gate: str, **kwargs: Any) -> str:
    tokens = ["GATE_PASS" if success else "GATE_FAIL", f"gate={gate}"]
    for key, value in kwargs.items():
        if isinstance(value, str) and (" " in value or "=" in value or '"' in value):
            escaped = value.replace('"', "'")
            tokens.append(f'{key}="{escaped}"')
        else:
            tokens.append(f"{key}={value}")
    return " ".join(tokens)


def list_changed_paths() -> list[str]:
    changed: set[str] = set()
    for args in [["diff", "--name-only"], ["diff", "--cached", "--name-only"],
                 ["ls-files", "--others", "--exclude-standard"]]:
        changed.update(run_git_lines(args))
    return sorted(changed)


def is_fill_scope_exempt(path: str) -> bool:
    exempt_patterns = CONFIG.get("fill_exempt", [])
    for pattern in exempt_patterns:
        if path == pattern:
            return True
        if pattern.endswith("/") and path.startswith(pattern):
            return True
    return False


def is_placeholder_contract_value(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    normalized = re.sub(r"\s+", " ", value).strip().lower()
    if normalized in PLACEHOLDER_EXACT_VALUES:
        return True
    return any(normalized.startswith(p) for p in PLACEHOLDER_PREFIXES)


def build_entry_map(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entry_map: dict[str, dict[str, Any]] = {}
    for row in ledger.get("entries", []):
        if isinstance(row, dict):
            rel = row.get("path")
            if isinstance(rel, str) and rel:
                entry_map[rel] = row
    return entry_map


def evaluate_changed_file_contracts(ledger: dict[str, Any]) -> dict[str, Any]:
    entry_map = build_entry_map(ledger)
    changed_paths = list_changed_paths()
    exemptions: list[dict[str, str]] = []
    validated_files: list[str] = []
    violations: list[dict[str, Any]] = []

    for rel in changed_paths:
        if is_excluded(rel):
            exemptions.append({"path": rel, "reason": "generated_or_excluded"})
            continue
        if is_fill_scope_exempt(rel):
            exemptions.append({"path": rel, "reason": "explicit_fill_scope_exempt"})
            continue
        full = REPO_ROOT / rel
        if not full.exists() or not full.is_file():
            exemptions.append({"path": rel, "reason": "removed_or_nonfile"})
            continue
        row = entry_map.get(rel)
        if row is None:
            violations.append({"path": rel, "reason": "missing_contract_entry", "fields": list(REQUIRED_CONTRACT_FIELDS)})
            continue
        kind = str(row.get("kind") or guess_kind(rel))
        contract = normalize_contract_payload(row.get("contract"), kind)
        offending = [f for f in REQUIRED_CONTRACT_FIELDS if is_placeholder_contract_value(contract.get(f))]
        if offending:
            violations.append({"path": rel, "reason": "placeholder_contract_fields", "fields": offending,
                               "module": str(row.get("module", "")), "stage": str(row.get("stage", ""))})
            continue
        validated_files.append(rel)

    report = {"generated_at": now_iso(), "changed_files": changed_paths,
              "validated_files": validated_files, "exemptions": exemptions, "violations": violations}
    write_json(SEMANTIC_GATE_REPORT_PATH, report)
    return report


def print_contract_violations(violations: list[dict[str, Any]]) -> None:
    for item in violations:
        fields = item.get("fields", [])
        field_list = ",".join(str(f) for f in fields) if isinstance(fields, list) else ""
        print(f"CONTRACT_VIOLATION path={item.get('path','')} reason={item.get('reason','')} fields={field_list or '-'}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def run_start(query: str, strict: bool) -> int:
    state = sync_state(query=query, write_ledger=False)
    print(f"START_OK files={len(state['files'])} digest={state['digest']}")
    missing, stale = len(state["drift"]["missing"]), len(state["drift"]["stale"])
    if missing or stale:
        print(gate_line(False, "structure_contract_coverage", missing=missing, stale=stale,
                        fix="make writeback-apply WRITE=1"))
        return 2 if strict else 0
    print(gate_line(True, "structure_contract_coverage", files=len(state["files"])))
    return 0


def run_verify() -> int:
    state = sync_state(query="verify", write_ledger=False)
    reports = write_writeback_reports(state)
    ledger = normalize_ledger(read_json(LEDGER_PATH, default_ledger()))
    semantic_report = evaluate_changed_file_contracts(ledger)

    missing, stale = len(state["drift"]["missing"]), len(state["drift"]["stale"])
    coverage_failed = False
    if missing or stale:
        print(gate_line(False, "structure_contract_coverage", missing=missing, stale=stale,
                        missing_report=reports["missing_report"], fix="make writeback-apply WRITE=1"))
        coverage_failed = True
    else:
        print(gate_line(True, "structure_contract_coverage", files=len(state["files"])))

    semantic_violations = semantic_report["violations"]
    semantic_failed = bool(semantic_violations)
    if semantic_failed:
        print_contract_violations(semantic_violations)
        print(gate_line(False, "changed_file_contract_semantics",
                        changed=len(semantic_report["changed_files"]), violations=len(semantic_violations),
                        fix="Fill File-Contracts purpose/invariants/verification for offending changed files."))
    else:
        print(gate_line(True, "changed_file_contract_semantics",
                        changed=len(semantic_report["changed_files"]),
                        validated=len(semantic_report["validated_files"])))
    return 2 if coverage_failed or semantic_failed else 0


def run_health(strict: bool) -> int:
    state = sync_state(query="health", write_ledger=False)
    verify_rc = run_verify()
    summary = {
        "generated_at": now_iso(), "structure_digest": state["digest"],
        "files": len(state["files"]), "modules": state["atlas"]["overview"]["module_count"],
        "kinds": state["atlas"]["breakdown"]["kinds"], "stages": state["atlas"]["breakdown"]["stages"],
        "drift": {"missing": len(state["drift"]["missing"]), "stale": len(state["drift"]["stale"])},
    }
    write_json(HEALTH_DIR / "health-summary-latest.json", summary)
    if verify_rc == 0:
        print(f"HEALTH_OK files={summary['files']} modules={summary['modules']}")
        return 0
    print("HEALTH_WARN verify gate failed; see .index/writeback/* and .index/health/health-summary-latest.json")
    return verify_rc if strict else 0


def run_writeback_preview() -> int:
    state = sync_state(query="writeback-preview", write_ledger=False)
    reports = write_writeback_reports(state)
    print("WRITEBACK_PREVIEW_OK")
    for key in ["summary_report", "missing_report", "stale_report", "patch_report"]:
        print(f"{key}={reports[key]}")
    return 0


def run_writeback_apply(force_write: bool) -> int:
    if not (force_write or os.environ.get("WRITE") == "1"):
        print("WRITEBACK_APPLY_BLOCKED missing WRITE=1; re-run: make writeback-apply WRITE=1")
        return 3
    state = sync_state(query="writeback-apply", write_ledger=True)
    reports = write_writeback_reports(state)
    print(f"WRITEBACK_APPLY_OK files={len(state['files'])} added={len(state['added_paths'])} removed={len(state['stale_paths'])}")
    for key in ["summary_report", "missing_report", "stale_report", "patch_report"]:
        print(f"{key}={reports[key]}")
    return 0


def run_enforce_fill(module: str, allowed_stages_raw: str) -> int:
    # Keep indices fresh
    sync_state(query="enforce-fill", write_ledger=False)

    module = module.strip()
    requested = [s.strip() for s in allowed_stages_raw.split(",") if s.strip()]
    valid = set(POLICY_STAGE_VALUES)
    allowed_stages = [s for s in requested if s in valid] or CONFIG.get("fill_allowed_stages", [])

    ledger = normalize_ledger(read_json(LEDGER_PATH, default_ledger()))
    entry_map = build_entry_map(ledger)
    semantic_report = evaluate_changed_file_contracts(ledger)
    semantic_violations = semantic_report["violations"]
    semantic_violation_paths = {
        item["path"] for item in semantic_violations
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }

    changed_files = semantic_report["changed_files"]
    exempt_items = semantic_report["exemptions"]
    exempt_set = {item["path"] for item in exempt_items if isinstance(item, dict)}

    allowed_files: list[str] = []
    scope_violations: list[dict[str, str]] = []

    for rel in changed_files:
        if rel in exempt_set or rel in semantic_violation_paths:
            continue
        row = entry_map.get(rel)
        if row is None:
            continue
        row_module = str(row.get("module", ""))
        row_stage = str(row.get("stage", ""))
        if module and row_module != module:
            scope_violations.append({"path": rel, "reason": "module_mismatch", "module": row_module})
            continue
        if row_stage not in allowed_stages:
            scope_violations.append({"path": rel, "reason": "stage_not_allowed", "stage": row_stage})
            continue
        allowed_files.append(rel)

    report = {
        "generated_at": now_iso(), "module": module or "(any)",
        "allowed_stages": allowed_stages, "changed_files": changed_files,
        "allowed_files": allowed_files, "exempt_files": exempt_items,
        "scope_violations": scope_violations, "semantic_violations": semantic_violations,
    }
    write_json(FILL_SCOPE_REPORT_PATH, report)

    scope_failed = bool(scope_violations)
    semantic_failed = bool(semantic_violations)

    if scope_failed:
        print(gate_line(False, "fill_queue_scope", changed=len(changed_files),
                        violations=len(scope_violations), fix="Constrain edits to allowed module/stages."))
    else:
        print(gate_line(True, "fill_queue_scope", changed=len(changed_files),
                        allowed=len(allowed_files), module=module or "any"))

    if semantic_failed:
        print_contract_violations(semantic_violations)
        print(gate_line(False, "changed_file_contract_semantics",
                        changed=len(changed_files), violations=len(semantic_violations),
                        fix="Fill File-Contracts purpose/invariants/verification for offending changed files."))
        return 2

    print(gate_line(True, "changed_file_contract_semantics",
                    changed=len(changed_files), validated=len(semantic_report["validated_files"])))
    return 2 if scope_failed else 0


def run_index_like(query: str, mode: str) -> int:
    state = sync_state(query=query, write_ledger=False)
    if mode == "mirror":
        print(f"MIRROR_OK path={MIRROR_PATH.relative_to(REPO_ROOT)} files={len(state['files'])}")
    elif mode == "atlas":
        print(f"ATLAS_OK path={ATLAS_PATH.relative_to(REPO_ROOT)} files={len(state['files'])}")
    elif mode == "context":
        print(f"CONTEXT_OK path={ATLAS_PACK_PATH.relative_to(REPO_ROOT)}")
    else:
        print(f"INDEX_OK mirror={MIRROR_PATH.relative_to(REPO_ROOT)} atlas={ATLAS_PATH.relative_to(REPO_ROOT)}")
    return 0


def run_gate_report(log_path: str) -> int:
    target = (REPO_ROOT / log_path).resolve() if not os.path.isabs(log_path) else Path(log_path)
    if not target.exists():
        print(f"GATE_REPORT_ERROR log_missing={target}")
        return 2
    gate_rows = []
    pattern = re.compile(r"^(GATE_PASS|GATE_FAIL)\s+gate=([^\s]+)(.*)$")
    for raw in target.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pattern.match(raw.strip())
        if not m:
            continue
        status_token, gate, rest = m.groups()
        fix_match = re.search(r'fix="([^"]+)"', rest)
        gate_rows.append({
            "status": "pass" if status_token == "GATE_PASS" else "fail",
            "gate": gate, "raw": raw.strip(), "fix": fix_match.group(1) if fix_match else None,
        })
    report = {
        "generated_at": now_iso(), "log": str(target),
        "total_gates": len(gate_rows),
        "failed_gates": sum(1 for r in gate_rows if r["status"] == "fail"),
        "passed_gates": sum(1 for r in gate_rows if r["status"] == "pass"),
        "gates": gate_rows,
    }
    write_json(HEALTH_DIR / "gate-report-latest.json", report)
    print(f"GATE_REPORT_OK path={HEALTH_DIR.relative_to(REPO_ROOT)}/gate-report-latest.json failed={report['failed_gates']}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="devtopology",
        description="Development topology for AI coding agents",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="Generate atlas-pack + detect drift")
    s.add_argument("--query", default="")
    s.add_argument("--strict", action="store_true")

    sub.add_parser("mirror", help="Generate mirror (file inventory)")
    sub.add_parser("atlas", help="Generate atlas (module aggregation)")

    c = sub.add_parser("context", help="Generate atlas-pack markdown")
    c.add_argument("--query", default="")

    sub.add_parser("verify", help="Run structure + semantic gates")

    h = sub.add_parser("health", help="Full health summary")
    h.add_argument("--strict", action="store_true")

    sub.add_parser("writeback-preview", help="Preview contract drift")

    wa = sub.add_parser("writeback-apply", help="Fix contract drift")
    wa.add_argument("--write", action="store_true")

    ef = sub.add_parser("enforce-fill", help="Module scope gate for changed files")
    ef.add_argument("--module", default="")
    ef.add_argument("--allowed-stages", default="planned,implemented,verified,done")

    gr = sub.add_parser("gate-report", help="Parse GATE_PASS/FAIL from log file")
    gr.add_argument("--log", required=True)

    return parser.parse_args()


def main() -> int:
    repo_root = find_repo_root()
    config = load_config(repo_root)
    init_paths(repo_root, config)

    args = parse_args()

    dispatch: dict[str, Any] = {
        "start": lambda: run_start(args.query, getattr(args, "strict", False)),
        "mirror": lambda: run_index_like("mirror", "mirror"),
        "atlas": lambda: run_index_like("atlas", "atlas"),
        "context": lambda: run_index_like(getattr(args, "query", ""), "context"),
        "verify": run_verify,
        "health": lambda: run_health(getattr(args, "strict", False)),
        "writeback-preview": run_writeback_preview,
        "writeback-apply": lambda: run_writeback_apply(getattr(args, "write", False)),
        "enforce-fill": lambda: run_enforce_fill(
            getattr(args, "module", ""),
            getattr(args, "allowed_stages", "planned,implemented,verified,done"),
        ),
        "gate-report": lambda: run_gate_report(args.log),
    }

    handler = dispatch.get(args.cmd)
    if handler:
        return handler()
    print(f"Unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
