-- TickerTide DuckDB schema — every DuckDB table, created idempotently on each
-- connect (compute/db.py). Each table notes the milestone/module that writes it.
-- Full schema spec + field dictionary: docs/PRD.md §12, 附录 B.
-- Safe to re-run: CREATE TABLE IF NOT EXISTS only adds what's missing.

CREATE TABLE IF NOT EXISTS universe (
  ticker      VARCHAR PRIMARY KEY,
  name        VARCHAR,
  exchange    VARCHAR,           -- NASDAQ | NYSE | AMEX (US-listed; ADRs allowed)
  sector      VARCHAR,
  industry    VARCHAR,
  country     VARCHAR,
  mktcap      DOUBLE,
  is_active   BOOLEAN DEFAULT TRUE,
  first_seen  DATE,
  last_seen   DATE
);

CREATE TABLE IF NOT EXISTS daily_bars (
  ticker     VARCHAR,
  date       DATE,
  open       DOUBLE,
  high       DOUBLE,
  low        DOUBLE,
  close      DOUBLE,
  adj_close  DOUBLE,
  volume     BIGINT,
  PRIMARY KEY (ticker, date)
);

-- splits: forward/reverse stock-split events per ticker (M0.4 valuation split-alignment).
-- WHY this table exists (PRD §10.5 split-alignment, fills a口径 gap): the price series
-- (daily_bars, yfinance) is split-adjusted to the latest session the MOMENT a split takes
-- effect on the exchange, but the per-share fundamentals (fundamentals_q, EDGAR) only
-- re-state to the post-split basis at the NEXT formal filing — which can be months later
-- (10-Q/10-K cadence). In that window `shares × adj_close ÷ revenue` mixes a POST-split price
-- with a PRE-split share count, collapsing P/S, P/E, EV/S, EV/EBITDA, PEG by the split ratio
-- (a 10-for-1 split makes them ~10× too small — see KLAC, ex-date 2026-06-11). compute/
-- valuation.py lifts eps/shares to the price basis using the cumulative ratio of splits with
-- ex_date AFTER a filing's effective_eod_date and on/before the ticker's latest bar. No matching
-- rows → factor 1.0 → byte-identical to the pre-split behaviour (revenue/ebitda/debt/cash are
-- absolute amounts and stay split-invariant). ratio = shares-out multiplier on/after ex_date:
-- forward 10-for-1 → 10.0; reverse 1-for-5 → 0.2. Source: yfinance .splits (M0 backbone).
CREATE TABLE IF NOT EXISTS splits (
  ticker   VARCHAR,
  ex_date  DATE,      -- split effective (ex-)date: prices on/after this trade split-adjusted
  ratio    DOUBLE,    -- shares-out multiplier (forward >1, reverse <1); never 0/negative
  PRIMARY KEY (ticker, ex_date)
);

CREATE TABLE IF NOT EXISTS spx_daily (
  date   DATE PRIMARY KEY,
  close  DOUBLE
);

-- bucket_bars: sector ETF (M3) / theme index (M4) daily closes — the RS-Ratio
-- numerator (vs spx_daily benchmark; compute/rotation.py resamples weekly, M3.2).
-- DELIBERATELY ISOLATED from universe daily_bars: ETF/index prices must NEVER enter
-- the universe cross-section (derived_daily.rs_pct / rank_in_universe), or per-date
-- percentiles drift (PRD §16, ROADMAP M3 "ETF 不污染横截面"). compute/run.py reads
-- daily_bars only; rotation reads bucket_bars only. `bucket` is the GICS sector name
-- (== universe.sector) so league aggregation joins by name; the ETF ticker lives in
-- ingest/sector_etf_map.txt. `close` is total-return basis (adj_close), like spx_daily.
CREATE TABLE IF NOT EXISTS bucket_bars (
  bucket_type  VARCHAR,   -- 'sector' (11 SPDR ETF, M3) | 'theme' (M4 index)
  bucket       VARCHAR,   -- GICS sector name (== universe.sector) | theme name
  date         DATE,
  close        DOUBLE,    -- adj close (total-return basis; matches spx_daily)
  PRIMARY KEY (bucket_type, bucket, date)
);

-- bucket_rrg: weekly RS-Ratio series per bucket (sector M3 / theme M4) — the Rotation
-- multi-line chart source (compute/rotation.py, M3.2). rs = 100*P_bucket/P_SPX (raw
-- price-relative line, kept for audit/transparency); rs_ratio = JdK RS-Ratio, a z-score
-- of EMA(rs) recentered to 100 (PRD §10.4). The RS-Momentum 归一量 is CUT (PRD §16):
-- momentum = the SLOPE of rs_ratio, derived on the fly (export/web), NOT stored here.
-- z-score basis is temporal (vs the bucket's own history) for the fixed 11 GICS sectors;
-- themes (M4, changing membership) will use point-in-time. Weekly (Friday close).
CREATE TABLE IF NOT EXISTS bucket_rrg (
  bucket_type  VARCHAR,   -- 'sector' (M3) | 'theme' (M4)
  bucket       VARCHAR,   -- GICS sector name | theme name
  date         DATE,      -- weekly (Friday)
  rs           DOUBLE,    -- 100 * P_bucket / P_SPX (raw price-relative line)
  rs_ratio     DOUBLE,    -- 100 + k·(M − SMA(M,n2))/σ(M,n2), M = EMA(rs, n1)
  PRIMARY KEY (bucket_type, bucket, date)
);

-- derived_daily: per-stock signals + the steady-riser core screen (PRD §10.8, 2026-07-02
-- spine pivot II). One row per (ticker,date) shared by every lens (C9). rise_* is the
-- CORE: chart-verifiable metrics + the cross-sectional percentile + the candidate flag
-- (single source of truth — export/web never re-derive it) + the on-list streak.
-- composite/c_* are calc-layer residue only (§10.6, never user-visible); brk_* is the
-- RETIRED base→breakout engine (§10.9) kept only until export/ switches off it.
CREATE TABLE IF NOT EXISTS derived_daily (
  ticker            VARCHAR,
  date              DATE,
  ret_63            DOUBLE,
  ret_126           DOUBLE,
  rs_raw            DOUBLE,    -- (ret_63 - spx_ret_63) + (ret_126 - spx_ret_126)
  rs_pct            DOUBLE,    -- cross-sectional percentile of rs_raw, per date, 0-100
  rs_accel          DOUBLE,    -- rs_pct[t] - rs_pct[t-21]
  high_prox         DOUBLE,    -- adj_close / rolling_max(adj_close, 252)
  ma50              DOUBLE,
  ma150             DOUBLE,
  ma200             DOUBLE,
  trend_quality     DOUBLE,    -- KER (Kaufman efficiency ratio), [0,1]
  vol_ratio         DOUBLE,    -- SMA(vol,50) / SMA(vol,200)
  ud_vol_ratio      DOUBLE,    -- up-volume / down-volume over last 50d
  ewmac_fast        DOUBLE,    -- vol-normalized EWMAC (16/64)
  ewmac_slow        DOUBLE,    -- vol-normalized EWMAC (32/128)
  c_rs              DOUBLE,    -- component [0,1]: rs_pct/100
  c_high            DOUBLE,    -- component [0,1]: high_prox
  c_trend           DOUBLE,    -- component [0,1]: trend_quality
  c_vol             DOUBLE,    -- component [0,1]: volume score
  c_accel           DOUBLE,    -- component [0,1]: rs_accel score
  composite         DOUBLE,    -- 100 * Σ wᵢ·cᵢ at default k (calc-layer only, §10.6 — NOT user-visible)
  rank_in_universe  INTEGER,   -- dense rank by composite per date (1 = strongest)
  -- base→breakout (RETIRED, PRD §10.9; 2026-07-02 spine pivot II). Kept only until export/
  -- switches to rise_* — then these columns are removed (fresh DBs each nightly).
  brk_tau_date      VARCHAR,   -- estimated changepoint date (2-seg piecewise-linear kink on log price)
  brk_base_slope    DOUBLE,    -- s1/σ: base-segment slope (≈0 = flat long base)
  brk_brk_slope     DOUBLE,    -- s2/σ: breakout-segment slope (steep)
  brk_drift_step    DOUBLE,    -- (s2-s1)/σ: slope jump
  brk_fit_gain      DOUBLE,    -- 1-SSE2/SSE1: kink salience
  brk_clearance     DOUBLE,    -- close/max(base-high) - 1
  brk_vcp           DOUBLE,    -- bar-level VCP: ATR(breakout)/ATR(base)
  brk_vsurge        DOUBLE,    -- volume surge: mean(vol breakout)/mean(vol base)
  brk_strength      DOUBLE,    -- recall-first combined strength
  brk_strength_pct  DOUBLE,    -- cross-sectional percentile of brk_strength
  -- steady-riser (CORE screen, PRD §10.8; 2026-07-02 spine pivot II). Chart-verifiable
  -- by construction: every value can be counted off the candles. Gate/candidate/streak
  -- are computed once in compute/run.py (C9 single source of truth).
  rise_net5         DOUBLE,    -- close/close[-5] - 1 (short reference window)
  rise_net10        DOUBLE,    -- close/close[-10] - 1 (PRIMARY: "the last 1-2 weeks"; sort key)
  rise_net20        DOUBLE,    -- close/close[-20] - 1 (long reference window)
  rise_up10         DOUBLE,    -- fraction of up days in the last 10 (gate: >= 0.6)
  rise_ddw10        DOUBLE,    -- max drawdown inside the 10d window from its running peak (<=0)
  rise_ker10        DOUBLE,    -- path efficiency |Σδ|/Σ|δ| in [0,1] (evidence column, never a gate)
  rise_net10_pct    DOUBLE,    -- cross-sectional percentile of rise_net10, per date, 0-100 (Ocean y)
  rise_candidate    INTEGER,   -- 1 = gate AND net10 top-N (single truth; export/web never re-derive)
  rise_streak_days  INTEGER,   -- consecutive days candidate=1 (islands; display column, not a filter)
  PRIMARY KEY (ticker, date)
);

-- fundamentals_q: trailing-4Q financials per reporting period (M0.2). Spec: PRD §12, §10.5.
-- FORMAL-FILING POINT-IN-TIME (PRD §10.5): the denominator is trailing-4Q from official
-- SEC filings ONLY (no preliminary release / 8-K earnings / press release / estimate).
-- Three date/provenance fields disambiguate "when":
--   period_end          — fiscal period the data BELONGS to (business period; NEVER an
--                         availability date — must not be used to align valuation).
--   filed_date          — the official SEC filing date (earliest filing per period = the
--                         original report, anti-restatement / anti-lookahead).
--   effective_eod_date  — the EOD snapshot from which this filing may enter valuation_daily
--                         (the ASOF availability key). v1: effective_eod_date = filed_date;
--                         v2 (future, EDGAR accepted-timestamp) may push it to next_trading_day
--                         when accepted after the close.
-- revenue/eps/ebitda are trailing-4Q (4 single quarters; Q4 derived from annual − sum(Q1..Q3)
-- when needed; annual-only filers fall back to yearly points). Balance-sheet items are instant.
CREATE TABLE IF NOT EXISTS fundamentals_q (
  ticker       VARCHAR,
  period_end   DATE,
  filed_date   DATE,
  revenue_ttm  DOUBLE,
  shares       DOUBLE,
  total_debt   DOUBLE,
  cash         DOUBLE,
  ebitda_ttm   DOUBLE,
  eps_ttm      DOUBLE,
  effective_eod_date  DATE,     -- ASOF availability key for valuation_daily (v1 == filed_date)
  source_type         VARCHAR,  -- provenance; 'formal_filing' is the ONLY value in v1
  source_form         VARCHAR,  -- '10-Q'|'10-K'|'20-F'|'40-F'|'unknown' (v1: 'unknown')
  PRIMARY KEY (ticker, period_end)
);
-- Idempotent migration for DBs created before these columns existed (CREATE IF NOT EXISTS
-- above is a no-op on an existing table, so back-fill the columns here).
ALTER TABLE fundamentals_q ADD COLUMN IF NOT EXISTS effective_eod_date DATE;
ALTER TABLE fundamentals_q ADD COLUMN IF NOT EXISTS source_type VARCHAR;
ALTER TABLE fundamentals_q ADD COLUMN IF NOT EXISTS source_form VARCHAR;

-- segment_revenue: theme revenue anchoring (PRD §8.3, §12). Table created in M0.2
-- but NOT populated here — companyfacts does not expose XBRL segment dimensions;
-- segment extraction is M4 (10-K/10-Q segment footnote + LLM, human-in-loop).
CREATE TABLE IF NOT EXISTS segment_revenue (
  ticker      VARCHAR,
  period_end  DATE,
  segment     VARCHAR,
  revenue     DOUBLE,
  PRIMARY KEY (ticker, period_end, segment)
);

-- theme_membership: many-to-many ticker<->concept-theme with continuous exposure,
-- point-in-time (M4.1). Theme keys + colour/cap defined in themes/themes.yaml
-- (AI/ROBO/SPACE/OPTIC/SEMI/NUKE/CYBR/CLOUD). NVDA in both AI and SEMI is a feature,
-- never forced MECE (PRD §8.2). Feeds the theme index (compute/theme_index.py, M4.2,
-- bucket_bars[bucket_type='theme']) and Stock/Discovery chips (export/board.py, M4.4).
--
-- POINT-IN-TIME (C3, PRD §7) — the hard invariant:
--   as_of_date carries history; the SAME (ticker,theme) gets a NEW row each time the
--   membership is restated, NEVER an in-place edit. Member@t = per (ticker,theme) the
--   row with the latest as_of_date <= t, KEPT only if its exposure > 0 (an exposure=0
--   row at date X drops the member as-of X without rewriting the pre-X history). Editing
--   a later as_of must never move an earlier snapshot, or theme RS-Ratio lines / Ocean
--   trails become fiction. Canonical query lives once in compute/db.theme_membership_asof.
--
-- exposure  : continuous revenue-share weight in [0,1] (NOT binary; PRD §8.3). The theme
--             index caps it per themes.yaml so one mega-cap can't dominate (C4) — capping
--             is an index-build concern (M4.2), exposure itself stays the raw share here.
-- source    : 'seed' (themes/seed.py from universe_seed groups) | 'llm' | 'manual'.
-- approved_by: human-in-loop approver, REQUIRED (C6 — LLM is candidate generator, never
--             the authority); 'seed' marks bootstrap rows not yet human-reviewed.
CREATE TABLE IF NOT EXISTS theme_membership (
  ticker       VARCHAR,
  theme        VARCHAR,   -- theme key (see themes/themes.yaml)
  exposure     DOUBLE,    -- continuous revenue-share weight, [0,1]
  as_of_date   DATE,      -- point-in-time: reflects only info disclosed as-of this date
  source       VARCHAR,   -- 'seed' | 'llm' | 'manual'
  approved_by  VARCHAR,   -- human-in-loop approver (C6); 'seed' for bootstrap rows
  PRIMARY KEY (ticker, theme, as_of_date)
);

-- valuation_daily: daily multiples = price/EV ÷ trailing-4Q financials (M0.4).
-- FORMAL-FILING PIT (PRD §10.5): ASOF-aligned on as_of_effective_eod (v1 == as_of_filed),
-- NOT on period_end — a quarter ending Mar 31 but filed in Apr enters P/S in Apr, not Mar.
-- Numerator is daily; the denominator steps at each filing's effective date. E<=0 -> n.m.
-- (pe NULL, fall back to ps). The three as_of_* dates mirror fundamentals_q:
--   as_of_period_end     — fiscal period of the denominator; drives common-vintage freshness
--                          (age = date − period_end), NEVER the availability date.
--   as_of_filed          — official filing date of that denominator.
--   as_of_effective_eod  — the date that denominator entered this series (the ASOF key used).
-- valuation_basis tags the口径 ('formal_filing_pit') so a future market_reaction_pit can't be
-- silently confused with it. as_of_period_end feeds common-vintage ranking (PRD §9.5, §10.5).
CREATE TABLE IF NOT EXISTS valuation_daily (
  ticker            VARCHAR,
  date              DATE,
  pe                DOUBLE,
  ps                DOUBLE,
  evs               DOUBLE,
  ev_ebitda         DOUBLE,
  peg               DOUBLE,
  growth            DOUBLE,
  margin            DOUBLE,
  rule40            DOUBLE,
  as_of_period_end  DATE,
  as_of_filed       DATE,
  as_of_effective_eod  DATE,     -- ASOF availability key actually joined on (v1 == as_of_filed)
  valuation_basis      VARCHAR,  -- 'formal_filing_pit' (the only口径 in v1)
  PRIMARY KEY (ticker, date)
);
-- Idempotent migration for pre-existing DBs (see fundamentals_q note above).
ALTER TABLE valuation_daily ADD COLUMN IF NOT EXISTS as_of_effective_eod DATE;
ALTER TABLE valuation_daily ADD COLUMN IF NOT EXISTS valuation_basis VARCHAR;
