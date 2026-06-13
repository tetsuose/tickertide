# TickerTide — ROADMAP（开发方案）

> PRD §13 里程碑的执行展开。**M0·M1·M2·M3 + 部署轨 D 写到可直接 `make task-open` 执行的粒度（★ 详细方案）；M4–M6 给纲要**（目标/前置/关键未决/验收指针），随各自临近再细化。**D（部署 + 夜间自动化）是正交 infra 轨，建议 M3 后与 M4/M5 并行。**
> **进度（2026-06-13）：M0 ✅（PR #1–#8）· M1 ✅（#9–#14）· M2 ✅ Ocean（#16–#20）· M3 ✅ Rotation（#25–#29）· D ✅ 部署（#37–#44、#48、#50；tickertide.pages.dev）· M4 ✅ DONE 主题分类（M4.1–4.4 #32–#36、M4.6 接线 #51、M4.5 LLM 抽取+human 审批 #52）· M5 ⏳ 预览已上线（Valuation+Stock tab #53，board.json 驱动）、正式版（duckdb-wasm + 时间轴 stack）待开。**
> **M4.5 NVDA demo（真实上线）**：`themes/extract.py` 拉真实 10-K → `claude` CLI（print 模式，**订阅 plan 额度，不接 API key**）→ 候选；sejonep 审批 AI 0.90/SEMI 1.00（C6）。真实 nightly 暴露并修了 2 个数据成熟度 bug：**theme 历史不足**（#54 seed as_of 回填到 bars 最早日 + check_theme graceful SKIP）、**approved as_of off-by-one**（#55 默认用 10-K filing 日而非审批日，否则最新 EOD board 回落 seed）。线上 NVDA 现显 SEMI 100%/AI 90% chip、theme Rotation 8 线 ×52 周。
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

## M3 — Rotation（narrow decide）★ 详细方案 ✅ DONE

**目标**：第二个 decide surface —— 11 个 GICS sector 的 **RS-Ratio 多线图（非散点）** + enriched league 表（4 态 + breadth + 估值 + 多 horizon relative return）+ GICS↔Theme 切换；点 bucket → **inline drawer**（N=1 单线斜率着色 + sector 聚合 summary + 成员证据卡）并 **set 全局 scope**（Rotation = 第二个 scope writer）。**RRG 散点已砍（PRD §16）；momentum = RS-Ratio 斜率（RS-Momentum 归一量整砍）。**

**技术栈（沿用，PRD §5.2）**：React+Vite+TS。Rotation 用 **SVG 多线图**（~11–22 条线 × ~52 周；DOM/SVG 清晰、易 hover/标签——不用 canvas，奥卡姆；与 M1 `MiniChart` 同源 SVG 范式）。仍静态：读 nightly 导出的 `rotation.json`。**成员证据卡复用 `board.json`**（按 scope filter，不重复造数据 — C9/DRY）。UX 合同 = `docs/equity-monitor-v2.jsx` 的 `RSRatioLines`(多线) + `SoloRSLine`(N=1)（**RRGChart 散点是已砍版本，勿抄**）。

**前置**：M0 价格 + `derived_daily`/`valuation_daily`（成员聚合）+ `spx_daily`（benchmark B）。新增：sector ETF 价格 ingest + `compute/rotation.py`（RS-Ratio 序列，PRD §10.4）。**对应模块**：`ingest/` + `compute/` + `export/` + `web/`。

### M3 任务拆解（每个 = 一个 worktree+PR）

| task | 分支建议 | 范围 | 产出文件 | 验收 |
|---|---|---|---|---|
| **M3.1** sector ETF 价格 ingest | `feat/ingest-sector-etf` | 11 SPDR ETF(XLK/XLF/XLV/XLY/XLC/XLI/XLP/XLE/XLU/XLRE/XLB) EOD bars → 独立 `bucket_bars`；sector→ETF 映射；`fixture.py` 同步造合成 ETF | `ingest/sector_etf.py` `ingest/schema.sql`(bucket_bars) `ingest/sector_etf_map.txt` `compute/fixture.py`(合成 ETF) | bucket_bars 覆盖 11 sector、≥2y 足量；offline fixture 也有 11 条；**ETF 不进 universe 横截面**(不污染 rs_pct/rank) |
| **M3.2** RS-Ratio 计算 | `feat/compute-rotation` | 周线 RS=100×P_S/P_B → JdK RS-Ratio(z-score recenter 100) → `bucket_rrg`；league 聚合(breadth %>MA50/MA200、#at-52w-high、composite 中位、agg EV/S、多 horizon rel return) | `compute/rotation.py` `ingest/schema.sql`(bucket_rrg) | bucket_rrg 11 行序列；RS-Ratio 定性合理(强 sector >100)；sector **temporal** z-score；聚合量取自 universe 成员 |
| **M3.3** rotation 导出 | `feat/export-rotation` | 每 bucket RS-Ratio 序列 + level/slope_4w/state + 聚合 + 成员 top-N ticker | `export/rotation.py` | rotation.json：buckets[] 含序列 + 4 态 + 聚合；成员卡走 board.json 不重复 |
| **M3.4** web Rotation view | `feat/web-rotation` | SVG 多线图(hover 高亮其余淡 + 右缘按末值排序贴标签防重叠 + y=100 基线) + league 表(#/bucket/RS-Ratio/Δ4w/state) + GICS↔Theme 切换；钻进 inline drawer(N=1 单线斜率色 + sector summary + 成员卡) + **set scope(第 2 writer)** | `web/src/views/Rotation.tsx` `web/src/lib/rotation-draw.ts`(SVG path/scale/state 纯函数) `web/src/App.tsx`(接 Rotation) | 对照 jsx `RSRatioLines`/`SoloRSLine`；≥11 线叠图；4 态正确；点 bucket→N=1+成员；set scope 跨 tab |
| **M3.5** 验证 + 构建 | `feat/web-rotation-build` | AC-M3 + Makefile(export 扩 rotation、pipeline/compute 扩 rotation) + 测试 + 浏览器 smoke | `Makefile` `web/src/views/Rotation.test.tsx` `web/src/lib/__fixtures__/rotation.sample.json` | AC-M3 全过；4 态/斜率/钻进/scope 头测；≥11 线浏览器流畅 |

> 顺序：M3.1(ETF 数据)→M3.2(RS-Ratio)→M3.3(导出)→M3.4(前端逐层)→M3.5(收口)。验证用 `make fixture-pipeline`（`fixture.py` 扩出合成 ETF）；真实 ingest 走 Stooq EOD。

### 数据契约（M3.3 `export/rotation.py` → `web/public/data/rotation.json`）
```
{ schema_version, as_of_date, benchmark:"SPX",
  params:{ basis:"weekly", n1_ema, n2_window, k },        // 透明 reconstruction 常数（暴露可审计）
  weeks:["YYYY-MM-DD" × N],                               // 周线 x 轴(~52)，老→新
  buckets:[ { bucket_type:"sector", bucket:"Information Technology", etf:"XLK",
              rs_ratio:[…×N],                             // 多线图序列
              level, slope_4w, state:"LEADING|WEAKENING|IMPROVING|LAGGING",
              breadth_ma50, breadth_ma200, at_high, member_count,
              composite_median, agg_evs, rel_ret_1m, rel_ret_3m, rel_ret_6m,
              members:[ ticker × top-N ] } × 11 ] }
```
- **成员证据卡不进 rotation.json**：前端按 scope=sector 从 `board.json` filter（同源 C9、DRY）；rotation.json 只承载 bucket 级序列 + 聚合 + 成员 ticker 清单。
- N 默认最近 ~52 周。输出 `web/public/data/rotation.json`（派生、gitignore，似 board/ocean）。

### 数学规格（RS-Ratio 透明 reconstruction，PRD §10.4）
- **周线**（daily_bars/ETF resample 到周五收盘）。`RS = 100 × P_bucket / P_SPX`（price relative，≠RSI≠IBD RS Rating）。
- `M = EMA(RS, n1)`；`RS-Ratio = 100 + k·(M − SMA(M,n2)) / σ(M,n2)`（z-score recenter 100）。**>100 = 跑赢自身近期趋势**。
- **momentum = RS-Ratio 斜率**；league `Δ4w = rs_ratio[t] − rs_ratio[t−4]`；N=1 线色 = 短窗(K≈3)平滑斜率（↑绿 / ↓红）。
- **4 态**（PRD §9.4）：level≥100 & slope≥0 → LEADING；≥100 & <0 → WEAKENING；<100 & ≥0 → IMPROVING；<100 & <0 → LAGGING。
- **z-score 基准**：11 GICS sector 用 **temporal**（对自身历史）；theme（M4）成分会变 → **point-in-time**（否则尾迹虚构，C3）。
- **常数默认（M3 定、可调，§17）**：`n1=10` 周 EMA、`n2=10` 周、`k=1`（StockCharts 量级 ~95–105）。**透明 reconstruction，不声称复刻 de Kempenaer / StockCharts 数值**（确切常数未公开）。

### 关键约束
- **C9 同源**：league 的 breadth / at-high / composite 中位 / 估值取自 `derived_daily`/`valuation_daily` 的 **universe 成员**（与 Discovery/Ocean/Stock 同源、可追溯）；成员卡复用 `board.json`；RS-Ratio 的 benchmark = `spx_daily`。
- **C10 第二个 scope writer**：点 league 行/线 → set scope(sector:X) + **原地展开 inline drawer**（不 auto-jump，§9.1.2「改 scope 与 换 view 解耦」）；「在 Ocean/Valuation/Discovery 看全部成员」按钮 = set scope + 切 tab。沿用 M2.4 App 单一真源 + Discovery/Ocean respect（Valuation 留 M5）。
- **IA（DRY/Occam）**：bucket→members 是 scope 收窄，**不建第 6 个 sector-detail surface**；drawer 内联在 Rotation tab。
- **透明 reconstruction**：RS-Ratio 是可审计重构，**不复刻 StockCharts 数值**（专有警告，PRD §10.4）；常数写进 rotation.json `params`。
- **ETF 不污染横截面**：sector ETF 价存独立 `bucket_bars` 表，**绝不进 universe 的 rs_pct/rank 横截面**（否则百分位漂移，破 C9）。

### 开放问题落地（PRD §17）
- **RS-Ratio 常数**：n1/n2/k 用上述默认；真实数据落地后回写校准（不回测优化 alpha，买 robustness）。
- **ETF 存储**：独立 `bucket_bars(bucket_type,bucket,date,close)`（不碰 M0 compute 横截面）；M4 theme index 复用同表（bucket_type='theme'）。
- **offline ETF**：`compute/fixture.py` 扩出 11 条确定性合成 sector ETF 序列（供无网络验证 rotation；合成即可，值不必对齐成员）。
- **daily vs weekly**：RS-Ratio 周线为主；存日线 ETF close、`rotation.py` resample 周五。
- **theme buckets**：M3 仅 sector；GICS↔Theme 切换 UI 就位、**Theme 空到 M4**（theme_membership + 非市值加权 theme index）。

### AC-M3（PRD §14）
≥11 条 sector RS-Ratio 线叠一张图；league 表 4 态正确（level+slope 推回）；点 bucket → N=1 单线（斜率着色）+ 成员证据卡；set scope=sector 跨 tab 粘滞（Discovery/Ocean 成员过滤）。

### M3 风险与缓解
| 风险 | 缓解 |
|---|---|
| RS-Ratio 常数无权威值 | 透明 reconstruction + 常数显式暴露在 rotation.json `params`；不声称复刻 StockCharts |
| sector ETF 数据缺（Stooq/网络不可达） | 主用 Stooq EOD；offline fixture 造合成 ETF；缺口标记 |
| ETF 混入 universe 横截面污染 rs_pct/rank | ETF 存独立 `bucket_bars`，compute 横截面只跑 universe（硬隔离） |
| league 聚合与 Discovery 数字不一致 | 聚合直接读 `derived_daily`/`valuation_daily` 成员、成员卡复用 board.json（单一源 C9） |
| 多线图 11–22 线重叠难读 | hover 高亮一条其余变淡、右缘按末值排序贴标签防重叠（jsx `RSRatioLines` 范式） |
| theme z-score 用 temporal 致尾迹虚构 | sector temporal、theme(M4) point-in-time（C3 硬约束） |

## D — 部署 + 夜间自动化（infra 轨）★ 详细方案 ✅ DONE（PR #37–#44、#48、#50；tickertide.pages.dev）

> **不占 M 编号**（M0–M6 是 PRD §13 的 feature 里程碑；D 是正交的 infra 轨）。**建议 M3 完成后启动、与 M4/M5 并行**，不阻塞功能开发；每多做一个 surface 自动随 nightly 上线。

**第一性原理**：这是 **EOD 静态前端**——`make web-build` 任何时候能出静态产物，但**数据一过夜就死**。所以"何时部署"≈"**何时真实 EOD 数据能自动流入**"，与做了几个 surface 无关。当前最大未知是**真实 ingest（Stooq/Nasdaq/EDGAR）从没成功跑过**（全程 fixture 验证）；故 **D.1 真实 ingest 冒烟是整条轨的硬 gate**：真实数据不通，后面不做。

**目标**：把静态客户端 + nightly 真实数据管道接通并上线到 Cloudflare Pages，生产域公开访问，让工具天天可用、并把最高风险的真实 ingest + 自动化逼到现在暴露（而非拖到 M6）。访问控制与数据源条款是两个独立 gate，后者按 PRD §6.2 / NFR-7 复核。

**技术栈/范式（PRD §5.1/§5.2/§16）**：离线预计算 + 静态分发；GitHub Actions（cron）跑 `pipeline→export→web-build→发布`；Cloudflare Pages 生产公开 host（WORKFLOW §8 已点名）。`engine/index.py` 仍 stdlib-only；CI 仅给产品代码装 `requirements.txt`。

**前置**：M0–M3（数据+引擎+至少 Discovery/Ocean/Rotation 可看）；有网机器/CI 可达数据源。**对应模块**：`ingest/` `Makefile` `.github/workflows/` + 新 host 配置。

### D 任务拆解（每个 = 一个 worktree+PR）

| task | 分支建议 | 范围 | 产出文件 | 验收 |
|---|---|---|---|---|
| **D.1** 真实 ingest 冒烟（硬 gate，先做） | `chore/real-ingest-smoke` | 有网机器手动 `make pipeline` 真实数据；记录/修真实坑（Nasdaq UA·403、Stooq 缺口、EDGAR 限速/concept、yfinance fallback、缺口标记） | ingest 真实修正（按需）+ `docs/runtime/` 真实数据 note | 真实 universe ≥500 US-only + bars ≥504d + fundamentals ≥4Q 落地；**AC-M0(`compute/check.py`) 在真实数据上过**；board/ocean/rotation.json 真实产出、size 合理 |
| **D.2** 夜间数据管道（Action） | `chore/nightly-pipeline` | `nightly.yml`：cron（美东盘后）→ 装 deps → `make pipeline`(真实)→`make export`(board+ocean+rotation)→`make web-build`→上传 dist+data artifact | `.github/workflows/nightly.yml` | `workflow_dispatch` 手测跑通、产物含最新 as_of；连续 2 晚自动刷新；engine 仍 stdlib、产品 deps 装在 CI |
| **D.3** 静态 host 上线（生产公开） | `chore/deploy-pages` | Cloudflare Pages 接 D.2 产物（nightly 发布 dist）；生产域公开，预览 wildcard 可由 Cloudflare Access 保护；auto-deploy 接线 | host 配置（wrangler/pages）+ deploy workflow | 站点公开可访问、Vite `base='./'` 路径正常、数据 fetch 正常、nightly 刷新可见 |
| **D.4**（可选）新鲜度健康 | `chore/deploy-health` | 前端显著位露 as_of/数据龄；pipeline 失败不静默服务陈旧（显警告/不发布）；可选告警 | `web/`（as_of badge）+ workflow 失败处理 | 陈旧/失败**可见**、不静默 |

> 顺序：**D.1（gate）必先过** → D.2 → D.3 →（D.4）。**别在未验证的 ingest 上盖自动化**。

### 关键约束
- **数据是绑定约束**：静态前端无价值除非 nightly 真实数据流入 → D.1 真实 ingest 是全轨硬 gate。
- **访问控制**：生产域 `tickertide.pages.dev` 公开无登录；预览 wildcard 可由 Cloudflare Access 限白名单；数据源条款复核另按 PRD §6.2 / NFR-7。
- **secrets 不入 repo**（见 `docs/runtime/Credentials-Management.md`）：EDGAR 联系邮箱 UA、Cloudflare API token 走 **Actions secret / env**，绝不进仓库/PR/日志。
- `engine/index.py` 保持 stdlib-only；CI 装 `requirements.txt` 仅给 `ingest/`/`compute/`/`export/`。
- **部署 / 合入 auto-deploy 分支 = hard stop**（WORKFLOW §8 / 全局 CLAUDE.md）：**首次 go-live + 启用 auto-deploy 需用户明确点头**。
- **不阻塞 feature 轨**：D 与 M4/M5 并行；后续每加一 surface 随 nightly 自动上线。

### 开放问题落地
- **host 选型**：Cloudflare Pages 默认（§8）；GitHub Pages 私有较弱，次选。
- **刷新节奏**：美东盘后 cron 时区 + 数据源更新时点（避开未结算）。
- **真实源脆弱兜底**：D.1 暴露后定（yfinance fallback、重试、缺口标记，§18）。
- **dist 体积**：真实全 universe 的 board.json 可能很大（M1 已记风险）→ mini-chart 降采样 / M5 Parquet 分片；nightly 注意产物大小。

### AC-D（部署轨完成）
真实数据端到端（D.1：AC-M0 真实过）；nightly Action 自动刷新（D.2）；**Cloudflare Pages 公开生产上线、访问到最新 as_of 的 Discovery/Ocean/Rotation**（D.3）；无 secrets 入库；陈旧/失败可见（D.4）。

### D 风险与缓解
| 风险 | 缓解 |
|---|---|
| 真实免费源脆（Nasdaq 403 / Stooq 缺口 / EDGAR 限速） | D.1 先证 + descriptive UA / 重试 / yfinance fallback / 缺口标记（§18） |
| nightly 网络 / CI 环境差异 | `workflow_dispatch` 先手测 + job 失败可见（不静默） |
| 数据分发合规 | 公开展示前复核数据源条款（PRD §6.2 / NFR-7） |
| secrets 泄漏 | Actions secret / env，不入 repo / PR / 日志（安全硬线） |
| 陈旧数据被静默服务 | D.4 新鲜度可见 / 失败不发布 |

## M4 — 主题分类（concept themes）★ 详细方案 ✅ DONE（M4.1–4.6，PR #32–#36 / #51 / #52；NVDA demo 真实上线，真实数据 fix #54 #55）

**目标**：在 GICS 标准底之上叠加**概念主题**的 point-in-time membership（营收锚定、连续 exposure），产出 theme RS-Ratio 多线（复用 Rotation theme 模式）+ 全 surface theme 上色/chips。**LLM = candidate generator + revenue extractor，human-in-loop 审批，绝不当权威 classifier**（PRD §8.3）。

**脊柱复用（M3 框架，不建新 surface）**：theme 走同一套 `bucket_bars`(bucket_type='theme') → `bucket_rrg` → `rotation.json` → Rotation 多线（GICS↔Theme 切换 UI 已 M3.4 就位）；8 theme 配色 `THEME_VAR`(`--th-*`) 已就位；`board.py` 的 `_themes`(M4 前空) + Stock/Discovery theme chips 已留接口。

**前置**：M0 EDGAR(`segment_revenue` 建表未填) + M3 Rotation 全链；`universe_seed.txt` 已有 8 theme 的代表 ticker 分组（seed membership 来源）。**对应模块**：`themes/`(新，pre-M0 planned) + `compute/` + `export/` + `web/`。

**8 主题（PRD §8.2 / `THEME_VAR` keys）**：AI · ROBO(Robotics) · SPACE(Space Compute) · OPTIC(Optical) · SEMI(Semis) · NUKE(Nuclear) · CYBR(Cybersecurity) · CLOUD。多对多、绝不强加 MECE（NVDA 同进 AI+SEMI 是 feature 不是 bug）。

### M4 任务拆解（每个 = 一个 worktree+PR）

| task | 分支建议 | 范围 | 产出文件 | 验收 |
|---|---|---|---|---|
| **M4.1** theme membership 数据基座 | `feat/theme-membership` | `theme_membership` 表(point-in-time) + `themes.yaml`(8 theme 定义/配色/cap) + seed membership(从 universe_seed 结构化、带 exposure 初值) + db helper(PIT 查询) + fixture 扩合成 membership | `ingest/schema.sql`(theme_membership) `themes/themes.yaml` `themes/seed.py` `compute/db.py` `compute/fixture.py` | ≥4 theme membership、(ticker,theme,as_of_date) PK、exposure∈[0,1]+approved_by；fixture 含多 as_of(PIT) |
| **M4.2** theme index(非市值加权,PIT) | `feat/compute-theme-index` | 每 theme 每日 = **as-of t 成员**的 exposure-weighted(capped) adj_close 复合 → `bucket_bars`(bucket_type='theme')；PIT 构建(成员变→rebalance，不用今天成员回溯) | `compute/theme_index.py` `compute/db.py` `compute/fixture.py` | theme index ≥4、非市值加权(单票权重≤cap)；**改 membership as_of → 历史 index 段不回溯变**(C3) |
| **M4.3** theme RS-Ratio + league | `feat/compute-theme-rotation` | `compute/rotation.py` 扩 bucket_type='theme'(RS-Ratio 算法复用 M3.2、对 theme index 价做)；theme league 成员取自 `theme_membership` PIT(非 universe.sector) | `compute/rotation.py` | bucket_rrg theme ≥4 序列；theme league 成员同源 theme_membership(C9)；RS-Ratio 定性合理 |
| **M4.4** export theme + web theme 模式 + chips | `feat/web-theme-rotation` | export theme buckets→rotation.json；Rotation theme 模式填数据(复用 M3.4 多线/league/钻进 + THEME_VAR 上色)；`board.py` `_themes` 填(PIT chips+exposure%)；theme C9 | `export/rotation.py` `web/src/views/Rotation.tsx` `export/board.py` `export/check_rotation.py` | theme 多线渲染、membership chips(exposure%)；改 as_of 历史不污染；theme league↔board C9 |
| **M4.5 ✅ #52** LLM 抽取 + human 审批 | `feat/theme-llm-review` | `extract.py`(拉 10-K → **claude CLI print 模式·订阅 plan 额度·不接 API key**·operator 步骤非 CI → 营收锚定候选) + `review.py`(human 审批·--by 必填·as_of 默认 filing 日 #55) + `land.py`(approved/*.json git 持久·每轮重播) + `run.py`(编排) + `check_land.py`(land+PIT 验收) | `themes/{extract,review,land,run,check_land}.py` `themes/approved/NVDA.json` | NVDA demo：sejonep 审批 AI 0.90/SEMI 1.00；缺 segment 标低置信(C6)；线上 NVDA 显 SEMI/AI chip |
| **M4.6 ✅ #51** 验证 + 构建 | `feat/theme-pipeline-build` | AC-M4 端到端 + Makefile(themes/theme-index/theme rotation/theme-c9 接线) + 测试 + 浏览器 smoke | `Makefile` `compute/check_theme.py` `themes/*` | AC-M4 全过；PIT 不回溯 + 非市值加权 + theme 多线头测 |

> 顺序：M4.1(membership)→M4.2(index)→M4.3(RS-Ratio)→M4.4(export+web)→M4.6(接线)→M4.5(LLM/human 真实路径)。**主链用 seed/fixture membership 确定性验证**；M4.5 真实路径用 claude CLI（plan 额度）+ EDGAR + human 审批跑通 NVDA。
>
> **真实数据暴露的 2 个数据成熟度 bug（D 轨"把真实风险逼现在"的价值）**：fixture 多 as_of 长历史下全绿，真实 nightly 第一次跑完整 theme 链才暴露——
> 1. **theme 历史不足**（#54）：seed membership 单一近期 as_of → theme index 仅 6 天 → 周线 RS-Ratio 产不出 → check-theme 硬 FAIL 阻断 deploy。修：`seed.py` as_of 回填到 daily_bars 最早日（index 覆盖完整 ~2y）+ `check_theme.py` 三态 PASS/FAIL/SKIP（历史不足时 RS-Ratio/C3 降级 SKIP 不误杀）。
> 2. **approved as_of off-by-one**（#55）：审批 as_of 默认 today（晚于最新 EOD board 一天）→ board PIT 回落 seed chip。修：`review.py` 默认 as_of = 10-K filing 日（PIT 信息可得日）。

### 数据契约（M4.1 schema + M4.4 rotation.json theme 扩展）
```
theme_membership(ticker, theme, exposure DOUBLE[0,1], as_of_date, source['seed'|'llm'|'manual'], approved_by,
                 PRIMARY KEY(ticker, theme, as_of_date));   -- point-in-time；同 ticker-theme 多 as_of = 历史
-- 成员@t = per(ticker,theme) argmax(as_of_date ≤ t) where exposure>0
rotation.json buckets[] 复用 M3.3 契约 + bucket_type='theme'；members 取自 theme_membership PIT
```

### 关键约束（code 不要翻案，详见 PRD §7/§16）
- **point-in-time membership 硬要求(C3)**：as_of_date 维度；index/RS-Ratio/chips 用 as-of t 成员；**改一条 membership 的 as_of 绝不回溯改写历史**(否则 theme 线 / Ocean trail 虚构)。
- **theme index 非市值加权(C4)**：exposure-weighted + cap(防单票主导)；**绝不市值加权**(否则「AI 主题」≈ NVDA 一只)。
- **theme index point-in-time 构建**：每 t 用当时成员当时价复合；**不用今天 membership 回溯历史**(尾迹虚构)。一旦 PIT 构建出真实 index 价序列，RS-Ratio z-score 同 M3.2(point-in-time 关键在 index 构建、非 RS-Ratio 算法)。
- **LLM 不当权威(C6)**：LLM=candidate generator + revenue extractor，human-in-loop 审批、approved_by 必填；EDGAR segment 脏 → 部分/近似抽取 + 低置信标记，别宣称精确。
- **exposure 连续(非二元)**：营收锚定 revenue_share；多对多绝不 MECE。
- **复用 M3 框架**：bucket_bars/bucket_rrg/Rotation theme 模式，不建第 6 surface。

### AC-M4（PRD §14）
≥4 主题有 point-in-time membership(含 exposure + approved_by)；改一条 membership 的 as_of → 历史不被回溯污染(C3)；theme RS-Ratio 线非市值加权(C4)。

### M4 风险与缓解
| 风险 | 缓解 |
|---|---|
| LLM 抽取需 API/EDGAR/human(本环境难自动验证) | seed/fixture membership 确定性验证主链(M4.1–4)；M4.5 框架 + 真实兜底(同 M3 真实 ingest) |
| EDGAR segment 脏/缺(C6) | LLM 部分抽取 + human 审批 + 缺 segment 低置信标记 / 总营收 fallback，不宣称精确 |
| point-in-time 回溯污染(C3) | as_of_date 维度 + index PIT 构建 + 测试(改 as_of → 历史段 byte 不变) |
| theme 市值加权致单票主导(C4) | exposure-weight + cap + 验证(NVDA 在 AI 权重 ≤ cap) |
| theme 成员少(seed 8 theme 各几只) | MVP 用 seed；真实 LLM 扩 candidate → human 审批增量 |
| 营收暴露阈值未定(PRD §17) | M4.1 seed 给 exposure 初值；真实落地后回写校准(不回测优化 alpha) |

## M5 — Valuation screener + Stock detail ★ 详细方案 ⏳ M5.1 进行中（预览 #53 已上线）

**目标**：把预览版（#53，board.json 驱动）升级到 PRD §9.5/§9.6 正式形态——Valuation 走 **duckdb-wasm 查 Parquet** 的全 universe 横截面（+PEG/Mgn%）；Stock 加 **price↔fundamentals 时间轴对齐 stack**（季度营收 bars + 每日 P/S over time，共用 x 轴 + 季度网格）。数据基础 M0 已全在 DuckDB（`valuation_daily` 每日含 peg/margin、`fundamentals_q` 季度营收）——M5 主要是 export 分片 + web 前端。

**前置**：M0 估值 + 预览 #53（前端壳 + 排序/scope/三档色/pctile 逻辑已就位，正式版换数据源 + 加列/格）。**对应模块**：`export/` `web/`。

**决策落地（PRD §17 原未决，2026-06-13 拍板）**：
- **duckdb-wasm 接法**：忠于 PRD §9.5，Valuation 走 duckdb-wasm 查 Parquet（为 M6 扩量铺路）。当前 universe ~510，纯 JSON 也够；选 duckdb-wasm 是产品方向（数千只 + 浏览器 SQL）。
- **Parquet 分片粒度**：Valuation = 单文件 `valuation.parquet`（全 universe 最新横截面，~510 行×16 列，~80KB）；Stock = per-name bundle（每票一文件，按 ticker 懒加载）。
- **filing AI 摘要**：留到 M5 之后（独立大块，复用 M4.5 claude CLI plan 额度 + human 校验范式），不阻塞 M5 主体。

### M5 任务拆解（每个 = 一个 worktree+PR）

| task | 分支建议 | 范围 | 产出文件 | 验收 |
|---|---|---|---|---|
| **M5.1 ⏳** 估值横截面 Parquet 导出 | `feat/m5-1-valuation-parquet` | 全 universe 最新 valuation 横截面（+peg/margin/freshness）→ `valuation.parquet` + `.meta.json`；接 Makefile export | `export/valuation_parquet.py` `Makefile` | parquet 全 universe 行、含 peg/margin 列、freshness 三档；与 board.json 同 valuation_daily（C9）；nightly 产出 |
| **M5.2** Valuation 正式版（duckdb-wasm） | `feat/m5-2-valuation-duckdb-wasm` | 引入 `@duckdb/duckdb-wasm`（Vite worker 集成）→ 浏览器查 `valuation.parquet`；全 universe 表 + PEG/Mgn% 列；复用预览的排序/scope writer/三档色/common-vintage pctile | `web/src/lib/duckdb.ts` `web/src/views/Valuation.tsx` `web/package.json` | 全 universe 行 duckdb-wasm 查询可排序；PEG/Mgn% 列；三档色 + vint；scope filter 改 pctile 分母 |
| **M5.3** Stock per-name bundle 导出 | `feat/m5-3-stock-bundle` | 每票导出价格 OHLCV 历史 + 季度营收序列（`fundamentals_q`）+ 每日 P/S 序列（`valuation_daily.ps`）→ per-name 分片 | `export/stock_bundle.py` `Makefile` | per-name bundle：价格+MA+52wh、季度营收（YoY）、每日 P/S；与 board/valuation 同源（C9） |
| **M5.4** Stock 四格时间轴 stack | `feat/m5-4-stock-stack` | PRICE / VOLUME / REVENUE（季度 bars，YoY 增绿降红）/ P/S over time（每日线），共用 x 轴 + 季度网格线贯穿；懒加载 per-name bundle | `web/src/views/Stock.tsx` `web/src/components/StockStack.tsx` | 四格共用 x 轴、季度网格贯穿；价↑营收平→P/S 扩 直接可视 |
| **M5.5** 验证 + 构建 | `feat/m5-build` | AC-M5 端到端 + manifest 收录 valuation + Makefile/nightly 接线 + C9（valuation↔board）+ 测试 | `export/manifest.py` `export/check_valuation.py` `Makefile` `.github/workflows/nightly.yml` | AC-M5 全过；duckdb-wasm 浏览器排序 + 四格 stack 头测；valuation↔board C9 |

> 顺序：M5.1(数据)→M5.2(Valuation 前端)；M5.3(数据)→M5.4(Stock 前端)；M5.5 收口。M5.1↔M5.2、M5.3↔M5.4 两条独立链可并行。**主链用 fixture 确定性验证**；duckdb-wasm 浏览器端到端在真实/fixture parquet 上 smoke。

### 数据契约
```
valuation.parquet（M5.1）：每 universe 票一行 ×
  ticker,name,sector,mktcap, pe,ps,evs,ev_ebitda,peg,growth,margin,rule40,
  as_of_period_end,as_of_filed,as_of_age_days,freshness('fresh'|'stale'|'overdue'|NULL)
  + valuation.meta.json{as_of_date,count,valuation_coverage}（manifest/header 用）
stock bundle（M5.3，per-name）：price[date,o,h,l,c,adj,vol,ma50,ma150,ma200], high_52w,
  revenue_q[period_end,revenue_ttm,yoy], ps_series[date,ps]
```

### 关键约束（code 不要翻案）
- **C9 同源**：valuation.parquet / stock bundle / board.json 都读同一份 `valuation_daily`+`daily_bars`+`fundamentals_q`；同票跨 surface 数字一致、可追溯。
- **common-vintage percentile（§10.5）**：pctile 仅在 fresh cohort（as-of ≤95d）内排；stale/overdue 显 `vint` 不进分母；scope filter 先于排序与 percentile。
- **Stock per-name 不受 scope（§9.1.2）**；duckdb-wasm 仅 Valuation（wide explore），Stock 走懒加载 bundle（narrow）。

### AC-M5（PRD §14）
Valuation 表 duckdb-wasm 浏览器查询可排序；as-of 三档上色正确；percentile 仅 current-vintage（stale=vint）；Stock stack 四格共用 x 轴、季度网格贯穿。

## M6 — 扩量（纲要）

- **目标**：universe 由 ~500 扩到数千（Stooq bulk 已支撑）。
- **前置**：M0–M5 在 ~500 只上稳定。
- **关键未决**：ingest 批量化/增量化；compute 全列扫描在数千只上的性能；client 数千点渲染（NFR-8）。
- **验收**：PRD §14 AC-M6（扩到 ≥2000 仍满足 AC-M2 性能）。

---

## 全局依赖链

```
M0(数据+引擎)✅ ─┬─> M1(Discovery)✅
                ├─> M2(Ocean)✅ ──> M5(Valuation+Stock)
                ├─> M3(Rotation) ──> M4(主题分类)
                ├─> D(部署+夜间自动化, infra 轨; 建议 M3 后, 与 M4/M5 并行)
                └─────────────────────────────────> M6(扩量, 需 M0–M5 稳定)
```

M0 是所有后续的根。先把 M0 五个 task 跑通，再按 explore(M2)/decide(M3) 两条线推进；**D（部署）是正交 infra 轨，硬 gate 是 D.1 真实 ingest 冒烟，建议 M3 后启动、不阻塞 M4/M5**；M6 收尾扩量。
