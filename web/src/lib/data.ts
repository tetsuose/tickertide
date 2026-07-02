import type { BoardData, BoardChartDetail, OceanData, OceanDetail, RotationData, ManifestData, StockBundle, StockIndex } from '../types'

// Load the nightly Discovery snapshot (export/board.py -> public/data/board.json, schema v2):
// every stock's card data WITHOUT the chart. Mini-charts load lazily per card via
// loadBoardChart (payload split — full board ~1.2MB brotli → bulk ~51KB; PRD §9.3).
// import.meta.env.BASE_URL respects Vite's base './', so the fetch works from any
// deploy subpath; the optional `?.` keeps it safe under non-Vite runtimes (tests).
export async function loadBoard(signal?: AbortSignal): Promise<BoardData> {
  const base = import.meta.env?.BASE_URL ?? './'
  const res = await fetch(`${base}data/board.json`, { signal })
  if (!res.ok) throw new Error(`board.json HTTP ${res.status}`)
  return (await res.json()) as BoardData
}

// Load one stock's Discovery mini-chart (export/board.py -> public/data/board/<TICKER>.json, v2):
// the ~90d OHLCV+MA chart only. Fetched by the EvidenceCard as it renders, so a session only
// downloads charts for the ~20 names actually shown (board payload split — mirrors loadOceanDetail).
export async function loadBoardChart(ticker: string, signal?: AbortSignal): Promise<BoardChartDetail> {
  const base = import.meta.env?.BASE_URL ?? './'
  const res = await fetch(`${base}data/board/${ticker}.json`, { signal })
  if (!res.ok) throw new Error(`board/${ticker}.json HTTP ${res.status}`)
  return (await res.json()) as BoardChartDetail
}

// Load the nightly Ocean bulk snapshot (export/ocean.py -> public/data/ocean.json, v5): the
// columnar draw fields (ps/rise_pct/cand) for every stock. The hover-only fields are NOT
// here — they load lazily per stock via loadOceanDetail (payload reduction; scales to M6).
export async function loadOcean(signal?: AbortSignal): Promise<OceanData> {
  const base = import.meta.env?.BASE_URL ?? './'
  const res = await fetch(`${base}data/ocean.json`, { signal })
  if (!res.ok) throw new Error(`ocean.json HTTP ${res.status}`)
  return (await res.json()) as OceanData
}

// Load one stock's Ocean hover detail (export/ocean.py -> public/data/ocean/<TICKER>.json, v5):
// the tooltip-only riser/valuation fields (columnar, index-aligned to ocean.json's dates). Fetched on hover
// so a session only ever downloads detail for the names actually inspected (M8 payload split).
export async function loadOceanDetail(ticker: string, signal?: AbortSignal): Promise<OceanDetail> {
  const base = import.meta.env?.BASE_URL ?? './'
  const res = await fetch(`${base}data/ocean/${ticker}.json`, { signal })
  if (!res.ok) throw new Error(`ocean/${ticker}.json HTTP ${res.status}`)
  return (await res.json()) as OceanDetail
}

// Load a nightly Rotation snapshot (export/rotation.py). Two files: sector ->
// rotation.json, theme -> rotation.theme.json (separate weeks axes — the theme index
// starts at its first as_of, M4.4). The web loads the one matching its GICS↔Theme toggle.
export async function loadRotation(
  signal?: AbortSignal,
  bucketType: 'sector' | 'theme' = 'sector',
): Promise<RotationData> {
  const base = import.meta.env?.BASE_URL ?? './'
  const file = bucketType === 'theme' ? 'rotation.theme.json' : 'rotation.json'
  const res = await fetch(`${base}data/${file}`, { signal })
  if (!res.ok) throw new Error(`${file} HTTP ${res.status}`)
  return (await res.json()) as RotationData
}

// Load the nightly freshness manifest (export/manifest.py -> public/data/manifest.json).
export async function loadManifest(signal?: AbortSignal): Promise<ManifestData> {
  const base = import.meta.env?.BASE_URL ?? './'
  const res = await fetch(`${base}data/manifest.json`, { signal })
  if (!res.ok) throw new Error(`manifest.json HTTP ${res.status}`)
  return (await res.json()) as ManifestData
}

// Load one Stock per-name bundle (export/stock_bundle.py -> public/data/stock/<TICKER>.json).
// Lazily fetched when a name is opened (Stock is narrow — one name at a time, M5.4).
export async function loadStockBundle(ticker: string, signal?: AbortSignal): Promise<StockBundle> {
  const base = import.meta.env?.BASE_URL ?? './'
  const res = await fetch(`${base}data/stock/${ticker}.json`, { signal })
  if (!res.ok) throw new Error(`stock/${ticker}.json HTTP ${res.status}`)
  return (await res.json()) as StockBundle
}

// Load the Stock bundle index (ticker list for the per-name selector).
export async function loadStockIndex(signal?: AbortSignal): Promise<StockIndex> {
  const base = import.meta.env?.BASE_URL ?? './'
  const res = await fetch(`${base}data/stock/index.json`, { signal })
  if (!res.ok) throw new Error(`stock/index.json HTTP ${res.status}`)
  return (await res.json()) as StockIndex
}
