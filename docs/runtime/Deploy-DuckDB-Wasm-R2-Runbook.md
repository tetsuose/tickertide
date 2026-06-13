# Deploy Runbook — duckdb-wasm on Cloudflare R2 (M5.2 Valuation screener)

> One-time operator setup so the Valuation screener's duckdb-wasm bundle is served from
> Cloudflare R2 instead of the Pages deploy. **Why R2:** the duckdb wasm is **35–41 MB**,
> over Cloudflare Pages' **25 MiB per-file cap** — a Pages deploy that bundled it would
> fail. R2 is the user's own object store (no third-party CDN), so the spine holds: data
> (`valuation.parquet`) stays self-hosted on Pages; only the static wasm **library** is
> offloaded. Until R2 is configured the client falls back to the jsDelivr CDN, so the site
> and nightly build are safe before this is done.

## What the client does

`web/src/lib/duckdb.ts` picks bundle URLs at build time:
- `VITE_DUCKDB_R2_BASE` set → `${base}/duckdb-{mvp,eh}.wasm` + `…worker.js` from R2.
- unset → `duckdb.getJsDelivrBundles()` (dev / pre-R2 fallback).

The wasm is **never** in `web/dist` either way (loaded from a URL), so Pages stays under the
cap. The worker URL is cross-origin, so the client wraps it in a same-origin blob that
`importScripts` it.

## One-time setup

1. **Create the R2 bucket** (Cloudflare dashboard → R2): e.g. `tickertide-wasm`.
2. **Public access**: enable the bucket's `r2.dev` URL, or bind a custom domain
   (e.g. `wasm.tickertide.<domain>`). Note the base URL.
3. **CORS**: allow `GET` from the Pages origin so the browser can fetch the wasm:
   ```json
   [{ "AllowedOrigins": ["https://tickertide.pages.dev"], "AllowedMethods": ["GET"],
      "AllowedHeaders": ["*"] }]
   ```
4. **Upload the bundle** (static; redo only on a duckdb-wasm version bump):
   ```bash
   cd web && npm ci         # ensures node_modules/@duckdb/duckdb-wasm/dist exists
   R2_BUCKET=tickertide-wasm bash scripts/upload-duckdb-wasm-r2.sh
   ```
   (wrangler logged in, or awscli with `R2_S3_ENDPOINT` set to the R2 S3 endpoint.)
5. **Point the build at R2**: set the GitHub **repo variable** (not a secret — it's a public
   URL) `DUCKDB_R2_BASE` to the bucket's public base URL. `nightly.yml` bakes it into
   `VITE_DUCKDB_R2_BASE` at build time.

## Verify

- After a nightly run, open the deployed site → Valuation tab. The browser fetches
  `duckdb-eh.wasm` (or mvp) from the R2 base; the table renders the full cross-section.
- Network tab: the wasm request goes to the R2 base URL with a 200 (CORS ok), not to
  `web/dist`.

## Credentials

R2 API token / `wrangler login` creds live ONLY locally or in the operator's environment,
never in the repo (same rule as the Pages token — see Credentials-Management.md).
`DUCKDB_R2_BASE` is a public URL, safe as a repo variable. Creating the bucket and binding
the domain are account-level actions the operator performs in Cloudflare.
