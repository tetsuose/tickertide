// TypeScript types mirroring export/board.py's board.json (M1.1 contract).
// The client re-weights composite from `components` by the early<->reliable knob
// k WITHOUT recomputing the engine (C9); those coefficients port to composite.ts
// in M1.4. Numeric fields are nullable wherever the engine can emit no value
// (insufficient history, E<=0 valuation, missing fundamentals).

export type Freshness = 'fresh' | 'stale' | 'overdue'

/** 5 raw composite components ∈ [0,1] (PRD §10.6). */
export interface Components {
  rs: number
  high: number
  trend: number
  vol: number
  accel: number
}

/** 6 raw evidence numbers shown on the collapsed card (PRD §9.1.3). */
export interface Evidence {
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  from_high: number | null
  weeks_since_breakout: number | null
  vol_mult: number | null
}

export interface Valuation {
  pe: number | null
  ps: number | null
  evs: number | null
  ev_ebitda: number | null
  growth: number | null
  rule40: number | null
  as_of_period_end: string | null
  as_of_filed: string | null
  as_of_age_days: number | null
  freshness: Freshness | null
}

/** ~90d OHLCV mini-chart + engine MAs + 52w-high level. */
export interface ChartSeries {
  dates: string[]
  open: (number | null)[]
  high: (number | null)[]
  low: (number | null)[]
  close: (number | null)[]
  adj_close: (number | null)[]
  volume: (number | null)[]
  ma50: (number | null)[]
  ma150: (number | null)[]
  ma200: (number | null)[]
  high_52w: number | null
}

export interface ThemeTag {
  theme: string
  exposure: number | null
}

export interface Stock {
  ticker: string
  name: string | null
  sector: string | null
  mktcap: number | null
  themes: ThemeTag[]
  composite: number | null
  composite_prev: number | null
  rank: number | null
  components: Components
  evidence: Evidence
  valuation: Valuation | null
  chart: ChartSeries
}

export interface BoardData {
  schema_version: number
  as_of_date: string
  knob_default_k: number
  weights_default: Components
  composite_recon_max_drift: number
  count: number
  valuation_coverage: number
  stocks: Stock[]
}

/** The five lenses, in the contract's fixed order (PRD §9.0). */
export type SurfaceId = 'ocean' | 'discovery' | 'rotation' | 'valuation' | 'stock'

/** Global scope filter (PRD §9.1.2, C8/C10). Single source, sticky across tabs. */
export type Scope =
  | { kind: 'all'; key: null }
  | { kind: 'sector'; key: string }
  | { kind: 'theme'; key: string }
  | { kind: 'pinned'; key: null }

// --- Ocean (M2.1 export/ocean.py -> public/data/ocean.json) ---
// Weekly RS×Valuation snapshots for the canvas scatter (PRD §9.2). A stock's
// pts[] is aligned to weeks[] (oldest→newest); a null pt = no renderable position
// that week (stale vintage / cold history — never fabricated). See export/ocean.py.

/** One week's position for a stock. rs/val ∈ [0,100]; val low=cheap (y bottom). */
export interface OceanPt {
  rs: number
  val: number
  ps: number | null
}

export interface OceanStock {
  ticker: string
  sector: string | null
  mktcap: number | null
  themes: ThemeTag[]
  pts: (OceanPt | null)[]
}

export interface OceanData {
  schema_version: number
  as_of_date: string
  metric: string
  fresh_days: number
  n_weeks: number
  weeks: string[]
  count: number
  fresh_cohort_latest: number
  stale_excluded_latest: number
  stocks: OceanStock[]
}

// --- Rotation (M3.3 export/rotation.py -> public/data/rotation.json) ---
// Weekly RS-Ratio series per bucket (sector M3 / theme M4) + an enriched league
// snapshot (PRD §9.4). rs_ratio[] aligns to weeks[] (oldest→newest; null = no point
// that week). The league member aggregates trace to derived_daily/valuation_daily (C9);
// members[] is the ticker list only — the client filters board.json by scope=sector for
// the evidence cards (DRY). RS-Momentum 归一量 is cut (PRD §16); momentum = slope_4w.

export type RotationState = 'LEADING' | 'WEAKENING' | 'IMPROVING' | 'LAGGING'

export interface RotationBucket {
  bucket_type: string
  bucket: string
  etf: string | null
  rs_ratio: (number | null)[]
  level: number | null
  slope_4w: number | null
  state: RotationState
  breadth_ma50: number | null
  breadth_ma200: number | null
  at_high: number | null
  member_count: number | null
  composite_median: number | null
  agg_evs: number | null
  rel_ret_1m: number | null
  rel_ret_3m: number | null
  rel_ret_6m: number | null
  members: string[]
}

export interface RotationData {
  schema_version: number
  as_of_date: string
  benchmark: string
  bucket_type: string
  params: { basis: string; n1_ema: number; n2_window: number; k: number }
  n_weeks: number
  weeks: string[]
  count: number
  buckets: RotationBucket[]
}

// --- Manifest (D.4 export/manifest.py -> public/data/manifest.json) ---
// Tiny freshness descriptor so the header as_of badge loads without a full surface JSON
// (data age + 陈旧色). as_of_date is the latest across surfaces; null = nothing exported.
export interface ManifestData {
  schema_version: number
  as_of_date: string | null
  generated_at: string
  surfaces: {
    board: number | null
    ocean: number | null
    rotation: number | null
    'rotation.theme': number | null
    valuation: number | null
    stock: number | null
  }
}

// --- Valuation screener (M5.1 export/valuation_parquet.py -> public/data/valuation.parquet) ---
// The FULL-universe latest valuation cross-section (wide explore, PRD §9.5), queried in the
// browser by duckdb-wasm (M5.2). One row per universe ticker; same valuation_daily as
// board.json (C9). `themes` is comma-joined point-in-time theme keys ('' if none) so the
// screener can honor scope='theme' from this one file.
export interface ValuationRow {
  ticker: string
  name: string | null
  sector: string | null
  mktcap: number | null
  pe: number | null
  ps: number | null
  evs: number | null
  ev_ebitda: number | null
  peg: number | null
  growth: number | null
  margin: number | null
  rule40: number | null
  as_of_period_end: string | null
  as_of_filed: string | null
  as_of_age_days: number | null
  freshness: Freshness | null
  themes: string
}

/** valuation.sample.json fixture shape (SSR tests inject rows without duckdb-wasm). */
export interface ValuationData {
  schema_version: number
  as_of_date: string
  count: number
  rows: ValuationRow[]
}

// --- Stock per-name bundle (M5.3 export/stock_bundle.py -> public/data/stock/<TICKER>.json) ---
// The series behind the M5.4 time-aligned price↔fundamentals stack (PRD §9.6). Self-contained
// per name (header + card + components too), lazily fetched. Same daily_bars/valuation_daily/
// fundamentals_q as every surface (C9). `price` reuses ChartSeries (the ~2y window here, vs
// board's 90d).
export interface RevenueQuarter {
  period_end: string | null
  revenue_ttm: number | null
  yoy: number | null
}

export interface PsPoint {
  date: string | null
  ps: number | null
}

export interface StockBundle {
  schema_version: number
  as_of_date: string | null
  meta: {
    ticker: string
    name: string | null
    sector: string | null
    mktcap: number | null
    composite: number | null
    themes: ThemeTag[]
  }
  components: Components | null
  valuation: {
    pe: number | null
    ps: number | null
    evs: number | null
    ev_ebitda: number | null
    peg: number | null
    growth: number | null
    margin: number | null
    rule40: number | null
    as_of_period_end: string | null
    as_of_filed: string | null
  } | null
  price: ChartSeries
  revenue_q: RevenueQuarter[]
  ps_series: PsPoint[]
}

/** stock/index.json — ticker list for the per-name selector. */
export interface StockIndex {
  schema_version: number
  as_of_date: string | null
  count: number
  tickers: string[]
}
