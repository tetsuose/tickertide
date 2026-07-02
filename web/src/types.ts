// TypeScript types mirroring export/board.py's board.json (M1.1 contract).
// composite is read from the engine's exported value at the fixed weighting (k=0.5);
// the client never recomputes the engine (C9) — the early⟷reliable knob is gone (PRD
// §16), composite.ts only carries the fixed WEIGHTS for the per-component %. Numeric
// fields are nullable wherever the engine can emit no value (insufficient history,
// E<=0 valuation, missing fundamentals).

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

/** The CORE screen (steady-riser, PRD §10.8; 2026-07-02 spine pivot II — replaces
 * base→breakout). Every number is chart-verifiable over the W=10 window: netN = N-day net
 * return, up10 = up-day fraction, ddw10 = max in-window drawdown, ker10 = path efficiency,
 * net10_pct = daily cross-sectional percentile of net10 (drives Ocean's y axis).
 * `candidate` = the gate (up10>=0.6 AND net10>0) + net10 top-N — computed ONCE in the
 * compute layer (derived_daily.rise_candidate, C9); the client NEVER re-derives it (not
 * even a pct>=90 shortcut — the #92–#94 rounding-boundary lesson). `streak_days` =
 * consecutive days on the board. Smoothness (ker/ddw) is evidence only, never a filter. */
export interface RiserBlock {
  net5: number | null
  net10: number | null
  net20: number | null
  up10: number | null
  ddw10: number | null
  ker10: number | null
  net10_pct: number | null
  candidate: boolean
  streak_days: number | null
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
  /** Formal-filing PIT (PRD §10.5): the EOD this filing entered valuation (v1 == as_of_filed),
   *  the口径 tag, and filing latency (filed − period_end). Optional: pre-PIT data omits them. */
  as_of_effective_eod?: string | null
  valuation_basis?: string | null
  disclosure_lag_days?: number | null
  as_of_age_days: number | null
  freshness: Freshness | null
}

/** OHLCV chart + engine MAs + 52w-high level. Shared shape: Discovery's ~90d mini-chart
 *  (schema v2: now lazy per-stock, see BoardChartDetail) and the Stock bundle's ~2y price. */
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
  /** Core screen (steady-riser, PRD §10.8). Optional: partial exports may omit it. */
  riser?: RiserBlock
  valuation: Valuation | null
  /** schema v2 payload split: the bulk board.json no longer ships the chart (~96% of the raw
   *  payload, yet only ~20 cards show at once) — it loads lazily per card via loadBoardChart ->
   *  board/<TICKER>.json (BoardChartDetail). Kept OPTIONAL only as a transitional fallback: if a
   *  stale v1 data artifact is served (a deploy reuses the last nightly's data), the card uses
   *  this inline chart instead of fetching a 404. The v2 export never emits it. See EvidenceCard. */
  chart?: ChartSeries
}

export interface BoardData {
  schema_version: number // 4 = steady-riser block (payload split retained: bulk + board/<T>.json)
  as_of_date: string
  composite_recon_max_drift: number
  count: number
  valuation_coverage: number
  /** steady-riser rollups (PRD §10.8) — optional for partial exports. */
  riser_coverage?: number
  riser_candidates?: number
  riser_top_n?: number
  stocks: Stock[]
}

/** Lazy per-stock mini-chart (export/board.py -> public/data/board/<TICKER>.json, schema v2).
 *  Discovery's bulk board.json carries no chart; each EvidenceCard fetches its own chart on
 *  render (loadBoardChart) so a session only downloads charts for the ~20 names actually shown.
 *  Same daily_bars the bulk's evidence numbers derive from (C9) — the split moves WHERE the
 *  chart lives, not WHAT it is. */
export interface BoardChartDetail {
  schema_version: number
  ticker: string
  chart: ChartSeries
}

/** The five lenses, in the contract's fixed order (PRD §9.0). */
export type SurfaceId = 'ocean' | 'risers' | 'rotation' | 'valuation' | 'stock'

/** Global scope filter (PRD §9.1.2, C8/C10). Single source, sticky across tabs. */
export type Scope =
  | { kind: 'all'; key: null }
  | { kind: 'sector'; key: string }
  | { kind: 'theme'; key: string }
  | { kind: 'pinned'; key: null }

// --- Ocean (export/ocean.py -> public/data/ocean.json, schema v5) ---
// steady-riser × Valuation daily SEA-LEVEL map (PRD §9.2, 2026-07-02 spine pivot II):
// y = rise_net10_pct (0-100, sea level fixed at 90 — a VISUAL reference line only), x = raw
// trailing P/S TTM on a LOG axis (NOT a valuation percentile, NOT a composite score).
//
// PAYLOAD SPLIT (scales to M6): the bulk ocean.json carries only the THREE fields every
// animation frame needs, in a COLUMNAR layout — per stock, parallel arrays ps/rise_pct/cand
// aligned to dates[] (oldest→newest). A null in ps/rise_pct at index i = no renderable
// position that day (the play tween fades it in/out; never fabricated). The tooltip-only
// fields live in per-stock ocean/<TICKER>.json (OceanDetail), fetched lazily on hover.

/** A single day's DRAW snapshot reconstructed from the columnar bulk (see ocean-draw.drawPtAt).
 *  rise_pct ∈ [0,100] (y), ps > 0 (x, log). candidate = the Risers gate+top-N flag, computed
 *  ONCE by compute (derived_daily.rise_candidate) — NOT derivable from y (cand ≠ y>=90; the
 *  gate has an up10 condition + top-N cut). The play tween lerps x/y between adjacent real
 *  snapshots — it never synthesizes candidate. */
export interface OceanDrawPt {
  ps: number
  rise_pct: number
  candidate: boolean
}

export interface OceanStock {
  ticker: string
  sector: string | null
  mktcap: number | null
  themes: ThemeTag[]
  // columnar draw fields, each aligned to OceanData.dates (oldest→newest). null at index i =
  // no renderable position that day. cand[i] ∈ {0,1} (1 = steady-riser candidate, read-only
  // from compute — never re-derived); 0 on a null day.
  ps: (number | null)[]
  rise_pct: (number | null)[]
  cand: (0 | 1)[]
}

/** Lazy per-stock hover detail (export/ocean.py -> public/data/ocean/<TICKER>.json, schema v5).
 *  The tooltip-only fields, columnar + index-aligned to OceanData.dates (so detail.evs[i]
 *  is the value at dates[i]); null exactly where the bulk has no position that day. Fetched on
 *  hover so the bulk stays tiny (payload reduction). `n` must equal dates.length (alignment guard). */
export interface OceanDetail {
  schema_version: number
  ticker: string
  n: number
  /** Formal-filing PIT (PRD §10.5):口径 tag (scalar) + the per-day fiscal/availability dates,
   *  index-aligned to OceanData.dates so the tooltip stays honest while the slider scrubs.
   *  Optional: pre-PIT detail omits them. */
  valuation_basis?: string
  net5: (number | null)[]
  net10: (number | null)[]
  net20: (number | null)[]
  up10: (number | null)[]
  ddw10: (number | null)[]
  streak_days: (number | null)[]
  evs: (number | null)[]
  pe: (number | null)[]
  ev_ebitda: (number | null)[]
  freshness: (Freshness | null)[]
  as_of_period_end?: (string | null)[]
  as_of_effective_eod?: (string | null)[]
}

/** Fixed axis descriptor — the export decides the axes; the client never re-derives them. */
export interface OceanAxis {
  x_metric: string   // 'ps' (raw trailing P/S TTM)
  x_scale: string    // 'log'
  y_metric: string   // 'rise_net10_pct'
  sea_level: number  // 90 (visual reference line only — candidate is NOT y>=90)
}

export interface OceanData {
  schema_version: number
  as_of_date: string
  axis: OceanAxis
  dates: string[]
  /** [min, max] of all valid P/S in the window, for the log-scale x domain. */
  x_domain: [number, number]
  count: number
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
  /** steady-riser aggregates (2026-07-02 pivot II): both count the STORED
   *  derived_daily.rise_candidate flag (read-only, C9) — the league aggregates the core
   *  screen; composite_median is gone (composite is not a user-visible concept). */
  igniting: number | null
  candidates: number | null
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
  /** Formal-filing PIT (PRD §10.5); optional for pre-PIT parquet. */
  as_of_effective_eod?: string | null
  valuation_basis?: string | null
  disclosure_lag_days?: number | null
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
  /** Formal-filing PIT (PRD §10.5): the bar sits at period_end (business period), but its
   *  data only enters P/S from effective_eod_date (v1 == filed_date). disclosure_lag_days =
   *  filed − period_end. Optional: pre-PIT bundles omit them (bar then assumed known at period_end). */
  filed_date?: string | null
  effective_eod_date?: string | null
  disclosure_lag_days?: number | null
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
  /** Core screen (steady-riser, PRD §10.8) — verbatim from derived_daily, same block
   * board.json ships per Risers card (C9). Drives Stock's riser 诊断. Optional/null: names
   * the screen couldn't score omit it. steady-riser has no tunable parameter (PRD §16). */
  riser?: RiserBlock | null
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
    /** Formal-filing PIT (PRD §10.5); optional for pre-PIT bundles. */
    as_of_effective_eod?: string | null
    valuation_basis?: string | null
    disclosure_lag_days?: number | null
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
