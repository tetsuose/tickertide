#!/usr/bin/env bash
# Upload the duckdb-wasm bundle (wasm + worker) to Cloudflare R2 for the M5.2 Valuation
# screener. The bundle is 35–41 MB — over Cloudflare Pages' 25 MiB per-file cap — so it is
# hosted on R2 (the user's own object store, not a third-party CDN) and the client fetches
# it at runtime via VITE_DUCKDB_R2_BASE. This is an OPERATOR step, run once per duckdb-wasm
# version bump (the wasm is static; it does NOT change nightly). See
# docs/runtime/Deploy-DuckDB-Wasm-R2-Runbook.md for the bucket/CORS/token setup.
#
# Usage:
#   R2_BUCKET=tickertide-wasm bash scripts/upload-duckdb-wasm-r2.sh
# Requires: wrangler (logged in) OR awscli configured for the R2 S3 endpoint.
set -euo pipefail

BUCKET="${R2_BUCKET:?set R2_BUCKET, e.g. tickertide-wasm}"
DIST="web/node_modules/@duckdb/duckdb-wasm/dist"
FILES=(duckdb-mvp.wasm duckdb-eh.wasm duckdb-browser-mvp.worker.js duckdb-browser-eh.worker.js)

for f in "${FILES[@]}"; do
  [ -f "$DIST/$f" ] || { echo "missing $DIST/$f — run 'cd web && npm ci' first" >&2; exit 1; }
done

ctype() { case "$1" in *.wasm) echo application/wasm ;; *) echo text/javascript ;; esac; }

if command -v wrangler >/dev/null 2>&1; then
  echo "[r2-upload] via wrangler -> bucket=$BUCKET"
  for f in "${FILES[@]}"; do
    wrangler r2 object put "$BUCKET/$f" --file "$DIST/$f" --content-type "$(ctype "$f")"
  done
elif command -v aws >/dev/null 2>&1; then
  : "${R2_S3_ENDPOINT:?set R2_S3_ENDPOINT (https://<account>.r2.cloudflarestorage.com) for awscli}"
  echo "[r2-upload] via awscli -> s3://$BUCKET (endpoint $R2_S3_ENDPOINT)"
  for f in "${FILES[@]}"; do
    aws s3 cp "$DIST/$f" "s3://$BUCKET/$f" --endpoint-url "$R2_S3_ENDPOINT" --content-type "$(ctype "$f")"
  done
else
  echo "[r2-upload] need wrangler or awscli on PATH" >&2; exit 1
fi

echo "[r2-upload] done — set the repo variable DUCKDB_R2_BASE to the bucket's public base URL"
echo "            (e.g. https://wasm.tickertide.<domain> or the r2.dev URL) so the nightly"
echo "            web build bakes VITE_DUCKDB_R2_BASE in. Verify CORS allows the Pages origin."
