# export/ — 静态分发分片

> 模块职责：把 `compute/` 的快照拆成 client 可查的 Parquet/JSON 分片。**Pre-M0（planned）。**

## 职责

零后端范式的「分发」环节：把 DuckDB 计算结果导出为静态文件，由 GitHub Actions 部署到 Cloudflare Pages，client 用 duckdb-wasm 在浏览器直接查 Parquet。

## 输入 → 输出

- 输入：`derived_daily` + `valuation_daily` 最新快照 + `bucket_rrg`（来自 `compute/`）。
- 输出：
  - **Parquet 分片**：Valuation screener 在浏览器横截面查询（duckdb-wasm）。
  - **JSON 分片**：Ocean 点集（含周度快照供 scrubber）、Rotation 多线序列、Discovery 候选、Stock per-name bundle。
- 分片切分粒度是实现级决策（PRD §17 开放问题）。

## 约束

- **不向 client 暴露任何 key。** 导出物只含派生数据，不含源凭证。
- point-in-time：Ocean trail / RS-Ratio 线依赖 membership 的 as-of 正确性（PRD §7 item 3）。

## 规格来源

PRD §5（架构）、§12（export 段）、BUILD-PLAN §2、§8。

## 未来文件

`run.py`（入口，`make export`）、`shards.py`、`manifest.json`（分片清单）。

## Milestone

M2（Ocean 分片）→ M5（Valuation Parquet + Stock bundle）。
