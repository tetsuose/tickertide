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
