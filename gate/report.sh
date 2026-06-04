#!/usr/bin/env bash
# DevTopology: Standalone gate report parser.
# Reads a log file, extracts GATE_PASS/GATE_FAIL lines, outputs JSON summary.
#
# Usage:
#   bash gate/report.sh <log-file>
#   bash gate/report.sh .index/health/verify-output-latest.log
#
# Output: JSON to stdout with pass/fail counts and gate details.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: gate/report.sh <log-file>" >&2
  exit 2
fi

LOG_FILE="$1"

if [[ ! -f "${LOG_FILE}" ]]; then
  echo "GATE_REPORT_ERROR log_missing=${LOG_FILE}" >&2
  exit 2
fi

passed=0
failed=0
gates_json="["
first=true

while IFS= read -r line; do
  # Match GATE_PASS or GATE_FAIL lines
  if [[ "${line}" =~ ^(GATE_PASS|GATE_FAIL)[[:space:]]+gate=([^[:space:]]+)(.*) ]]; then
    status_token="${BASH_REMATCH[1]}"
    gate_name="${BASH_REMATCH[2]}"
    rest="${BASH_REMATCH[3]}"

    if [[ "${status_token}" == "GATE_PASS" ]]; then
      status="pass"
      ((passed++)) || true
    else
      status="fail"
      ((failed++)) || true
    fi

    # Extract fix="..." if present
    fix=""
    if [[ "${rest}" =~ fix=\"([^\"]+)\" ]]; then
      fix="${BASH_REMATCH[1]}"
    fi

    # Escape special chars for JSON
    escaped_line="${line//\\/\\\\}"
    escaped_line="${escaped_line//\"/\\\"}"
    escaped_fix="${fix//\\/\\\\}"
    escaped_fix="${escaped_fix//\"/\\\"}"

    if [[ "${first}" == "true" ]]; then
      first=false
    else
      gates_json+=","
    fi

    if [[ -n "${fix}" ]]; then
      gates_json+="{\"status\":\"${status}\",\"gate\":\"${gate_name}\",\"fix\":\"${escaped_fix}\",\"raw\":\"${escaped_line}\"}"
    else
      gates_json+="{\"status\":\"${status}\",\"gate\":\"${gate_name}\",\"fix\":null,\"raw\":\"${escaped_line}\"}"
    fi
  fi
done < "${LOG_FILE}"

gates_json+="]"
total=$((passed + failed))

cat <<EOF
{"total_gates":${total},"passed_gates":${passed},"failed_gates":${failed},"gates":${gates_json}}
EOF

if [[ "${failed}" -gt 0 ]]; then
  exit 1
fi
