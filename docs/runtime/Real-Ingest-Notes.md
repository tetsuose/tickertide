# Real-Ingest Notes — D.1 冒烟（真实数据）

> 何时读：配 nightly Action（D.2）、debug 真实 ingest、或想知道真实数据 vs fixture 差异时。
> 来源：D.1 真实 ingest 冒烟（2026-06-06 跑，数据 as_of 2026-06-05）。**首次真实数据端到端**——M0–M3 此前全程 fixture 验证。

## 结论：真实 ingest 三源全通，AC-M0 + 三 C9 在真实数据上过

`make pipeline PIPELINE_ARGS="--limit 100"` 3'07" 端到端：AC-M0 八项 `CHECK_OK`；`make export` 三件套（board/ocean/rotation.json）+ `rotation-c9` / `ocean-c9` `GATE_PASS`（board `C9_drift=0`）。D 轨「真实数据从没成功跑过」的硬 gate 解除。

## 各源真实状态 + 坑 / 修复

| 源 | 端点 | 真实结果 | 坑 / 修复 |
|---|---|---|---|
| universe | api.nasdaq.com | HTTP 200，6733 US-listed | **sector 命名**：Nasdaq 12 名 ≠ GICS 11 名 → `ingest/nasdaq.py` `NASDAQ_TO_GICS` 归一（Technology→Information Technology、Finance→Financials、Telecommunications→Communication Services、Basic Materials→Materials；Miscellaneous 无 GICS 对应、保留）→ rotation league join `universe.sector` 通 |
| bars | yfinance (Yahoo) | 127 tickers，ok=127 skip=0 | **Yahoo 429**：curl 直打 raw endpoint 得 429，但 yfinance 库（自带 session/重试）零失败绕过 → bars 非 blocker |
| sector ETF | yfinance | 11 SPDR，ok=11 | M3.1 `ingest/sector_etf.py` 真实路径首验 |
| fundamentals | data.sec.gov (EDGAR) | cik_map 10405，83/100 ok（no_cik=0 no_facts=0） | ebitda 部分 concept 缺 → None → EV/S fallback（M0 已处理）；EDGAR 要 descriptive UA（`ai@cyberbrid.com`） |

## 规模 / 时间（外推 nightly D.2）
- 100 tickers full pipeline = **3'07"**。外推 ≥500：bars ~15–20 分钟、EDGAR fundamentals 受限速更长 → nightly cron 给足超时。
- board.json：126 stocks = 980KB；全量 ≥500 约 ~4MB → mini-chart 降采样 / Parquet 分片（M5/M6，ROADMAP 风险表已记）。

## 小样本特性（非 bug）
- top-100 mktcap + 48 seed 样本里 Real Estate / Utilities 成员少或无 → rotation league member agg `NaN` → export 转 `null` → 前端显 `—`。全量 ≥500 自然有成员；`check_rotation.py` 对无成员 sector skip、不误报。

## 解锁
D.1 硬 gate 过 → **D.2（nightly GitHub Action）+ D.3（Cloudflare Pages 私有上线）可启动**。secrets（EDGAR UA 邮箱、Cloudflare API token）走 Actions secret / env（见 `Credentials-Management.md`），**绝不入库 / PR / 日志**。首次 go-live + 启用 auto-deploy 是 hard stop（需用户点头）。
