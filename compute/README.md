# compute/ — DuckDB 计算引擎

> 模块职责：从 `ingest/` 原始表派生**单一 per-stock 信号**，五个 surface 共用。**Pre-M0（planned）。**

## 职责

DuckDB(列存 OLAP，嵌入式、single-writer、offline batch) 计算派生表。**所有 surface 的数字必须从同一份 per-stock 数据派生**（数据一致性硬约束，PRD §7 item 9）。

## 计算内容

- **趋势/return**：vol-normalized EWMAC（`(EMA_fast−EMA_slow)/σ`，多 horizon 混合），并保留 Minervini SMA Trend Template。
- **RS percentile**：`rs_raw=(ret_63−SPX_63)+(ret_126−SPX_126)`，每日 cross-sectional percentile。
- **trend quality**：KER 或 log-price OLS slope t-stat。
- **composite**：`score=100·Σwᵢ·componentᵢ`，components∈[0,1]；`early⟷reliable` 旋钮 `k` 重配权（两端各归一 Σ=1）。
- **估值（ASOF）**：`valuation_daily` 由 `daily_bars ASOF JOIN fundamentals_q ON ticker AND date>=period_end`；price ÷ trailing-4Q 日频；`E≤0→n.m.`；百分位 **common-vintage**。
- **Rotation**：sector/theme 的 RS-Ratio 序列（透明 reconstruction，非复刻 StockCharts）。

## 输入 → 输出

- 输入：`ingest/` 落地的原始表。
- 输出：`derived_daily`、`valuation_daily`、`bucket_rrg`（schema 见 PRD §12）。

## 规格来源

PRD §4（数学规格）、§12（schema）、BUILD-PLAN §4。诚实定调：买 robustness/stability，不买 alpha；不回测优化权重。

## 未来文件

`run.py`（入口，`make compute`）、`composite.py`、`rs.py`、`trend.py`、`valuation.py`、`rotation.py`。

## Milestone

M0（composite + valuation，~500 只）→ M3（bucket RS-Ratio）→ M4（theme 维度）。
