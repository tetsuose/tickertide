# TickerTide — ROADMAP（开发方案）

> PRD §13 里程碑的执行展开。**M0·M1·M2 写到可直接 `make task-open` 执行的粒度（★ 详细方案）；M3–M6 给纲要**（目标/前置/关键未决/验收指针），随各自临近再细化。
> **进度（2026-06-05）：M0 ✅ DONE（数据+引擎，PR #1–#8）· M1 ✅ DONE（Web + Discovery + C9，PR #9–#14）· M2 ✅ DONE（Ocean canvas，PR #16–#20）· M3 ⏳ NEXT（Rotation）。**
> 引用而非复制：数学见 PRD §10，schema 见 PRD §12，约束见 PRD §7。冲突以 PRD §16 为准。
>
> **执行原则（just-in-time）**：M2 之后的实现级决策（客户端框架、duckdb-wasm 接法、shard 粒度、权重常数、theme 阈值）在 PRD §17 标为未决；本文不提前承诺，等 M0 经验落地后回写。每个 milestone 拆成若干 task(worktree+PR)，对应 File-Contracts 的 `planned → implemented → verified` 推进。

---

## M0 — 数据 + 引擎（先窄）★ 详细方案 ✅ DONE

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

## M1 — Web 客户端起步 + Discovery board ★ 详细方案 ✅ DONE

> **已完成 2026-06-05（PR #9–#14）**：M1.1 board.json 导出 → M1.2 Vite+React+TS 脚手架（暗色主题/5-tab shell）→ M1.3 EvidenceCard + MiniChart → M1.4 旋钮 + `composite.ts`（**C9 前端重算对拍引擎、逐位一致**）→ M1.5 Makefile web target + AC-M1 提交测试。AC-M1 全过、可复跑（`make web-test` vitest 11/11 / `make web-build` 自包含 dist）。另：PR #10 加了离线 `make fixture-pipeline`（无网络喂真实引擎）。

**目标**：第一个能看的 web 界面 —— Discovery evidence-first 卡流 + early⟷reliable 旋钮 + composite 排序 + d/d 标注。**email digest 已砍**（PRD §15，2026-06）。

**技术栈（PRD §5.2 已定，2026-06）**：React + Vite + TypeScript（视觉优先 + 与 `equity-monitor-v2.jsx` 同源）。视图用 SVG/DOM，Ocean canvas 留 M2。暗色配色对照 PRD 附录 C。M1 仍静态（Vite 构建 + nightly 导出 JSON，无常驻 server；零后端放宽给未来留口子，M1 不提前加 — 奥卡姆）。

**前置**：M0（composite + valuation + bars 已在 DuckDB）。**对应模块**：`export/`（最小 JSON 导出）+ `web/`（React app）。

### M1 任务拆解（每个 = 一个 worktree+PR）

| task | 分支建议 | 范围 | 产出文件 | 验收 |
|---|---|---|---|---|
| **M1.1** board JSON 导出 | `feat/export-board` | compute 后从 DuckDB 导出 Discovery 数据 | `export/board.py` | board.json 含 per-stock composite + 5 分量 + 6 字段 + 90d bars + valuation + d/d |
| **M1.2** web 脚手架 | `feat/web-scaffold` | Vite+React+TS + 暗色主题 + 布局骨架（5 tab，仅 Discovery 实现） | `web/package.json` `vite.config.ts` `src/{main.tsx,App.tsx,theme.css,types.ts}` | `npm run build` 成功；配色对附录 C |
| **M1.3** evidence-card 组件 | `feat/web-evidence-card` | EvidenceCard + MiniChart（SVG：K线+MA50/150/200+volume+52w 高） | `src/components/{EvidenceCard,MiniChart}.tsx` | 对照 jsx：头部+theme tags+mini 图+6 字段+composite 角标可展开 5 分量 |
| **M1.4** Discovery board + 旋钮 | `feat/web-discovery` | 2 列卡流 + composite 排序 + early⟷reliable 旋钮（前端按 c_* 重算）+ d/d | `src/views/Discovery.tsx` `src/lib/{composite,data}.ts` | 旋钮改 k → 排序实时变；d/d 标注 |
| **M1.5** 验证 + 构建 | `feat/web-build-m1` | npm build 静态产出 + Makefile web target | `Makefile`(web/build target) | AC-M1 全过 |

> 顺序：M1.1（数据）先；M1.2→M1.3→M1.4（前端逐层，依赖脚手架）；M1.5 收尾。

### 数据契约（M1.1 `export/board.py`）

读 DuckDB（`derived_daily` + `valuation_daily` + `daily_bars` + `universe` + `theme_membership`〔M4 前空〕）→ 每票导出：
- 身份：ticker / name / sector / mktcap / themes[]
- 引擎：composite + **5 分量原始值 c_***（供前端按 k 重算）+ rank
- evidence 6 字段：ret1m/3m/6m、from-high、weeks-since-breakout、volX
- mini chart：最近 ~90 日 OHLCV
- 估值：pe/ps/evs/ev_ebitda/growth/rule40 + as_of 新鲜度
- d/d：`composite_prev`（前一交易日 composite）

输出 `web/public/data/board.json`（最新快照）。

### 关键约束（C9 数据一致性）

- **前端 `weights(k)` 必须与 `compute/signals.weights` 数值一致**（同曲线 `rs=.20+.03k …`）。前端用导出的 `c_*` 按 k 重算 composite，**绝不重算引擎**；`src/lib/composite.ts` 直接移植系数 + 单测对拍。
- evidence-card 的 6 字段、mini chart bars、composite 来自**同一份 export**，可互相追溯（与 Ocean/Stock 跨 surface 同源是 M2+ 的事；M1 先保证 board 内部一致）。

### AC-M1（PRD §14）

web 静态构建成功；Discovery 渲染 ≥18 卡；旋钮改 k 排序实时变（前端重算与引擎一致 C9）；6 字段 + 角标展开 5 分量；d/d 标注。

### M1 风险与缓解

| 风险 | 缓解 |
|---|---|
| 前端/引擎 `weights(k)` 不一致 → 数据矛盾（C9） | `composite.ts` 移植 `signals.weights` 系数 + 单测对拍 |
| board.json 体积（数百票 × 90d OHLCV） | M1 先窄（~50–100 票）；mini chart bars 可降采样；M2 export 分片优化 |
| React 引入 node_modules 构建依赖 | `web/` 独立 package.json；`web/node_modules`、`web/dist` 已在 .gitignore |

## M2 — Ocean（canvas，wide explore）★ 详细方案 ✅ DONE

> **已完成 2026-06-05（PR #16–#20）**：M2.1 `export/ocean.py` 周度快照（`common_vintage` 按交易日参数化、M2/M5 共用 — C9）→ M2.2 `ocean-draw.ts` 纯绘制库 + `Ocean.tsx` canvas（固定 RS×Val 轴、√市值尺寸、sector/theme/quadrant 三配色）→ M2.3 手动 WEEK scrubber（无 autoplay C2）+ hover 最近邻 tip → M2.4 click→pin trail/箭头（仅 pinned C2）+ lasso 框选→全局 scope（Ocean 首个 writer C10）+ Discovery scope filter → M2.5 `make export` 接 ocean + `make ocean-c9` C9 跨 surface 校验器 + AC-M2 浏览器端到端验证。AC-M2 全过（517 票流畅、scrub/hover/pin/lasso/scope 粘滞可清、ocean 点位与 Stock 数字逐票一致 C9）。

**目标**：第一个 wide/explore surface —— 数百只票的 canvas 二维相图（x=RS percentile，y=Valuation percentile，**底=便宜**），周度 scrubber + pin→trail，固定 RS×估值轴。引入全局 scope 的**第一个写入口**（lasso）。**轴固定，RRG-axes 已砍（PRD §16）。**

**技术栈（沿用 M1，PRD §5.2/§17）**：React + Vite + TS。Ocean 用**原始 canvas 2D**（`<canvas>` ref + rAF 重绘；数千点 SVG 太慢 — 与 jsx 同源，不引图表库，奥卡姆）。仍静态：读 nightly 导出的 `ocean.json`，**不需要 duckdb-wasm**（那是 M5 Valuation screener 的事）。

**前置**：M0 信号（`derived_daily.rs_pct` + `valuation_daily`）；新增 `export/ocean.py` 周度快照。**对应模块**：`export/` + `web/`。

### M2 任务拆解（每个 = 一个 worktree+PR）

| task | 分支建议 | 范围 | 产出文件 | 验收 |
|---|---|---|---|---|
| **M2.1** ocean 周度导出 | `feat/export-ocean` | 每周末取 `rs_pct` + `val_pct`(common-vintage 横截面百分位) + mktcap + sector + themes，N 周序列 | `export/ocean.py` | `ocean.json`：weeks[] + 每票 N 周位置 pts[]；val_pct 用 common-vintage（§10.5）、底=便宜 |
| **M2.2** canvas 散点骨架 | `feat/web-ocean-canvas` | `<canvas>` 渲染：固定轴 RS×Val + (50,50) 十字线 + 右下绿象限 + size=√mktcap clamp 1.6–11px + color 三模式(sector/theme/quadrant) | `src/views/Ocean.tsx` `src/lib/ocean-draw.ts` | 渲染最新周 ≥500 点；轴/象限/size/color 对照 jsx |
| **M2.3** scrubber + hover | `feat/web-ocean-scrubber` | 周 scrubber(WEEK n/N，**无 autoplay** C2) + hover nearest-neighbor tip | extend `Ocean.tsx` | 拖 scrubber 改周点位移动；hover 出 tip(ticker/sector/RS/Val/P-S/mktcap/themes) |
| **M2.4** pin→trail + lasso scope | `feat/web-ocean-pin-scope` | click→pin toggle→彩色 trail(周连线)+当前位箭头(**仅 pinned** C2)；lasso 框选→**set global scope**；Ocean + Discovery respect scope(先 filter) | `Ocean.tsx` + `App.tsx`(scope writer) + `Discovery.tsx`(scope filter) | pin 一只出 trail+箭头；lasso set scope；非 scope 点变淡(in≈0.72/out≈0.06，C10)；scope 跨 tab 粘滞可一键清 |
| **M2.5** 验证 + 构建 | `feat/web-ocean-build` | AC-M2 + 性能(≥500 点流畅) + `ocean` 接 Makefile(export 扩 ocean) | `Makefile` `src/views/Ocean.test.tsx` | AC-M2 全过；500 票 fixture 下 scrub/hover/pin 流畅 |

> 顺序：M2.1（数据）先；M2.2→M2.3→M2.4（canvas 逐层）；M2.5 收尾。验证用 `make fixture FIXTURE_ARGS="--tickers 500"` 造 ≥500 票（真实 ingest 需 Nasdaq/Yahoo，常不可达）。

### 数据契约（M2.1 `export/ocean.py` → `web/public/data/ocean.json`）

Ocean 要 scrubber + trail，需**每票的周度位置序列**（非 M1 的单日快照）。每周末交易日取：
- 位置：`rs_pct`（来自 `derived_daily.rs_pct`，已是每日横截面百分位）；`val_pct`（估值横截面百分位，**common-vintage** §10.5，默认 P/S，**底=便宜**）。
- 不变量：`mktcap`(size)、`sector`(color)、`themes[]`(theme color/filter)。
- 结构：`{ as_of, weeks: ["YYYY-MM-DD" × N], metric: "ps", stocks: [{ ticker, sector, mktcap, themes, pts: [{rs, val} × N] /* 老→新 */ }] }`。
- N 默认最近 ~14 周（对齐 jsx；可调）。输出 `web/public/data/ocean.json`（最新快照，似 board.json gitignore 派生）。

### 关键约束

- **C9（数据一致性）**：Ocean 的 `rs_pct`/`val_pct` 与 Discovery/Stock **同源**（`derived_daily`/`valuation_daily`），点位可追溯到 Stock 数字。`val_pct` 的 common-vintage 口径**即 M5 Valuation screener 复用的同一函数**（M2 定义、M5 精化门槛），避免两处估值百分位漂移。
- **C10（scope）**：Ocean 是 scope 的**第一个写入口**（M1 的 scope 单一真源已就位但无 writer）。M2.4 同时给 **Discovery 补 scope filter**（先 filter 再排序，PRD §9.3）；scope 跨 tab 粘滞、可见可一键清（沿用 M1 App 的单一 state）。
- **C2（认知带宽）**：trail/箭头**仅 pinned**；scrubber 手动、**无 autoplay**（PRD §15 OUT OF SCOPE）。
- **性能（NFR-8）**：canvas 2D + rAF；hover 最近邻线性扫描（500–2000 点可接受）；静态层可离屏缓存。数千只（M6）再上空间索引/降采样。

### 开放问题落地（PRD §17）

- **lasso → set scope**：M2.4 做真实 writer（§17 原「mock 只做 respect/变淡」→ 本期兑现写入口）。
- **shard 粒度**：M2 单文件 `ocean.json`（~500 票 × 14 周，仅位置+元数据无 OHLCV，几百 KB 可接受）；M6 扩量再分片。
- **common-vintage 门槛 %**：沿用 export 现有近似（as-of ≤95d fresh cohort）；真实「末季 ≥X% 已报」与 M5 统一精化。
- **duckdb-wasm**：M2 不需要（读静态 `ocean.json`）；留 M5。

### AC-M2（PRD §14）

Ocean 渲染 ≥500 点流畅；scrubber 切周；pin 一只 → 出现 trail+箭头；scope=sector 时非成员变淡（C10）；**Ocean 点位与 Stock 数字一致**（C9）。

### M2 风险与缓解

| 风险 | 缓解 |
|---|---|
| 周度 `val_pct` common-vintage 与 M5 口径漂移 | M2 定义即 M5 复用的同一 percentile 逻辑；export 层共享，不各写一套 |
| canvas ≥500 点 hover/scrub 卡顿 | 原始 canvas 2D + rAF；最近邻线性扫描(500–2000 OK)；静态层离屏缓存 |
| `ocean.json` 体积（票×周×payload） | M2 仅位置+元数据（无 OHLCV），~500×14 几百 KB；M6 分片 |
| scope 第一个 writer 引入跨 tab 状态 bug | scope 已是 App 单一真源；M2.4 只加 writer + filter，sticky 由现有 state 保证 |
| ≥500 点测试数据（真实 ingest 网络不可达） | `make fixture FIXTURE_ARGS="--tickers 500"` 造合成 universe 喂真实引擎 |

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
M0(数据+引擎)✅ ─┬─> M1(Discovery)✅
                ├─> M2(Ocean) ──> M5(Valuation+Stock)
                ├─> M3(Rotation) ──> M4(主题分类)
                └─────────────────────────────────> M6(扩量, 需 M0–M5 稳定)
```

M0 是所有后续的根。先把 M0 五个 task 跑通，再按 explore(M2)/decide(M3) 两条线推进；M6 收尾扩量。
