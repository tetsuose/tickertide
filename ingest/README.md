# ingest/ — 数据拉取

> 模块职责：把外部数据源拉成本地原始表，喂给 `compute/`。**Pre-M0（planned）。**

## 职责

US-only 过滤下，每日(EOD)拉取四类源，落地到 DuckDB 原始表（`data/`，gitignored）。

| source | 用途 | 备注 |
|---|---|---|
| **Stooq** | bulk EOD OHLCV（价格主干） | CSV 批量，无 per-symbol 限速；数千只的最佳免费源；校验覆盖、补缺口 |
| **Nasdaq screener** (`api.nasdaq.com/api/screener/stocks`) | universe + market cap + sector/industry + trailing P/E + last sale | 一次拿全美股清单；半官方 |
| **SEC EDGAR** (`data.sec.gov`) | revenue/shares/debt/cash/segment → 估值与主题锚定 | 官方权威；需 descriptive `User-Agent`，~10 req/s |
| **(opt) Tiingo / yfinance** | 干净补缺 / 脆弱兜底 | Tiingo 便宜付费；yfinance 仅 fallback（非官方、会断） |

## 输入 → 输出

- 输入：外部 HTTP API / CSV。US-only（Nasdaq 限 NYSE/Nasdaq/AMEX；EDGAR 天然 US filers）。
- 输出：`universe`、`daily_bars`、`fundamentals_q`、`segment_revenue`、`spx_daily`（schema 见 PRD §12）。

## 规格来源

PRD §3（数据源）、§12（schema）、BUILD-PLAN §3。Licensing：个人不分发 → 当前合规；公开前须复核（Stooq/EDGAR 最友好，其余多禁 redistribute）。

## 未来文件（实现时登记进 File-Contracts）

`run.py`（入口，`make ingest`）、`stooq.py`、`nasdaq.py`、`edgar.py`、`schema.sql`。

## Milestone

M0（先 ~500 只：S&P 500 + 人工种子）→ M6（Stooq bulk 扩到数千）。
