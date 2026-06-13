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

-- derived_daily: per-stock signals + composite (M0.3) + ignition (M7.1). Spec: PRD
-- §12, math: §10.6 (composite) / §10.8 (ignition). Stores the 5 composite COMPONENTS
-- (c_*) in [0,1] so the client can recompute composite at any early<->reliable knob k
-- (`composite` is the default-k snapshot). The two engines are PARALLEL and share this
-- one per-stock row (C9): composite confirms (long windows, "already a leader"),
-- ignition discovers (short windows, "just starting"); both lenses read this table so
-- they never drift. The ignition columns (ig_*/ignition/ign_pct/ign_persist_days, §10.8)
-- carry the 5 short-window components + the cross-sectional score + top-decile persistence.
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
  composite         DOUBLE,    -- 100 * Σ wᵢ·cᵢ at default k
  rank_in_universe  INTEGER,   -- dense rank by composite per date (1 = strongest)
  -- ignition engine (early discovery, PRD §10.8) — the 5 raw self-relative short-window
  -- components, each then cross-sectionally percentile-ranked to [0,1] and averaged:
  ig_accel          DOUBLE,    -- momentum acceleration: ret_10/10 - ret_50/50 (slope steepening)
  ig_expand         DOUBLE,    -- squeeze->expansion: mean(|Δp|,10)/mean(|Δp|,60) (range opening)
  ig_vsurge         DOUBLE,    -- volume surge: mean(vol,5)/mean(vol,60) (vs own recent base)
  ig_breakout       DOUBLE,    -- breakout/reclaim: clamp(close/max(close,60),0,1)·1[close>MA50]
  ig_rsturn         DOUBLE,    -- RS-line turn: slope10(P/P_spx) - slope30(P/P_spx)/3 (inflection)
  ignition          DOUBLE,    -- 100·mean(cross-sectional percentile-rank of the 5 components), [0,100]
  ign_pct           DOUBLE,    -- cross-sectional percentile of ignition, per date, 0-100
  ign_persist_days  INTEGER,   -- consecutive days (incl. today) with ign_pct>=90 (top-decile persistence)
  PRIMARY KEY (ticker, date)
);

-- fundamentals_q: trailing-4Q financials per reporting period (M0.2). Spec: PRD §12.
-- point-in-time: filed_date is the as-of (anti-lookahead). revenue/eps/ebitda are
-- trailing-4Q (4 single quarters; Q4 derived from annual − sum(Q1..Q3) when needed;
-- annual-only filers fall back to yearly points). Balance-sheet items are instant.
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
  PRIMARY KEY (ticker, period_end)
);

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
-- ASOF-aligned on filed_date (point-in-time, anti-lookahead); numerator is daily,
-- denominator steps at each filing. E<=0 -> n.m. (pe NULL, fall back to ps).
-- as_of_period_end exposes vintage freshness for common-vintage ranking (PRD §9.5, §10.5).
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
  PRIMARY KEY (ticker, date)
);
