#!/usr/bin/env bash
# DevTopology: Task isolation via git worktrees.
# Creates one worktree per task to prevent cross-task pollution.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load config defaults (can be overridden by devtopology.yaml via Make vars)
DEFAULT_BASE="${DEVTOPOLOGY_BASE:-origin/main}"
DEFAULT_WORKTREE_ROOT="${DEVTOPOLOGY_WORKTREE_ROOT:-../.worktrees}"

usage() {
  cat <<'EOF'
Usage:
  scripts/worktree.sh open   --query "<task>" [--kind task|docs|workflow] [--base origin/main] [--root ../.worktrees]
  scripts/worktree.sh status [--base origin/main]
  scripts/worktree.sh check
  scripts/worktree.sh close  [--base origin/main]

Commands:
  open    Create a new dedicated worktree on a new branch.
  status  Print current branch/worktree cleanliness and base diff status.
  check   Fail if current worktree has uncommitted changes.
  close   Check whether the current task is closed / merged / ready for PR.
EOF
}

# --- helpers ---

current_worktree_root() {
  git rev-parse --show-toplevel
}

common_git_dir() {
  local common_dir
  common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
  if [[ "${common_dir}" = /* ]]; then
    echo "${common_dir}"
    return
  fi
  local worktree_root
  worktree_root="$(current_worktree_root)"
  cd "${worktree_root}"
  cd "${common_dir}"
  pwd
}

canonical_repo_root() {
  local common_dir
  common_dir="$(common_git_dir)"
  cd "${common_dir}/.."
  pwd
}

current_branch() {
  git rev-parse --abbrev-ref HEAD
}

is_protected_branch() {
  local branch="${1:-}"
  # Read protected patterns from env (set by Makefile from devtopology.yaml)
  local patterns="${DEVTOPOLOGY_PROTECTED_BRANCHES:-main,master,develop,release/*}"
  IFS=',' read -ra pats <<< "${patterns}"
  for pat in "${pats[@]}"; do
    pat="$(echo "${pat}" | xargs)"  # trim whitespace
    case "${branch}" in
      ${pat}) return 0 ;;
    esac
  done
  return 1
}

dirty_status() {
  git status --porcelain
}

slugify() {
  local value="${1:-}"
  value="$(echo "${value}" | tr '[:upper:]' '[:lower:]')"
  value="$(echo "${value}" | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g')"
  if [[ -z "${value}" ]]; then
    value="task"
  fi
  echo "${value}"
}

# --- commands ---

cmd_check() {
  local repo_root
  repo_root="$(current_worktree_root)"
  cd "${repo_root}"
  if [[ -n "$(dirty_status)" ]]; then
    echo "TASK_GUARD_FAIL reason=dirty_worktree branch=$(current_branch)"
    git status --short
    exit 2
  fi
  echo "TASK_GUARD_OK clean=true branch=$(current_branch)"
}

cmd_status() {
  local base="${DEFAULT_BASE}"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --base) base="${2:-}"; shift 2 ;;
      *) echo "unknown option: $1" >&2; usage; exit 2 ;;
    esac
  done

  local repo_root
  repo_root="$(current_worktree_root)"
  cd "${repo_root}"

  local branch
  branch="$(current_branch)"
  local worktree
  worktree="$(pwd)"
  local dirty_count
  dirty_count="$(dirty_status | wc -l | tr -d ' ')"
  local ahead=0 behind=0

  if git rev-parse --verify "${base}" >/dev/null 2>&1; then
    read -r behind ahead < <(git rev-list --left-right --count "${base}"...HEAD)
  fi

  echo "TASK_STATUS branch=${branch} worktree=${worktree} dirty_count=${dirty_count} base=${base} ahead=${ahead} behind=${behind}"
  if [[ "${dirty_count}" != "0" ]]; then
    git status --short
  fi
}

cmd_open() {
  local query="" kind="task" base="${DEFAULT_BASE}" root="${DEFAULT_WORKTREE_ROOT}"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --query) query="${2:-}"; shift 2 ;;
      --kind)  kind="${2:-}"; shift 2 ;;
      --base)  base="${2:-}"; shift 2 ;;
      --root)  root="${2:-}"; shift 2 ;;
      *) echo "unknown option: $1" >&2; usage; exit 2 ;;
    esac
  done

  if [[ -z "${query}" ]]; then
    echo "missing required --query" >&2
    usage
    exit 2
  fi

  local repo_root
  repo_root="$(canonical_repo_root)"
  cd "${repo_root}"

  git fetch origin --prune --quiet || true

  local slug
  slug="$(slugify "${query}")"
  slug="${slug:0:48}"

  local date_tag
  date_tag="$(date +%Y%m%d)"
  local branch
  case "${kind}" in
    task)     branch="task/${slug}" ;;
    docs)     branch="docs/${date_tag}-${slug}" ;;
    workflow) branch="workflow/${date_tag}-${slug}" ;;
    *) echo "TASK_OPEN_FAIL reason=unknown_kind kind=${kind}" >&2; exit 2 ;;
  esac

  local root_abs
  if [[ "${root}" = /* ]]; then
    root_abs="${root}"
  else
    cd "${repo_root}"
    mkdir -p "${root}"
    cd "${root}"
    root_abs="$(pwd)"
    cd "${repo_root}"
  fi
  mkdir -p "${root_abs}"

  local dir_name="${branch//\//-}"
  local worktree_dir="${root_abs}/${dir_name}"

  if git show-ref --verify --quiet "refs/heads/${branch}"; then
    echo "TASK_OPEN_FAIL reason=branch_exists branch=${branch}" >&2
    exit 2
  fi
  if [[ -e "${worktree_dir}" ]]; then
    echo "TASK_OPEN_FAIL reason=worktree_exists path=${worktree_dir}" >&2
    exit 2
  fi

  git worktree add -b "${branch}" "${worktree_dir}" "${base}"

  echo "TASK_OPENED branch=${branch} path=${worktree_dir} base=${base} kind=${kind}"
  echo "NEXT_STEP: cd ${worktree_dir}"
}

cmd_close() {
  local base="${DEFAULT_BASE}"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --base) base="${2:-}"; shift 2 ;;
      *) echo "unknown option: $1" >&2; usage; exit 2 ;;
    esac
  done

  local repo_root
  repo_root="$(current_worktree_root)"
  cd "${repo_root}"

  local branch
  branch="$(current_branch)"
  if [[ -z "${branch}" || "${branch}" = "HEAD" ]]; then
    echo "TASK_CLOSE_FAIL reason=detached_head" >&2
    exit 2
  fi

  if is_protected_branch "${branch}"; then
    echo "TASK_CLOSE_FAIL reason=protected_branch branch=${branch}" >&2
    exit 2
  fi

  if [[ -n "$(dirty_status)" ]]; then
    echo "TASK_CLOSE_FAIL reason=dirty_worktree branch=${branch}" >&2
    git status --short
    exit 2
  fi

  local ahead=0 behind=0
  if git rev-parse --verify "${base}" >/dev/null 2>&1; then
    read -r behind ahead < <(git rev-list --left-right --count "${base}"...HEAD)
  fi

  local merged=0
  if git rev-parse --verify "${base}" >/dev/null 2>&1 && git merge-base --is-ancestor HEAD "${base}"; then
    merged=1
  fi

  # Try gh CLI for PR status
  local pr_number="" pr_state="none" pr_url=""
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    local pr_json
    pr_json="$(gh pr list --head "${branch}" --json number,state,url --limit 1 2>/dev/null || true)"
    if [[ -n "${pr_json}" && "${pr_json}" != "[]" ]]; then
      IFS=$'\t' read -r pr_number pr_state pr_url < <(
        PR_JSON="${pr_json}" python3 -c "
import json, os
items = json.loads(os.environ['PR_JSON'])
item = items[0] if items else {}
print(item.get('number',''), item.get('state',''), item.get('url',''), sep='\t')
" 2>/dev/null || true
      )
      pr_state="${pr_state:-none}"
    fi
  fi

  local next_action="drop"
  if [[ "${merged}" -eq 1 ]]; then
    next_action="drop"
  elif [[ -n "${pr_number}" ]]; then
    next_action="wait_or_merge"
  elif [[ "${ahead}" != "0" ]]; then
    next_action="open_pr"
  fi

  echo "TASK_CLOSE_OK branch=${branch} clean=true base=${base} ahead=${ahead} behind=${behind} merged=${merged} next_action=${next_action}"
  if [[ -n "${pr_number}" ]]; then
    echo "TASK_CLOSE_PR number=${pr_number} state=${pr_state} url=${pr_url}"
  fi

  case "${next_action}" in
    open_pr)       echo "NEXT_STEP: gh pr create --fill" ;;
    wait_or_merge) echo "NEXT_STEP: watch existing PR until merge" ;;
    drop)          echo "NEXT_STEP: remove merged or empty worktree" ;;
  esac
}

# --- main ---

main() {
  if [[ $# -lt 1 ]]; then usage; exit 2; fi
  local cmd="$1"; shift
  case "${cmd}" in
    open)   cmd_open "$@" ;;
    status) cmd_status "$@" ;;
    check)  cmd_check ;;
    close)  cmd_close "$@" ;;
    *) echo "unknown command: ${cmd}" >&2; usage; exit 2 ;;
  esac
}

main "$@"
