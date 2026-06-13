// M5.2 duckdb-wasm loader for the Valuation screener (PRD §9.5: query Parquet in the
// browser). duckdb-wasm reads valuation.parquet and does the metric ORDER BY (its core
// value — columnar read + sort, and the path that scales to M6's thousands); scope filter,
// common-vintage percentile, and tri-color rendering stay in JS (Valuation.tsx), since
// theme scope needs membership not in the SQL and percentile is a cohort statistic.
//
// The wasm+worker are loaded from a URL, NOT bundled into the Pages artifact: the duckdb
// wasm is 35–41 MB, over Cloudflare Pages' 25 MiB per-file cap. Production hosts them on
// Cloudflare R2 (the user's own object store — no third-party CDN, spine-compatible:
// data/parquet stays self-hosted, only the static wasm lib is offloaded), pointed to by
// VITE_DUCKDB_R2_BASE. Dev (no env) falls back to the jsDelivr CDN so a local smoke needs
// no R2. Either way the wasm never enters dist/, so the Pages deploy stays under the cap.
import * as duckdb from '@duckdb/duckdb-wasm'
import type { ValuationRow } from '../types'

export type MetricKey = 'ps' | 'pe' | 'evs' | 'ev_ebitda' | 'growth' | 'rule40'

// cheapAsc: cheap-on-top multiples ascend; quality metrics (growth, rule40) descend (§9.5).
export const VALUATION_METRICS: { key: MetricKey; label: string; cheapAsc: boolean }[] = [
  { key: 'ps', label: 'P/S', cheapAsc: true },
  { key: 'pe', label: 'P/E', cheapAsc: true },
  { key: 'evs', label: 'EV/S', cheapAsc: true },
  { key: 'ev_ebitda', label: 'EV/EBITDA', cheapAsc: true },
  { key: 'growth', label: 'Grw%', cheapAsc: false },
  { key: 'rule40', label: 'R40', cheapAsc: false },
]

/** R2 (production) or jsDelivr (dev fallback) bundle URLs. The wasm is never in dist/. */
function bundles(): duckdb.DuckDBBundles {
  const r2 = (import.meta.env?.VITE_DUCKDB_R2_BASE as string | undefined)?.replace(/\/$/, '')
  if (r2) {
    return {
      mvp: { mainModule: `${r2}/duckdb-mvp.wasm`, mainWorker: `${r2}/duckdb-browser-mvp.worker.js` },
      eh: { mainModule: `${r2}/duckdb-eh.wasm`, mainWorker: `${r2}/duckdb-browser-eh.worker.js` },
    }
  }
  return duckdb.getJsDelivrBundles()
}

/** Pure: the screener SELECT for a metric. Sorts cheap-on-top / quality-desc with NULLs
 *  last; scope filtering happens in JS (theme membership isn't a Parquet column we sort on).
 *  Exported so the SQL is unit-tested without spinning up the wasm engine. */
export function buildValuationSql(metric: MetricKey, table = 'valuation'): string {
  const m = VALUATION_METRICS.find((x) => x.key === metric) ?? VALUATION_METRICS[0]
  const dir = m.cheapAsc ? 'ASC' : 'DESC'
  return `SELECT * FROM ${table} ORDER BY ${m.key} ${dir} NULLS LAST, ticker`
}

let dbPromise: Promise<duckdb.AsyncDuckDB> | null = null
let parquetReady: Promise<void> | null = null

async function getDb(): Promise<duckdb.AsyncDuckDB> {
  if (!dbPromise) {
    dbPromise = (async () => {
      const bundle = await duckdb.selectBundle(bundles())
      // The worker URL is cross-origin (R2/CDN); a Worker can't be constructed from a
      // cross-origin script directly, so wrap it in a same-origin blob that importScripts it.
      const workerUrl = URL.createObjectURL(
        new Blob([`importScripts("${bundle.mainWorker}");`], { type: 'text/javascript' }),
      )
      const worker = new Worker(workerUrl)
      const db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(), worker)
      await db.instantiate(bundle.mainModule, bundle.pthreadWorker)
      URL.revokeObjectURL(workerUrl)
      return db
    })()
  }
  return dbPromise
}

async function ensureParquet(db: duckdb.AsyncDuckDB): Promise<void> {
  if (!parquetReady) {
    parquetReady = (async () => {
      const base = import.meta.env?.BASE_URL ?? './'
      const res = await fetch(`${base}data/valuation.parquet`)
      if (!res.ok) throw new Error(`valuation.parquet HTTP ${res.status}`)
      const buf = new Uint8Array(await res.arrayBuffer())
      await db.registerFileBuffer('valuation.parquet', buf)
      const conn = await db.connect()
      // strftime the DATE columns to ISO strings in the view: duckdb-wasm's Arrow->JSON
      // returns DATE as epoch-millis, which would render as a raw number. Doing it in SQL
      // keeps the client free of date-coercion and matches the .sample.json fixture shape.
      await conn.query(
        `CREATE VIEW valuation AS SELECT * REPLACE (
           strftime(as_of_period_end, '%Y-%m-%d') AS as_of_period_end,
           strftime(as_of_filed, '%Y-%m-%d') AS as_of_filed
         ) FROM read_parquet('valuation.parquet')`,
      )
      await conn.close()
    })()
  }
  return parquetReady
}

/** Load + sort the full-universe cross-section via duckdb-wasm. Returns plain rows; the
 *  view (Valuation.tsx) applies scope/percentile/coloring. Throws if wasm or fetch fails. */
export async function queryValuation(metric: MetricKey): Promise<ValuationRow[]> {
  const db = await getDb()
  await ensureParquet(db)
  const conn = await db.connect()
  try {
    const result = await conn.query(buildValuationSql(metric))
    return result.toArray().map((r) => r.toJSON() as ValuationRow)
  } finally {
    await conn.close()
  }
}
