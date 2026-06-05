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
