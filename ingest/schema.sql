-- TickerTide DuckDB schema — M0 (price + universe layer).
-- Full schema spec: docs/PRD.md §12. This file covers only the tables M0.1 writes.
-- Idempotent: safe to re-run on every ingest.

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

-- derived_daily: per-stock signals + composite (M0.3). Spec: PRD §12, math: §10.
-- Stores the 5 composite COMPONENTS (c_*) in [0,1] so the client can recompute
-- composite at any early<->reliable knob k; `composite` is the default-k snapshot.
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
  PRIMARY KEY (ticker, date)
);
