# TickerTide — ROADMAP（开发方案）

> PRD §13 里程碑的执行展开。**M0 写到可直接 `make task-open` 执行的粒度；M1–M6 给纲要**（目标/前置/关键未决/验收指针），随各自临近再细化。
> 引用而非复制：数学见 PRD §10，schema 见 PRD §12，约束见 PRD §7。冲突以 PRD §16 为准。
>
> **执行原则（just-in-time）**：M2 之后的实现级决策（客户端框架、duckdb-wasm 接法、shard 粒度、权重常数、theme 阈值）在 PRD §17 标为未决；本文不提前承诺，等 M0 经验落地后回写。每个 milestone 拆成若干 task(worktree+PR)，对应 File-Contracts 的 `planned → implemented → verified` 推进。

---

## M0 — 数据 + 引擎（先窄）★ 详细方案

**目标**：对 ~500 只票端到端跑通 `ingest → DuckDB → compute`，产出 `composite` 与 `valuation`。证明数据拉得动、composite 直观。**不做 UI、不做 export、不扩量。**

**前置依赖**：无（这是第一个产品里程碑）。Python stdlib + DuckDB（产品代码可用 pip 装 `duckdb`；注意 `engine/index.py` 工作流引擎仍须零依赖，二者分离）。

**对应模块**：`ingest/`、`compute/`。**产出**：`data/tickertide.duckdb`（gitignored）。

### M0 任务拆解（每个 = 一个 worktree+PR）

| task | 分支建议 | 范围 | 产出文件 | 验收 |
|---|---|---|---|---|
| **M0.1** universe + 价格 ingest | `feat/ingest-prices` | Nasdaq screener → `universe`；Stooq bulk → `daily_bars`；`^GSPC`/SPY → `spx_daily` | `ingest/run.py` `ingest/nasdaq.py` `ingest/stooq.py` `ingest/schema.sql` `ingest/universe_seed.txt` `compute/db.py` | universe ≥500 US-only；daily_bars 覆盖 universe 且 ≥504 交易日(≈2y)；缺口已补/标记 |
| **M0.2** fundamentals ingest | `feat/ingest-edgar` | EDGAR `company_tickers.json`(ticker→CIK) + `companyfacts` → `fundamentals_q` + `segment_revenue` | `ingest/edgar.py` | trailing-4Q 的 revenue/shares/debt/cash/ebitda/eps 落地；as-of(filed_date) 正确；缺失字段有 fallback 且标记 |
| **M0.3** compute 信号 | `feat/compute-signals` | EWMAC、RS percentile、rs_accel、high_prox、trend_quality、volume、composite | `compute/run.py` `compute/signals.py` | `derived_daily.composite` 生成；5 分量∈[0,1]；旋钮 k 重配权两端归一 Σ=1 |
| **M0.4** compute 估值 | `feat/compute-valuation` | ASOF JOIN → 日频倍数；E≤0→n.m.；common-vintage percentile | `compute/valuation.py` | `valuation_daily` 对齐；n.m. 退 P/S；stale 不进 percentile |
| **M0.5** pipeline 串联 + 抽查 | `feat/pipeline-m0` | `make pipeline` 本地跑通；抽查校验脚本 | 接 `Makefile` 的 ingest/compute target；`compute/check.py` | `make pipeline` 端到端无错；抽查 5 只 composite 方向与人工一致 |

> 顺序：M0.1 → M0.2 可并行后段；M0.3 依赖 M0.1（价格）；M0.4 依赖 M0.1+M0.2；M0.5 依赖全部。建议 M0.1 先行打通 DuckDB 落地范式。

### 数据源接入要点（M0 已确定的硬事实）

- **Stooq**：per-symbol `https://stooq.com/q/d/l/?s={sym}.us&i=d`（CSV，无限速）；或 bulk DB 包。校验覆盖率，缺口用 fallback。adj_close 处理拆股/分红。
- **Nasdaq screener**：`https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=0&exchange=NASDAQ|NYSE|AMEX`，**必须带 descriptive `User-Agent` header**，否则 403。一次拿 universe + mktcap + sector/industry + trailing P/E。
- **EDGAR**：先拉 `https://www.sec.gov/files/company_tickers.json` 建 ticker→CIK(10 位补零)；再 `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`。**必须带 descriptive `User-Agent`（含联系邮箱），限 ~10 req/s。** concept 名不统一（`Revenues` / `RevenueFromContractWithCustomerExcludingAssessedTax` 等）→ 需 concept 候选列表 + fallback。
- **US-only**：Nasdaq screener 已限三交易所；EDGAR 天然 US filers。
- **universe seed**：S&P 500 + 人工种子清单（AI/Robotics/Space/Optical/Semis 等主题代表票），落 `ingest/universe_seed.txt`。

### DuckDB 落地范式（M0.1 定型，后续复用）

- 单文件 `data/tickertide.duckdb`，single-writer、offline batch。
- schema 见 PRD §12；`ingest/schema.sql` 建表，`compute/db.py` 封装连接/`ASOF JOIN`/`QUALIFY`。
- `valuation_daily` 由 `daily_bars ASOF JOIN fundamentals_q ON ticker AND date>=period_end`（PRD §10.5）。

### AC-M0 验收细化（在 PRD §14 AC-M0 基础上可测化）

1. `universe` ≥500 行，全部 US-listed（exchange ∈ {NASDAQ,NYSE,AMEX}）。
2. `daily_bars` 覆盖 universe，每只 ≥504 交易日（足够算 252d high + 126d return + percentile）。
3. `fundamentals_q` 每只有 ≥4 季 trailing 数据，`filed_date`(as-of) 非空。
4. `derived_daily.composite` 全 universe 生成；随机抽 5 只，5 分量 ∈[0,1] 且 composite 方向与人工心算一致。
5. `valuation_daily`：构造一只 E≤0 的票，确认 P/E=n.m. 且回退 P/S；ASOF 边界正确（季报日阶进）。
6. common-vintage：构造混合 vintage cohort，确认 stale 行不进 percentile 分母。
7. `make pipeline` 本地端到端无错；`make verify` 两 gate `GATE_PASS`（新增 ingest/compute 代码合同填实）。

### M0 风险与缓解

| 风险 | 缓解 |
|---|---|
| EDGAR concept 名不统一、segment 脏 | concept 候选列表 + fallback；segment 留到 M4 精修，M0 只取总营收 |
| Stooq 覆盖/缺口 | 校验覆盖率，缺口用 fallback 源补并标记 |
| ticker→CIK 映射漂移 | 用 SEC 官方 company_tickers.json，按 ticker 主键 |
| 历史不足算 252d/126d | 拉 ≥2 年；不足的票标记并暂排除横截面 |
| 把工作流引擎也装了 pip 依赖 | 产品代码(`ingest/`/`compute/`)可用 duckdb；`engine/index.py` 保持 stdlib only |

---

## M1 — Leaders + digest（纲要）

- **目标**：bounded top-N board（Discovery 的最小可用形态）+ early⟷reliable 旋钮 + day-over-day 标注 + 每日 email digest（保证你真的会看）。
- **前置**：M0（composite 已生成）。
- **关键未决**：digest 实现方式（GitHub Actions + 邮件服务 vs 本地）；board 是先静态 HTML 还是直接进 `web/` 框架。
- **验收**：PRD §14 AC-M1。

## M2 — Ocean（纲要）

- **目标**：canvas 散点（≥500 点）+ 周 scrubber + pin→trail，轴固定 valuation×RS，respect global scope。
- **前置**：M0 信号 + `export/` 周度快照分片（JSON）。
- **关键未决**：客户端框架、canvas 渲染方案、shard 切分粒度（PRD §17）。
- **验收**：PRD §14 AC-M2（含 C9 数据一致性：Ocean 点位与 Stock 数字一致；C10 respect scope）。

## M3 — Rotation（纲要）

- **目标**：11 SPDR ETF 的 RS-Ratio 多线图 + RS-rank 表 + breadth；点 bucket → N=1 单线 + 成员卡。
- **前置**：M0 价格；`compute/rotation.py`（RS-Ratio 序列，PRD §10.4）。
- **关键未决**：RS-Ratio 的 n1/n2/n3 窗口常数（透明 reconstruction，非复刻 StockCharts）。
- **验收**：PRD §14 AC-M3（4 态由 level+slope 推回）。

## M4 — 主题分类（纲要）

- **目标**：EDGAR + LLM 营收锚定 membership（point-in-time, human-in-loop）→ theme RS-Ratio 线 / theme 上色。
- **前置**：M0 EDGAR segment；M3 Rotation 框架（theme 复用 bucket 多线）。
- **关键未决**：营收暴露阈值；LLM→human 审核流形态；segment 脏数据兜底（PRD §17、C6）。
- **验收**：PRD §14 AC-M4（point-in-time 不回溯污染；theme 指数非市值加权 C4）。

## M5 — Valuation screener + Stock detail（纲要）

- **目标**：duckdb-wasm 浏览器横截面查询；as-of 三档上色 + common-vintage percentile；Stock 的 price↔fundamentals 时间轴对齐 stack。
- **前置**：M0 估值；`export/` 的 Parquet 分片 + per-name bundle。
- **关键未决**：duckdb-wasm 接法、Parquet 分片粒度、Stock bundle 结构（PRD §17）。
- **验收**：PRD §14 AC-M5。

## M6 — 扩量（纲要）

- **目标**：universe 由 ~500 扩到数千（Stooq bulk 已支撑）。
- **前置**：M0–M5 在 ~500 只上稳定。
- **关键未决**：ingest 批量化/增量化；compute 全列扫描在数千只上的性能；client 数千点渲染（NFR-8）。
- **验收**：PRD §14 AC-M6（扩到 ≥2000 仍满足 AC-M2 性能）。

---

## 全局依赖链

```
M0(数据+引擎) ──┬─> M1(Leaders+digest)
                ├─> M2(Ocean) ──> M5(Valuation+Stock)
                ├─> M3(Rotation) ──> M4(主题分类)
                └─────────────────────────────────> M6(扩量, 需 M0–M5 稳定)
```

M0 是所有后续的根。先把 M0 五个 task 跑通，再按 explore(M2)/decide(M3) 两条线推进；M6 收尾扩量。
