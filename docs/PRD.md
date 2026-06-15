# TickerTide — 产品需求文档 (PRD)

| | |
|---|---|
| **状态** | Draft v1.0 · Pre-M0 |
| **权威性** | 本仓库的产品规格 SoT（Single Source of Truth） |
| **来源** | 派生自 `docs/BUILD-PLAN.md`（构建计划 + 数学规格）与 `docs/equity-monitor-v2.jsx`（UX 合同 mock） |
| **读者** | 实现者（人或 AI agent）、reviewer |
| **配套** | UX 视觉契约 `equity-monitor-v2.jsx`；工作流 `docs/workflow/WORKFLOW.md`；数据/文件合同 `docs/runtime/File-Contracts.json` |

> **文档分工（避免重复）：** BUILD-PLAN 是 kickoff prompt 原件与数学推导出处；本 PRD 是结构化、可追溯（FR/NFR 编号）的需求规格；jsx 锁定 UX 的 layout/interaction/hierarchy/color。三者冲突时，以本 PRD §16「已定死」为准。

---

## 0. 目录

§1 概述与范围 · §2 背景与问题陈述 · §3 目标用户与用例 · §4 产品原则（脊柱） · §5 系统架构 · §6 数据源与数据契约 · §7 不可妥协约束 · §8 分类本体 · §9 UX 规格（五个 surface） · §10 数学/信号规格 · §11 功能与非功能需求 · §12 数据模型 · §13 里程碑 · §14 验收标准 · §15 OUT OF SCOPE · §16 已定死 · §17 实现级决策与开放问题 · §18 风险 · §19 内建工作流 · 附录 A 术语 · 附录 B 字段词典 · 附录 C 配色表

---

## 1. 概述与范围

### 1.1 一句话定义

TickerTide 是一个 **盘后(EOD)、美股专属** 的 momentum + valuation 监控工具。

### 1.2 脊柱（产品成立的前提）

**ignition 发现引擎 + valuation + raw evidence，五个 lens，两个尺度，默认静态分发。**
- **ignition（发现引擎，§10.8，项目核心）**：短窗口、测「刚起步的票在加速 / 突破 / 放量」，比 composite 早数月点亮。驱动 Discovery「持续点火」榜 + Ocean 海平面图（§9.2）。
- **valuation（横截面估值，§10.5）**：原始倍数（P/S / EV/S / P/E / EV/EBITDA），驱动 Ocean 横轴 + Valuation screener + Rotation/Stock 估值。
- **composite（§10.6）**：计算层暂存的长窗口确认分，**M8 起退出全部用户可见层**（不再驱动任何 surface、不再露角标）；保留仅为引擎自检/未来可选确认。

旧表述「composite 驱动 Ocean / composite 副读」已废弃（M8）。

两台引擎**共用同一份 per-stock 数据**（C9），离线预计算 + 静态分发。**早期发现 ≠ 趋势确认的旋钮档位**——它们测的是不同的物理量（加速度 / 拐点 vs 水平），故是两台并列引擎而非一个标量的两端（§10.8，实证 `analysis/`）。

### 1.3 SCOPE（不可越界）

- **仅限美股**：US-listed（NYSE / Nasdaq / NYSE American）。ADR 因在美上市可纳入；非美上市标的一律 out。
- 中文 / cross-language 标的判定本期 **不做**（显式 descoped）；主题语义判定只读英文 EDGAR filings。

### 1.4 不解决什么（摘要，详见 §15）

intraday / real-time、auth / 多用户 / 支付、非美标的、backtesting 引擎、Ocean 无控/常驻全量 autoplay（M8 的用户受控 Play/Pause 不在此列）。

---

## 2. 背景与问题陈述

### 2.1 动机

个人投资者想在 **emerging leader 还便宜时** 发现它，而不是等它登上各种榜单后追高。现成工具的失败模式：

- **要么是漂亮地图**（一堆散点/热力图）—— 好看，但不导向「去动手买哪 N 只」。
- **要么是黑箱分数榜**（给一个 0–100 的「评分」）—— 不暴露证据，无法 informed consent，权重被当成事实。
- **要么把相对强度和绝对趋势混为一谈** —— 熊市里「Leading」的标的可能绝对在跌。
- **要么是滞后的确认引擎** —— 等 RS 进前列 / 创新高 / 趋势变干净才点亮（IBD / Minervini 谱系），那时 emerging leader 已经涨完大半（实测：等这类信号点亮，票已涨 +84%~+732%，§10.8）。

### 2.2 本工具的立场

- **evidence-first**：默认露原始证据（涨幅、距高点、量比、估值倍数），composite 只是一个可展开的角标，**永不给 buy / target**。
- **核心是 ignition，composite 退辅助确认**：项目核心技术指标是 ignition（持续点火，§10.8）—— 无可调参（5 分量等权 + persistence/top-decile 阈值离线定死，刻意=**买 robustness/stability，不买 alpha**）。composite 是辅助确认引擎，用**固定权重**（k=0.5，§10.6）；其 5 分量原始值全程可见（角标可展开，informed consent），但**不可拨**——`early⟷reliable` 旋钮已取消（§16/§17）。
- **两个尺度解耦**：用来「逛」的 wide explore 和用来「动手」的 bounded decide 是不同界面，互不取代。
- **相对永远配绝对读**：RS-Ratio 只讲相对，必须与 composite/regime 并置。

---

## 3. 目标用户与核心用例

### 3.1 用户

核心用户：具备量化/技术分析素养、盘后做美股研究与决策的投资者。当前不做 auth / 支付 / 团队协作。

### 3.2 核心用例

| # | 用例 | 尺度 | 主 surface |
|---|---|---|---|
| UC1 | 盘后扫一遍全市场，找「便宜且在转强」的票 | wide/explore | Ocean |
| UC2 | 看哪些 sector/theme 在轮动换手、谁在 leading | bounded/decide | Rotation |
| UC3 | 拿到一份 evidence-first 候选清单，逐张看证据决定动手 | bounded/decide | Discovery |
| UC4 | 按估值倍数横截面筛选（在 sector/theme 内比 percentile） | wide/explore | Valuation |
| UC5 | 钻进单只票，看价格↔基本面时间轴对齐、判断「赚到这波 vs 变贵无基本面」 | narrow | Stock |
| UC6 | 看 ignition 持续点火榜（核心发现引擎），每卡读原始证据（无 composite，M8） | bounded/decide | Discovery + ignition |
| UC7 | 锁定一个 sector/theme scope，所有 wide surface 同步过滤到该范围 | 全局 | scope filter |

---

## 4. 产品原则（脊柱，贯穿所有 surface）

**P1 — 两台引擎共用一份数据，不写五条独立管线。** composite（确认，§10.6）+ ignition（发现，§10.8）共用同一份 per-stock 数据（C9）。
- **Discovery** = ignition「持续点火」排序；**Rotation** = RS-Ratio 按 bucket group-by（league 含 # igniting / # candidates 聚合）；**Ocean** = ignition × valuation 海平面图（§9.2）；**Valuation** = 估值的 cross-section；**Stock** = 单票展开（ignition 点火诊断 + 估值时间轴）。

**P2 — 两个尺度。**
- **wide / explore**：Ocean、Valuation screener —— 数千只，用来逛。
- **bounded / decide**：Discovery（候选）、Rotation（~10–12 桶）—— 用来动手。

**P3 — composite 用固定权重，分量全可见。** composite = `Σ wᵢ·componentᵢ`，权重固定在 `k=0.5`（曲线见 §10.6），不删任何 component、5 分量原始值角标可展开。`early⟷reliable` 旋钮已取消（核心是 ignition、ignition 无可调参；§16/§17）。

**P4 — evidence-first，composite 永不黑箱。** card/surface 默认露原始数字；composite 是可展开角标，点开见 5 分量原始值 + 权重；永不给 buy/target。

**P5 — 数据一致性。** 五个 surface 的所有数字必须从同一份 per-stock 数据派生，同一只票在任何 surface 上对得上、可互相追溯（见 §7-9）。

**P6 — 相对配绝对。** RS-Ratio 只讲相对强度，永远与绝对 regime（composite）并置读。

**P7 — 双引擎互补，ignition 是核心。** composite 答「是否已成型 leader」（守已成、辅助确认），ignition 答「是否刚开始加速」（抓刚起、项目核心）；两者是不同物理量。early 发现的精度靠 persistence（§10.8），不靠旋钮——曾经的 `early⟷reliable` 旋钮（只在 composite 那些**都滞后**的分量间重配权、是假 early）已取消，composite 退为固定权重的辅助确认副读。

---

## 5. 系统架构

### 5.1 范式：离线预计算 + 静态分发（fomo5000）

```
GitHub Actions (nightly cron, post-US-close)
  └─ ingest (Python):  Stooq (bulk EOD) + Nasdaq screener (universe/cap/sector/PE) + SEC EDGAR (fundamentals/segment)
  └─ compute (DuckDB): derived_daily + composite + RS-Ratio 序列 + theme membership + percentiles(common-vintage) + ASOF valuation
  └─ export:           snapshot → Parquet/JSON shards
  └─ deploy:           Cloudflare Pages (static)
Client (canvas + duckdb-wasm): renders Ocean (thousands of points) + boards; screener queries Parquet shards in-browser
(optional) private Streamlit cockpit for server-side interactive work
```

### 5.2 关键架构决策

- **默认无常驻 server、无托管 DB、不向 client 暴露任何 key。** GitHub Actions = cron。与 SCOPE 的零后端 spine 一致。
- **DuckDB 选型理由**：列存 OLAP（rolling window / 聚合 / 横截面 percentile 是全列扫描型 workload）+ 嵌入式（single-writer、offline batch，不需要 Postgres 的 client-server/MVCC/并发写）+ 原生 `ASOF JOIN` / `QUALIFY` / `PIVOT` + 整库单文件可移植 + duckdb-wasm 可在浏览器查 Parquet。
- **演进边界**：若以后变多用户事务型 app 才考虑 Postgres —— 那是另一个 ontology，不在本期。
- **Web 技术栈（已定，2026-06）**：客户端用 **React + Vite + TypeScript**（视觉效果优先 + 与 UX 合同 `equity-monitor-v2.jsx` 同源，迁移直接）；视图用 SVG/DOM 组件，Ocean 用 canvas。
- **零后端放宽（已定，2026-06）**：原「零常驻后端」从硬约束降为**默认**——M0–M1 仍是静态构建 + nightly 导出的 JSON（无常驻 server）；视觉/功能需要时可引入后端，不为零后端洁癖牺牲视觉。

### 5.3 模块映射（仓库目录 = 架构层）

`ingest/` → `compute/` → `export/` → `web/`；`themes/` 横切（membership）。各模块 README 描述职责与未来文件；工作流工具在 `engine/ scripts/ gate/`。

---

## 6. 数据源与数据契约

### 6.1 数据源（免费、支持每日更新、US-only）

| source | 用途 | 备注 |
|---|---|---|
| **Stooq** | bulk EOD OHLCV（价格主干） | CSV 批量，**无 per-symbol 限速** → 数千只的最佳免费源；校验覆盖、补缺口 |
| **Nasdaq screener** (`api.nasdaq.com/api/screener/stocks`) | universe + market cap + GICS-ish sector/industry + trailing P/E + last sale | 一次拿全美股清单；半官方 |
| **SEC EDGAR** (`data.sec.gov` companyfacts / submissions) | revenue / shares / debt / cash / **segment** → P/S, EV/S, Rule-of-40，以及主题营收锚定 | 官方权威；需 descriptive `User-Agent` header，~10 req/s |
| **(opt) Tiingo** | 干净补缺 | 便宜付费；yfinance 仅作 fallback（非官方、ToS 灰、会断） |

### 6.2 数据契约约束

- **US-only 过滤**：Nasdaq screener 限 NYSE/Nasdaq/AMEX；EDGAR 天然是 US filers。
- **Licensing**：任何公开展示、再分发或商业化前必须复核：Stooq/EDGAR 条款最友好；其余多数禁止 redistribute，需 display license。
- **IEX Cloud 已退役（2024-08），勿用。**

---

## 7. 不可妥协约束（informed consent，非偏好）

> 这些是设计前提，违反任何一条会让产品在认知或数据完整性上失效。编号供 FR/验收追溯。

- **C1 — 数千只放 Ocean(explore) 可以；DECISION 必须 bounded。** 别让漂亮地图取代去 act 那 N 只。
- **C2 — pin/标签必须 selective（仅 pinned）；Ocean 默认静止在 latest EOD。** 认知带宽硬约束。M8 起允许**用户受控**的 Play/Pause 时间动画（相邻真实 EOD 间视觉插值、到最新日自停、拖 slider 即暂停）；仍**禁止**无控、常驻、自启的全量 autoplay。
- **C3 — point-in-time membership 是硬要求。** membership 一改会回溯改写历史 → 否则 Ocean trail 和 RS-Ratio 线是虚构的。
- **C4 — 主题指数别纯 cap-weight**（否则「AI 主题」≈ NVDA 一只）→ equal/capped-weight；轮动视图 ~10–12 桶封顶。
- **C5 — RS-Ratio 只讲相对**：熊市能「Leading」却绝对在跌 → 永远配绝对 regime（composite）一起读。
- **C6 — EDGAR segment 很脏**：大量公司不单列主题营收线 → LLM 抽取必然部分/近似，human-in-loop，别宣称精确。
- **C7 — 估值是 trailing 滞后近似**（财务季度更新），界面别假装日频精确。
- **C8 — scope filter 必须全程可见 + 一键清除**（dismissable chip，如 `Scope: Industrials ✕`）；禁止隐式 filtered 状态。
- **C9 — 所有 surface 来自单一 per-stock 引擎。** Ocean 的 `(ign_pct, ps)` 位置、Stock 的价格/财务、Discovery 卡、Valuation 行必须从同一份底层 per-stock 数据（`derived_daily` / `valuation_daily` / `daily_bars` / `universe`）派生，可互相追溯（前端永不重算引擎）。（mock 现状是两套独立合成系统对不上；真实管线禁止此分裂。）
- **C10 — Ocean 必须 respect global scope。** scope = sector/theme 时，Ocean 把非 scope 点 filter 掉或大幅变淡；框选/点击写同一个 scope。

---

## 8. 分类本体（标准底 + 营收锚定的语义主题）

**Ontology：** 一只票没有内在板块，桶是提问 lens 的函数 → 数据模型 **ticker↔(sector, theme) many-to-many + 连续 exposure 权重 + point-in-time**。

### 8.1 标准底（GICS-ish）

直接用 Nasdaq screener 的 sector/industry。标准板块轮动用 **11 SPDR Select Sector ETF 对 SPY** 的 RS-Ratio（XLK/XLF/XLE/XLV/XLY/XLP/XLI/XLB/XLU/XLRE/XLC）→ 零分类管线。

### 8.2 概念主题（人工提需求，多对多，绝不强加 MECE）

本期清单：**AI、智能机器人(Robotics)、太空算力(Space Compute)、光模块(Optical)**，加 半导体(Semis) / 核能(Nuclear) / 网安(Cybersecurity) / 云(Cloud)。NVDA 同时进 AI 和 Semis 是 feature 不是 bug。

### 8.3 新概念成员判定 = 语义 + 营收锚定（核心方法）

1. LLM 读 **EDGAR 10-K/10-Q 的 business + segment** 段（英文）。
2. 抽取该主题的**营收暴露** → `membership.exposure = revenue_share`（连续，不是二元）。把 fuzzy 主题钉在近似可证伪的数字上。
3. **human-in-loop 审批**；LLM 当 candidate generator + revenue extractor，**不当权威 classifier**。
4. **point-in-time**：`t` 时刻的 membership 只反映 as-of `t` 已披露的信息。

---

## 9. UX 规格（五个 surface）

> 视觉契约 = `docs/equity-monitor-v2.jsx`。本节锁定 layout / interaction / hierarchy / color；数据/算法以 §10 为准。配色见附录 C。**code 不要照抄 jsx 的造数逻辑（合成数据）。**

### 9.0 全局框架与导航

- **布局**：固定顶部控制栏 + 中央内容面板。**暗色唯一方案**（`--bg #080b11`）。
- **五个 tab**（胶囊按钮，选中高亮绿 `#2ec07a`）：`Ocean` · `Discovery` · `Rotation` · `Valuation` · `Stock`。单击即切。
- **顶部控制栏两部分**：tab 组 · scope 过滤条（仅 scope≠all 时出现）。（曾经的 early⟷reliable 旋钮已取消——核心是 ignition、ignition 无可调参；旁附一行引擎说明「IGNITION = 发现核心引擎（无可调参） · composite = 确认副读（固定权重）」。）
- **字体**：显示用 `Saira Semi Condensed`；数据用 `IBM Plex Mono`。

### 9.1 全局原语

**9.1.1 composite = 固定权重的确认副读（无旋钮）**
- 曾经的 `early⟷reliable` 旋钮已**取消**：它只在 composite 那些都滞后的分量间重配权（假 early，§10.8/§16），而项目核心已转为 ignition——ignition 无可调参（刻意，买 robustness 不买 alpha），故全局没有可拨旋钮。
- composite 用**固定权重**（`k=0.5`，曲线见 §10.6），引擎离线算好（compute/run.py 默认 `--k 0.5`），前端**不重算**、直接读导出值（C9）。
- composite 仍是**可展开角标**（informed consent）：点开见 5 个 component（RS / 52WH / Trend / Vol / Accel）的原始值 + 各自固定权重 %（高度=原始值），永不黑箱（P4）。不再「可拨」，只「可看」。

**9.1.2 global scope filter（C8、C10）**
- 状态 = `{ all | sector:X | theme:Y | pinned }`，**单一真源**。
- UI：scope≠all 时显示 chip `Scope: ● <名称> ✕`，副标 `filtering Discovery · Valuation · Rotation · Ocean`。
- **写入口**（都写同一个 scope，后写覆盖）：Rotation 点表行/线、Valuation 下拉、Ocean 框选/点击。
- **sticky**：切 tab 不 reset；只有显式换或点 `✕` 才清。
- **respond**：Discovery / Valuation / Rotation / Ocean；**Stock 是 per-name，不受 scope 影响**。
- **解耦**：「改 scope」与「换 view」是两个独立动作（点 sector 只 set scope + 原地展开 panel，不 auto-jump）。

**9.1.3 evidence-card = Stock 的 collapsed 态（一个对象，两种渲染密度）**
- **collapsed = evidence-card**（扫描态：密、多、浅）：price+volume+MA mini 图 + 6 个**原始数字**（摊开，非 percentile）+ 头部 ignition 状态（🔥 持续点火 / ign_pct）+ 点火证据条 + AI「why moving」占位格。**无 composite 角标（M8 退出用户可见层）。**
- **expanded = Stock**（详情态：全、单、深）：§9.6 完整视图。
- 点任意 card → 展开成 Stock。**不要把两者当两个东西做。**
- card 字段 = **6 个原始数字**：原始涨幅 1M / 3M / 6M、距 52w high %、突破后第几周、量/均量 `×`、（外加 market cap 在头部）。密度 = 一屏 3–4 张大卡（2 列网格）。

### 9.2 Ocean（canvas，wide explore）—— Ignition × Valuation 海平面图（M8 重构）

> **M8 重构（2026-06-15）**：Ocean 从旧的「RS percentile × Valuation percentile 周度散点」改为 **Ignition × Valuation 的 daily 海平面图**。理由：核心已转 ignition（§10.8），Ocean 作为 wide/explore 入口应直接呈现「谁正在点火、贵不贵」；composite 退出全部用户可见层（仅计算层暂存）。旧 RS×Val 设计见 ROADMAP「M2」段（history）。

- **渲染**：一个 EOD daily cross-section，数千只股票的 canvas 散点。
- **轴固定**：
  - **y = ign_pct**（点火横截面百分位 0–100，§10.8）。一条固定**海平面 = ign_pct 90**（top decile）。海平面**以上 = 点亮**（正在快速上涨 / 加速 / 突破 / 放量），跃出高度 ∝ `ign_pct − 90`；海平面以上区域轻微高亮、以下压暗。
  - **x = 原始 trailing P/S TTM**（`ps`），**log 轴**。**不用 valuation percentile 做默认横轴**，不引入估值综合分或隐含阈值参数（§16）。`x_domain` 由导出窗口内所有有效 P/S 自动算出，供 log scale。
- **candidate 语义**：海平面以上且 `ign_persist_days ≥ 5`（= `ign_pct ≥ 90 AND persist ≥ 5`）= Discovery 的「持续点火」候选 —— Ocean 海平面以上点与 Discovery candidate **同一总体、逐票可追溯**（C9）。
- **color**（两模式可切）：sector / theme（选定主题：成员正常、非成员极淡）。candidate 点加光晕 + 亮环；海平面以上点 solid bright、以下更暗。
- **size** = market cap（半径随 sqrt(mktcap)，clamp 1.6–11px）。
- **时间轴（日期滑杆 + 播放）**：图下方日期 slider 在不同 EOD 之间切换，**默认打开 latest EOD**。Play/Pause + prev/next；**Play 自动播放**时每支股票的点在**相邻真实 EOD 快照之间用视觉插值平滑移动**（rAF，每两日 ~900–1200ms，到最新日自动停）。**插值仅用于视觉动画，不伪造中间交易日数据**：tooltip 与状态恒取真实 snapshot。拖动 slider 暂停播放并切到对应日期（phase 归零）。
- **交互**：
  - hover → nearest-neighbor 显示 tip（ticker / sector / ign_pct / 持续点火天数 + candidate / P/S / EV/S / P/E / EV/EBITDA / 10d·1m return / volume surge / valuation freshness / mktcap / themes）。hover 命中用**当前绘制后的插值位置**。其中 ign_pct / 持续点火 candidate / P/S 三个绘制字段来自 bulk 即时可见，其余 9 个证据字段按票**懒加载**（见下「payload」，首次 hover 显骨架 `…`）。
  - click → toggle **pin**（pinned 点高亮 + 标签，仅 ≤ cap 时标 ticker，C2）。
  - 框选（lasso）→ **set 全局 scope**（Ocean 是 scope 的第一个写入口，C10）。
- **respect scope**（C10）：非 scope 点 filter 掉或大幅变淡（in-scope ~0.5–0.92 按是否点亮，out ~0.06）。
- **已砍**：旧 RS×Val 轴、(50,50) 十字线、quadrant 配色、周度 WEEK scrubber、pinned 多周 trail/箭头（时间维度由播放动画承担）；更早砍掉的 RRG-axes（`rsr`/`rsm` 字段早已删除）。
- **payload（schema v3，体积裁剪 / 为 M6 扩量铺路）**：每帧绘制只需 3 个字段（`ps` / `ign_pct` / `candidate`），其余 9 个仅 tooltip 字段实测占压缩体积 ~79%。故 `ocean.json` 拆两层：**bulk**（`ocean.json`，每票仅三绘制字段的 columnar 数组、与 `dates[]` 同索引、全员前置下载）+ **per-stock detail**（`ocean/<TICKER>.json`，9 个 tooltip 字段 columnar、hover 时按票懒加载——只下你真去看的票）。实测 top-500 bulk brotli ≈ **100KB**（旧 v2 整合 596KB → −83%）。**勘误**：旧文写的「ocean gzip ~1.5MB」是 **board.json** 的数；ocean v2 实测 gzip 866KB / brotli 596KB。M6 全量后 bulk 仍只随票数 ×3 字段增长、detail 永远按需，故可扛数千只。两文件 columnar 且按 `dates[]` 同索引对齐、全字段 C9 同源（`derived_daily` / `valuation_daily` / `daily_bars` / `universe`）；`make ocean-c9` 额外校验 bulk↔detail 一致（bulk `cand` == ign_pct≥90 AND detail.persist≥5、detail.evs 追溯 board）。**M8 行为不变**：海平面图 / 轴 / candidate gate / 插值动画完全一致，仅首次 hover 某票多一次取数（tooltip 先显 3 个已知字段 + 骨架）。

### 9.3 Discovery（evidence-first 卡流，bounded decide）

- **渲染**：2 列 evidence-card 网格，**按 ignition「持续点火」排序**（§10.8）—— **不是 composite 排序**（composite 是滞后 14–45 周的确认分，M8 起退出用户可见层）。卡片为 evidence-first（原始数字 + 点火证据），**不显示 composite 角标**。
- **候选池 = 三级漏斗前两级**（§10.8）：① ignition 跨入横截面 top decile（触发，recall）→ ② persistence 连续 ~5 日仍在（去假突破，把 forward LIFT 从 ≈0 提到正，实证 `analysis/precision_ignition.py`）→ 上榜；③ 用户翻财报 = 终筛（human，§10.8）。bound = 「持续点火」名单而非硬 top-20；漏斗阈值（top-decile / persistence ~5 日）离线定死、无旋钮可调（ignition 是核心、无可调参）。
- **点火证据**：卡片头部突出 ignition 触发理由（突破日 / 放量 × / 10d–50d 步速比 / 是否刚收复 MA50），衔接「为什么现在值得看」→ 接 Stock 翻财报。
- **每张卡** = §9.1.3 evidence-card：
  - 头部：ticker + `(sector · $XXB mktcap)` + ignition 状态（🔥 持续点火 + 天数 / 否则 ign_pct 角标）。
  - theme tags（若有）。
  - MiniChart：90 日 K 线 + MA50/150/200 + 成交量 + 52w 高虚线。
  - 6 字段行：1M / 3M / 6M / from-high / weeks-since-breakout / vol×（涨绿跌红，量≥1.5× 绿）。
  - 「why moving」AI 占位格。
- **交互**：点卡任意处 → 打开 Stock。（无 composite 展开面板，M8。）
- **respect scope**：先 filter 再排序。

### 9.4 Rotation（narrow decide）

- **总览（scope=all）**：
  - **所有 sector/theme 的 RS-Ratio 多线图（非散点）**：height=level（>100 跑赢 SPY）、slope=momentum（走平=中性）、线交叉=leadership 换手。基线 y=100。hover 高亮一条、其余变淡；右缘按末值排序贴标签防重叠。
  - **enriched league 表**（按 RS-Ratio level 排序）：`# | bucket | RS-Ratio | Δ4w(=斜率/momentum) | state`，外加 breadth(%>MA50 / %>MA200)、#at-52w-high、member composite 中位数、agg EV/S、多 horizon relative return。state 由 level+slope 推回四态：**LEADING**(≥100,↑) / **WEAKENING**(≥100,↓) / **IMPROVING**(<100,↑) / **LAGGING**(<100,↓)。
  - **GICS ↔ Theme 切换**。
- **钻进（点表行/线 → set scope + 钻进该 bucket，inline drawer 非新 tab）**：
  - **N=1 单线放大**：单 bucket 的 RS-Ratio 折线，**线色=斜率**（升绿/降红，N=1 时 color 空出来给斜率）。
  - **sector 聚合 summary**（唯一真正新内容，filter 得不到）：breadth、dispersion、aggregate valuation、#at-52w-high、sector RS trail。
  - **成员预览**：Discovery 同款 evidence-card（top-N），每张 → Stock；按钮「在 Ocean / Valuation / Discovery 看全部成员」= set scope + 跳转。
- **已砍**：RRG 散点（唯一强项「同屏比 N 个斜率」由各线自身斜率 + league 表 Δ 列补回）。RS-Momentum 归一量整个砍掉（momentum = RS-Ratio 的斜率）。
- **IA 原则**：bucket→members 是 scope 收窄，不是新 surface；不建第 6 个 sector-detail surface（DRY/Occam）。

### 9.5 Valuation（screener，wide explore）

- **渲染**：横截面表（可滚动），duckdb-wasm 在浏览器查 Parquet。
- **列**：`Ticker | Sector | As-of | P/E | P/S | EV/S | EV/EBITDA | PEG | Grw% | Mgn% | R40 | pctile`。
- **排序**：下拉选指标（P/S 默认）；PS/EV 型升序（便宜在上），Rule40/Growth 降序。
- **scope 过滤下拉** = scope 的 UI（ALL | 各 sector | ◆各 theme）。
- **As-of 新鲜度分档上色**（C7、§10.5）：● 绿(≤95d 已报当期 fresh) / 黄(≤160d 落后一季) / 红(>160d，行变暗 opacity 0.6)。行左边界同色。
- **percentile = common-vintage**（§10.5）：只在 current-vintage cohort（as-of ≤~95d）内排名；stale 行显示 `vint`（不进排名）。
- **respect scope**：先 filter 再排序、再算 percentile（scope 改变 percentile 分母）。

### 9.6 Stock（narrow，evidence-card 的 expanded 态）

- **核心 = 时间轴对齐的 price↔fundamentals stack**（共用同一 x 轴，季度网格线贯穿）：
  1. **PRICE**：日 K 线 + MA50/150/200 + 52w 高虚线。
  2. **VOLUME**：日成交量柱（涨绿跌红）。
  3. **REVENUE**：季度营收 bars（YoY 增绿降红）。
  4. **P/S over time**：每日 P/S 线（= mktcap / TTM revenue）。
  - 直接可视化：价↑营收平 = P/S 扩 = **变贵无基本面**；价↑营收↑ = **赚到这波**。
- **下接**：6 个估值指标卡（P/S · EV/S · EV/EBITDA · P/E · Rev growth · Rule of 40）+ ignition 点火诊断（5 原始分量 + 点火证据 + persistence 时间线）+ theme memberships(+exposure) + 最新 filing AI 摘要。**无 composite 5 分量序列（M8）。**
- **头部**：ticker + `sector · $XXB` + theme chips（带 exposure %）+ **IGN PCT 大分数**（发现核心；candidate 时绿）。
- **入口**：card 点开落地 / 顶部下拉按 ticker 直接查（per-name，**不受 scope 影响**）。

### 9.7 配色与视觉语言

见附录 C。核心：绿 `#2ec07a`(正向/leading) · 红 `#ff5d57`(负向/lagging) · 琥珀 `#e0a02e`(weakening/中性偏弱) · 蓝 `#5197ff`(improving/MA50/weight bar)。象限、11 sector、8 theme 各有固定色；composite 分数 ≥62 绿 / ≥47 琥珀 / else 暗灰。

---

## 10. 数学 / 信号规格

> 诚实定调：以下大多**买 robustness/stability，不买 alpha**。EWMAC 是 80/20；KER/t-stat 值得加；Kalman 锦上添花，别当成提升收益的关键路径。

### 10.1 趋势 / return —— vol-normalized EWMAC

- `forecast = (EMA_fast − EMA_slow) / σ`，σ = price-change 的 EWMA 标准差。无窗口跌落跳变、频域干净一阶低通、自比例。
- 多 horizon：混几对 fast/slow（对应原 63/126；**不跳近期**，目标是 emerging leader 要早）。
- Minervini Trend Template 处保留 SMA（`close>MA50>MA150>MA200`、`MA200` slope≥1mo via `MA200[t]>MA200[t−21]`、距 `low_252d`≥+30%），与 EWMAC 并算两套。

### 10.2 RS percentile

- `rs_raw = (ret_63 − SPX_63) + (ret_126 − SPX_126)`（相对 SPY / `^GSPC`）。
- **每个交易日做 cross-sectional percentile**（池内横截面，非跨时间）。这是 IBD RS Rating 思路。

### 10.3 趋势质量

- KER：`ER = |P_t − P_{t−n}| / Σ|P_i − P_{i−1}|` ∈[0,1]；或 log-price OLS 的 slope t-stat（`slope/resid_σ`）。

### 10.4 RS-Ratio / Rotation 算法（RS-Ratio = 相对强度 level）

对 security S（sector ETF 或 theme index）与 benchmark B（SPY），weekly 为主：
- **RS line（price relative，≠ RSI ≠ IBD RS Rating）**：`RS = 100 × P_S / P_B`，上升=跑赢。
- **RS-Ratio（JdK RS-Ratio = level）**：`M = EMA(RS, n1)`；`RS-Ratio = 100 + k·(M − SMA(M, n2))/σ(M, n2)`（z-score recenter 到 100）。>100 = 跑赢自身近期趋势。
- **momentum = RS-Ratio 的斜率**（一阶导）。**RS-Momentum 归一量整个砍掉**；N=1 单线按短窗平滑斜率着色（升=转强、降=转弱）。
- **plot 决策**：总览 = 所有 bucket 的 RS-Ratio 叠一张多线图（非散点）；N=1 = 单线放大。state 由 level+slope 推回四态（§9.4）。
- **专有警告**：de Kempenaer 确切常数未公开 → 上式是**透明 reconstruction**，定性一致、可审计，**别声称复刻 StockCharts 数值**。
- **z-score 基准**：固定 11 GICS sector 用 temporal（对自身历史）；theme 成分会变 → **point-in-time**，否则尾迹虚构。

### 10.5 估值对齐 —— ASOF JOIN + common-vintage

- **统一规则**：所有倍数 = price（或 mktcap/EV）÷ **过往 4 个季度的对应财务指标**，逐日计算（分母按季 ASOF 阶进、分子日频）。方法就是「价 ÷ trailing-4Q」，**不引入任何 analyst estimate**（forward 不做）。统一套用 P/E（净利）、P/S（营收）、EV/EBITDA 等。默认 diluted GAAP 归母，**point-in-time**（用 as-of-date 实报、不用 restated，防 lookahead）；`E≤0 → n.m.`，回退 P/S/EV/S。
- `EV = mktcap + total_debt − cash`。
- P/S 看 **level + expansion（相对起点/行业中位）+ percentile**，别只看 level。
- **跨行业比较**优先 EV/EBIT（P/E 受杠杆扭曲）。横截面约束 = 方法一致（全票同算法）。
- **as-of 同步（数据完整性）**：横截面每个倍数用该票**最新可得** trailing-4Q（永不取未来季 = anti-lookahead），但各票窗口截止日不同（财报时滞 10-Q ~40/45 天、10-K ~60/75/90 天 + off-calendar 财年）→ **必须暴露 as-of 日并分档上色**（§9.5）：fresh / stale / n.m.。新鲜度按「最新季末距今天数」定义（>~95 天 = 落后一季 = flag）。
- **横截面 percentile = common-vintage**：percentile 是相对统计，只有同 vintage 才有效。**绝对 multiple** 用最新可得（fresh，显示+标记）；**percentile/排名**用「该 peer 集 ≥X%(如 50%)已报出的最近季末」为共同基准，覆盖率没过线则基准停在上一季 → **孤单先发报者不移动基准**。绝不拿先发者的新季数去排别人的旧季数。

### 10.6 composite

- `score = 100 · Σ wᵢ · componentᵢ`，components ∈[0,1]：
  - `rs_pct`、`high_proximity = close/rolling_max(close,252)`、`trend_quality`、`volume`（`SMA(vol,50)/SMA(vol,200)` 抬升 **AND** up-vol>down-vol；另加快脉冲 `today_vol>1.5×SMA(vol,50)`）、`rs_accel`（`rs_pct[t]−rs_pct[t−21]`）。
- **固定权重（无旋钮）**：曾经的 `early⟷reliable` 旋钮 `k` 已取消（核心是 ignition、ignition 无可调参；§16/§17）。composite 用**固定 `k=0.5`** 的权重曲线（compute/run.py 默认 `--k 0.5`，export/board.py 同）：`rs=.20+.03k, high=.34−.24k, trend=.22−.10k, vol=.14−.04k, accel=.10+.35k`（斜率和为 0、Σ=1 全 k），代入 k=0.5 → `rs=.215, high=.22, trend=.17, vol=.12, accel=.275`。前端不重算、直接读引擎导出的 composite（C9）；这条固定曲线只用来在角标里显每分量权重 %。

### 10.7 (optional) Kalman level+slope

要日间稳定 / 无丑跳变时再上：`rs≈level`，`rs_accel≈slope` 变化，`slope/√var` 做 z-score。**不是关键路径。**

### 10.8 ignition 引擎（早期发现，与 composite 并列的第二台引擎）

> **为什么是第二台引擎、且旋钮已取消（已定，实证支撑）：** composite（§10.6）是趋势**确认**引擎——5 分量全是长窗口 / 测水平（rs 63/126、high 252、trend KER63、vol 50/200），数学上系统性滞后于「早期」。曾经的 `early⟷reliable` 旋钮只在这些**都滞后**的分量间重配权、从不引入短窗口信号，故 k=1「early」仍滞后——这就是最初诊断出的「假 early」。早期发现与趋势确认测的是**不同的物理量**（加速度 / 拐点 vs 水平），不是一个标量的两端 → 必须是并列的第二台引擎。**结论（本次定调）**：ignition 升为项目**核心**技术指标（无可调参）、composite 退为**辅助确认**（固定 k=0.5），那个假 early 旋钮**取消**（§16/§17）。

**10.8.1 ignition 的 5 个短窗口分量**（每个先 per-stock 计算，再每日做横截面 percentile-rank 到 [0,1]，等权平均）：
1. **动量加速** `accel = ret_10/10 − ret_50/50` —— 短窗步速超过中窗步速 = 斜率在**变陡**（不是已经高）。
2. **波动收缩→扩张** `expand = mean(|Δp|,10) / mean(|Δp|,60)` —— 起涨前低波动 base、突破时区间放大。
3. **成交量异动** `vsurge = mean(vol,5) / mean(vol,60)` —— 短窗、对自身近月基线（**非** 50/200 慢量比）。
4. **突破 / 收复** `breakout = clamp(close/max(close,60),0,1) · 1[close>MA50]` —— 逼近 / 突破 60 日高 + 站上 MA50（从底部抬升，**非**逼近 52w 高）。
5. **RS 拐点** `rsturn = slope₁₀(P/P_spx) − slope₃₀(P/P_spx)/3` —— 相对强度线短期斜率由负转正 / 加速（**拐点**，非 RS 已在高位）。

`ignition = 100 · mean(percentile_rankₜ(各分量))`；每日再横截面 percentile → `ign_pct`。

**10.8.2 点亮 + persistence（精度的关键，实证支撑）：** 「点火事件」= `ign_pct` 跨入 top decile（≥90）。**但瞬时点火无精度**——precision pass（`analysis/precision_ignition.py`，中性 800 只 Nasdaq habitat 池）实测瞬时点火的 forward LIFT ≈ 0（不胜过随机入场）；提高强度阈值（top 1%）无效甚至更差；**唯 persistence（跨入后连续 ~5 个交易日仍在 top decile）把 60–120 日中位 LIFT 转正 +2.5~3.1pp**，命中率亦升。机理：真突破赖在强势区、假突破速熄。persistence 仅延迟 ~5 天，**仍远早于 composite 的 14–45 周**。

**10.8.3 三级漏斗（ignition 的产品形态，已定）：**
1. **ignition 触发**（recall，早）→ 跨入 top decile。
2. **persistence 确认**（precision，去假突破）→ 连续 ~5 日仍在 → 上 Discovery「持续点火」榜（§9.3）。
3. **基本面终筛**（human）→ 用户在 Stock 翻财报做业务 / 财务，消化剩余噪音。

> **诚实定调（同 §10「买 robustness 不买 alpha」）：** lift 温和（非暴利）；persistence 是**结构性去噪、不是调参买 alpha**。实证 caveat：yfinance 仅含现存票 → 幸存者偏差；2023–26 是 AI 牛市 → base 偏高；但 **LIFT = event − base，对两者相对稳健**。`composite` 不废——它是「已成型 leader」视角，与 ignition「刚起步」互补（一个守已成、一个抓刚起）。实证脚本：`analysis/verify_ignition.py`（timing）+ `analysis/precision_ignition.py`（precision）。

---

## 11. 功能需求 (FR) 与非功能需求 (NFR)

### 11.1 功能需求

| ID | 需求 | 关联 |
|---|---|---|
| FR-1 | 每日(EOD)从 Stooq/Nasdaq/EDGAR 拉取并落地 US-only universe 的价格、universe、基本面、segment | §6 |
| FR-2 | 由单一 per-stock 引擎计算 composite（5 分量）+ derived_daily | §10.6, C9 |
| FR-3 | 每日 cross-sectional RS percentile + rs_accel | §10.2 |
| FR-4 | ASOF 对齐的日频估值倍数（P/E·P/S·EV/S·EV/EBITDA·PEG·Rule40），E≤0→n.m. | §10.5 |
| FR-5 | common-vintage 横截面 percentile，stale 不进排名 | §10.5 |
| FR-6 | sector(11 SPDR) + theme 的 RS-Ratio 周序列 | §10.4 |
| FR-7 | theme membership：LLM 营收锚定 + human-in-loop + point-in-time | §8.3, C3, C6 |
| FR-8 | Ocean：canvas 散点、固定 ignition×P/S(log) 海平面轴、日期滑杆 + 受控 Play 插值动画、pin/lasso→scope、respect scope | §9.2 |
| FR-9 | Discovery：evidence-first 卡流、composite 可展开角标、AI 兜底候选 | §9.3 |
| FR-10 | Rotation：RS-Ratio 多线 + enriched league 表 + GICS/Theme 切换 + 钻进 | §9.4 |
| FR-11 | Valuation：横截面 screener、duckdb-wasm 查询、as-of 上色、scope 过滤 | §9.5 |
| FR-12 | Stock：price↔fundamentals 时间轴对齐 stack + 估值/分量/membership | §9.6 |
| FR-13 | composite 用固定权重（k=0.5）的确认副读，前端读引擎导出值、不重算、无旋钮（early⟷reliable 已取消） | §9.1.1, §10.6, §16 |
| FR-14 | global scope filter：单一真源、跨 tab 粘滞、可见可一键清、4 surface respond | §9.1.2, C8, C10 |
| FR-15 | evidence-card collapsed ↔ Stock expanded 同一对象两态 | §9.1.3 |
| FR-16 | export：snapshot → Parquet/JSON 分片，不含任何 key | §5, C9 |
| FR-17 | ignition 发现引擎：5 短窗口分量 → 横截面 top-decile + persistence；Discovery 改「持续点火」排序 + 点火诊断卡 | §10.8, §9.3 |

### 11.2 非功能需求

| ID | 需求 |
|---|---|
| NFR-1 | **默认静态分发**：M0–M1 无常驻 server / 托管 DB、client 不暴露 key；零后端非硬约束，视觉/功能需要可引入（§5.2） |
| NFR-2 | **数据一致性**：同一票在所有 surface 数字可互相追溯（C9） |
| NFR-3 | **认知带宽**：DECISION bounded、标签仅 pinned、autoplay 仅用户受控（C1/C2） |
| NFR-4 | **可复现**：纯 trailing、point-in-time、anti-lookahead；无 forward estimate（§10.5） |
| NFR-5 | **可审计**：composite 永不黑箱，分量+权重可见（P4） |
| NFR-6 | **US-only**：非美标的不进 universe（§1.3） |
| NFR-7 | **Licensing 合规**：公开展示 / 再分发 / 商业化前复核数据源条款（§6.2） |
| NFR-8 | **Ocean 性能**：数千点 canvas 流畅 scrub / hover / pin（§9.2） |

---

## 12. 数据模型（DuckDB schema，起点可演进）

```sql
universe(ticker PK, name, exchange, sector, industry, mktcap, is_active, first_seen, last_seen);
daily_bars(ticker, date, open, high, low, close, adj_close, volume, PRIMARY KEY(ticker,date));
fundamentals_q(ticker, period_end, filed_date, revenue_ttm, shares, total_debt, cash, ebitda_ttm, eps_ttm);
segment_revenue(ticker, period_end, segment, revenue);            -- from EDGAR, dirty
theme_membership(ticker, theme, exposure, as_of_date, source, approved_by);  -- many-to-many, point-in-time
derived_daily(ticker, date, ret_63, ret_126, rs_pct, rs_accel, high_prox,
              ma50, ma150, ma200, trend_quality, vol_ratio, ud_vol_ratio,
              ewmac_fast, ewmac_slow, composite, rank_in_universe,
              ig_accel, ig_expand, ig_vsurge, ig_breakout, ig_rsturn,  -- ignition 5 分量（§10.8）
              ignition, ign_pct, ign_persist_days);                    -- ignition 分 + 横截面 pct + 已持续天数
valuation_daily(ticker, date, pe, ps, evs, ev_ebitda, peg, growth, margin, rule40);  -- ASOF-aligned
bucket_rrg(bucket_type, bucket, date, rs_ratio, rs_mom);          -- sectors + themes
spx_daily(date, close);
```

- 估值对齐核心：`valuation_daily` 由 `daily_bars ASOF JOIN fundamentals_q ON ticker AND date>=period_end` 生成。
- export：把 `derived_daily` + `valuation_daily` 最新快照 + `bucket_rrg` 拆成 Parquet/JSON 分片给 client。

---

## 13. 里程碑与构建顺序

| M | 目标 | 主要模块 | 验收（见 §14） |
|---|---|---|---|
| **M0** | 数据 + 引擎（先窄）：Stooq+Nasdaq+EDGAR ingest → DuckDB → 对 ~500 只(S&P 500 + 人工种子)算 composite + valuation | ingest, compute | AC-M0 |
| **M1** | Web 客户端起步 + Discovery board：React 证据卡流 + composite 排序 + d/d（M1 期建过 early⟷reliable 旋钮，M7 后取消——核心转 ignition、composite 退固定权重确认；email digest 已移出，见 §15） | export, web | AC-M1 |
| **M2** | Ocean v1（已被 M8 取代）：canvas + 周 scrubber + pin→trail，轴固定 valuation×RS | export, web | AC-M2 |
| **M3** | Rotation：11 SPDR RS-Ratio 多线 + RS-rank 表 + breadth；点 bucket → N=1 + 成员 | compute, web | AC-M3 |
| **M4** | 主题分类：EDGAR + LLM 营收锚定 membership（point-in-time, human-in-loop）→ theme RS-Ratio 线 / 上色 | themes, compute | AC-M4 |
| **M5** | Valuation screener + Stock detail：duckdb-wasm 浏览器查询；per-name 面板 | export, web | AC-M5 |
| **M6** | 扩量：universe 由 ~500 扩到数千（Stooq bulk 已支撑） | ingest, compute | AC-M6 |
| **M7 ✅** | **ignition 发现引擎 + Discovery 持续点火榜**（§10.8，✅ 已实现 M7.1–M7.5）：`compute/ignition.py`（5 分量 + 横截面 + persistence）→ export 持续点火榜 → Discovery 改造（ignition 排序 + 点火诊断卡）→ Stock 衔接基本面。**双引擎脊柱兑现；AC-M7 五条 `make ac-m7` 一键复验。** | compute, export, web | AC-M7 |
| **M8 ✅** | **Ocean 重构 = Ignition × Valuation 海平面图**（§9.2）：`export/ocean.py` v3（60 日 daily、海平面 ign_pct 90、log P/S 横轴；schema v3 = payload 拆分 bulk 三绘制字段 columnar + per-stock 懒加载 detail，bulk brotli −83%）→ `ocean-draw.ts` 重写（log 轴 + 海平面 + candidate glow + 插值 + drawPtAt 列重建）→ `Ocean.tsx`（日期滑杆 + 受控 Play 插值动画 + hover 懒取 detail）→ **composite 退出全部用户可见层**（Discovery/Stock/Rotation/App）；Rotation league 改 # igniting / # candidates 聚合。 | export, compute, web | AC-M8 |

**起手**：把 BUILD-PLAN 全文 + 本 PRD 当 kickoff，从 **M0**（~500 只跑通端到端）起，先证明数据拉得动、composite 直观，再扩量。

---

## 14. 验收标准 (Definition of Done)

- **AC-M0**：~500 只的 `daily_bars` + `fundamentals_q` 落地；`derived_daily.composite` 与 `valuation_daily` 生成；抽查 5 只票，composite 5 分量与人工心算方向一致；估值 E≤0 正确退 n.m.。
- **AC-M1**：web 静态构建成功；Discovery board 渲染 evidence-card（≥18 张）；composite 角标用引擎导出的固定权重（k=0.5）composite（前端不重算、读导出值，与引擎 `signals.weights(0.5)` 数值一致，C9）（注：M1 期此处曾是 early⟷reliable 旋钮实时重排，M7 后取消——核心转 ignition）；evidence-card 6 字段 + composite 角标可展开 5 分量；d/d（day-over-day）标注。（composite 角标 / d/d 已于 M8 移除——composite 退出用户可见层。）
- **AC-M2**（已被 AC-M8 取代）：Ocean v1 渲染 ≥500 点流畅；scrubber 切周；pin 一只 → trail+箭头；scope=sector 时非成员变淡（C10）；Ocean 点位与 Stock 数字一致（C9）。
- **AC-M3**：≥11 条 sector RS-Ratio 线叠图；league 表 4 态正确；点 bucket → N=1 单线（斜率着色）+ 成员卡。
- **AC-M4**：≥4 个主题有 point-in-time membership（含 exposure + approved_by）；改一条 membership 的 as_of → 历史不被回溯污染（C3）；theme RS-Ratio 线非市值加权（C4）。
- **AC-M5**：Valuation 表 duckdb-wasm 浏览器查询可排序；as-of 三档上色正确；percentile 仅 current-vintage（stale=vint）；Stock stack 四格共用 x 轴、季度网格贯穿。
- **AC-M6**：universe 扩到 ≥2000 只仍满足 AC-M2 性能（NFR-8）。
- **AC-M7**：`derived_daily` 含 ignition 5 分量 + `ign_pct` + `ign_persist_days`；Discovery 按「持续点火」排序（ignition 跨入 top decile **且**持续 ~5 日），非 composite 排序；evidence-card 头部露点火证据（突破 / 放量 / 步速 / MA50 收复）；ignition 与 composite 共用同一份 per-stock 数据（C9）；持续点火榜非空且与 board 同源可追溯。
- **AC-M8**：Ocean = Ignition × Valuation 海平面图 —— 默认显示 latest daily snapshot；海平面 = ign_pct 90；海平面以上股票与 Discovery candidate 语义一致（C9）；横轴 = 原始 P/S 的 log 轴（非 valuation percentile）；日期 slider 可手动切日；Play 自动播放且点在相邻真实 EOD 间**平滑插值**（不伪造交易日，tooltip 取真实快照）；**composite 不再出现在任何用户可见 UI**（Discovery/Stock/Rotation/App）；`make ocean-c9`（ign_pct/candidate/ps 同源）+ `make web-test` + `make web-build` 全过。
- **横切**：每个 M 通过 `make verify`（两个 gate GATE_PASS）+ acceptance comment（§19）。

---

## 15. 显式 OUT OF SCOPE（防 scope creep）

intraday / real-time；auth / 多用户 / 支付；**非美上市标的**；**中文 cross-language 判定（本期 descoped）**；backtesting 引擎（验证信号有效性是独立的事，别掺进监控管线）；Ocean **无控/常驻全量** autoplay 动画（M8 的用户受控 Play/Pause + 相邻真实快照插值不在此列）；**email digest（暂不做，2026-06）**。

---

## 16. 已定死（code 不要再翻案）

- spine：**ignition 发现引擎（核心）+ valuation + raw evidence → 5 surface → 2 scale → 默认静态分发**（双引擎 2026-06-13 立项 §10.8；零后端从硬约束放宽为默认 §5.2；web 栈 = React+Vite+TS）。**M8 起 composite 退出全部用户可见层**，仅作计算层暂存。
- 数据源：Stooq(EOD) + Nasdaq screener + EDGAR + yfinance(脆弱兜底)。
- 5 surface 行为 + evidence-first（**永不给 buy/target**；不露 composite，露原始证据 + ignition + valuation）。
- 数学：vol-normalized EWMAC、RS=双窗超额收益横截面百分位、trend=KER/OLS t 值、composite=Σwᵢ·分量（权重**固定 k=0.5**，仅计算层保留；早⟷reliable **旋钮已取消**；§17）。
- **ignition 引擎（§10.8，2026-06-13 立项；2026-06-14 定调为项目核心）**：早期发现 = **项目核心技术指标**，5 个短窗口分量（加速 / 收缩-扩张 / 放量 / 突破收复 / RS 拐点）→ 横截面 top decile；**瞬时点火无精度，唯 persistence（持续 ~5 日）有 lift**（实证 `analysis/precision_ignition.py`）→ **Discovery = 「持续点火」榜** + **Ocean 海平面图**（§9.2，海平面 = ign_pct 90）；三级漏斗 = 触发 → 持续 → 翻财报。**ignition 无任何可调参**（5 分量等权 + 阈值离线定死，刻意=买 robustness 不买 alpha）。
- **核心是 ignition**：不回测优化，买 robustness 不买 alpha；ignition 无可调参；composite 仅计算层暂存、UI 不暴露，旋钮已取消。
- 估值：price ÷ trailing-4Q 日频、`E≤0→n.m.` 退 P/S、无 forward、百分位用 **common-vintage**；**Ocean 横轴用原始 P/S（log），非 percentile**（§9.2）。
- Rotation = **RS-Ratio 多线（非散点）**，league 聚合 **# igniting / # candidates**（非 composite 中位）；**Ocean 轴固定 ignition × P/S(log) 海平面图**（旧 RS×Val + RRG-axes 均已砍，`rsr`/`rsm` 删）。
- 全局 scope（all|sector|theme|pinned）单一真源、跨 tab 粘滞、可见可一键清，4 surface 全 respond。
- point-in-time membership 硬要求；theme 指数非市值加权。

---

## 17. 留给实现的决策（非翻案）与开放问题

- composite 固定权重的具体常数（现取 k=0.5 曲线）、trend 取 KER 还是 OLS t 值、Kalman 是否上（§10.3、§10.7）。
- **已定（2026-06-14）：early⟷reliable 旋钮取消。** 诊断为「假 early」（只在 composite 都滞后的分量间重配权、不引短窗口信号，§10.8）；项目核心转 ignition（无可调参，刻意），composite 退辅助确认、用固定 k=0.5。全局不再有可拨旋钮。
- theme membership 的营收阈值、LLM→human 审核流的具体形态（§8.3）。
- common-vintage 的 coverage 门槛具体 %（mock 用 ≤95 天近似，真实按「末季 ≥X% 已报」）（§10.5）。
- Ocean lasso 框选 set scope 的实现（mock 只做 respect/变淡）。
- duckdb-wasm 接法、shard 切分粒度（§5；客户端框架已定 React+Vite+TS，2026-06）。

---

## 18. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| EDGAR segment 脏、主题营收线缺失 | theme membership 部分/近似 | human-in-loop、exposure 连续而非二元、不宣称精确（C6） |
| 财报时滞导致横截面 vintage 不齐 | percentile 被先发者污染 | common-vintage 基准 + as-of 上色（§10.5、C7） |
| membership 改写回溯污染历史 | Ocean trail / RS-Ratio 线虚构 | point-in-time 硬约束、as_of 字段（C3） |
| 数据源 licensing（公开展示 / 再分发 / 商业化） | 合规风险 | 上线对应形态前复核（§6.2、NFR-7） |
| 两套合成/派生系统对不上 | surface 间数字矛盾 | 单一 per-stock 引擎（C9、NFR-2） |
| yfinance 非官方会断 | 数据缺口 | 仅作 fallback；Stooq 主干 + 校验补缺 |
| Ocean 数千点性能 | scrub/hover 卡顿 | canvas（非 DOM/SVG）、static-per-snapshot（NFR-8、C2） |

---

## 19. 内建工作流（实现纪律）

本仓库内建 **devtopology**（文件合同 + 硬 gate）+ **workflow-system 理念**（PR 为合并边界、worktree 隔离）。实现 TickerTide 时遵守：

- 新任务：`make route` → `make task-open QUERY="..."`（一个 worktree 一个 merge intent）。
- 改/增文件：更新 `docs/runtime/File-Contracts.json` 合同（禁占位）。
- 提交前：`make verify`（两个 gate 必须 GATE_PASS）。
- 收口：`make accept GOAL="..."` → PR → `gh pr merge --merge --delete-branch` → `make task-close`。

完整 policy：`docs/workflow/WORKFLOW.md`。

---

## 附录 A — 术语表

| 术语 | 含义 |
|---|---|
| **composite** | per-stock 综合分 `100·Σwᵢ·分量`，5 分量∈[0,1]（§10.6）；**确认引擎** |
| **ignition** | **发现引擎**：5 个短窗口分量的横截面综合（§10.8），与 composite 并列，抓早期点火 |
| **persistence** | ignition 点火后连续 ~5 日仍在 top decile = 去假突破的精度过滤（§10.8） |
| **三级漏斗** | ignition 触发（recall）→ persistence 确认（precision）→ 翻财报终筛（§10.8） |
| **EWMAC** | Exponentially Weighted Moving Average Crossover，vol-normalized 趋势（§10.1） |
| **RS percentile** | 双窗超额收益的每日横截面百分位（§10.2，≠ RSI ≠ IBD RS Rating ≠ RS-Ratio） |
| **RS-Ratio** | bucket 相对 SPY 的相对强度 level（JdK，§10.4） |
| **KER** | Kaufman Efficiency Ratio，趋势质量（§10.3） |
| **ASOF JOIN** | 把季度财务对齐到日线的时间连接（§10.5） |
| **common-vintage** | 横截面 percentile 的同 vintage 共同基准（§10.5） |
| **as-of** | 该票最新可得 trailing-4Q 的季末日（新鲜度，§9.5） |
| **n.m.** | not meaningful（E≤0 时 P/E 退 P/S，§10.5） |
| **scope** | 全局过滤状态 all/sector/theme/pinned（§9.1.2） |
| **evidence-card** | Stock 的 collapsed 态（§9.1.3） |
| **bucket** | sector 或 theme 的统称（Rotation 单位） |
| **exposure** | ticker 对某 theme 的连续营收暴露权重（§8.3） |

## 附录 B — 字段词典

**evidence-card 6 个原始数字**：`ret1m`(1M 涨幅) · `ret3m`(3M) · `ret6m`(6M) · `pctFromHigh`(距 52w high %) · `weeksSince`(突破后第几周) · `volX`(量/50 日均量 ×)。（market cap 在头部）

**composite 5 分量**：`rs_pct`(RS 百分位) · `high_proximity`(close/252d max) · `trend_quality`(KER/t-stat) · `volume`(量比+up/down) · `rs_accel`(RS 21 日变化)。

**估值倍数**：`pe` · `ps` · `evs` · `ev_ebitda` · `peg` · `growth`(营收增速) · `margin` · `rule40`(growth+margin)。

## 附录 C — 配色表（取自 UX 合同）

| 角色 | 变量 | hex |
|---|---|---|
| 主背景 | `--bg` | `#080b11` |
| 面板/卡片 | `--bg2` / `--panel` | `#0c1117` / `#0e141d` |
| 边框 | `--line` / `--line2` | `#1b232e` / `#2a3441` |
| 主文字 / 辅文字 | `--txt` / `--dim` / `--dim2` | `#e9eef5` / `#8593a3` / `#56616f` |
| 正向 / leading | `--grn` | `#2ec07a` |
| 负向 / lagging | `--red` | `#ff5d57` |
| weakening / 中性偏弱 | `--amb` | `#e0a02e` |
| improving / MA50 / weight bar | `--blu` | `#5197ff` |

**象限**：LEADING 绿 / WEAKENING 琥珀 / LAGGING 红 / IMPROVING 蓝。
**11 sector**：TECH `#4d9bff` · COMM `#7c6bff` · DISC `#ff8f3f` · HLTH `#2ec0a0` · FIN `#3fb950` · INDU `#c9a227` · NRG `#e0612e` · STPL `#9aa7b5` · MATL `#b06fd0` · UTIL `#5f8fa8` · RE `#d08fae`。
**8 theme**：AI `#2ec07a` · ROBO `#ff5d57` · SPACE `#5197ff` · OPTIC `#e0a02e` · SEMI `#7c6bff` · NUKE `#2ec0a0` · CYBR `#ff8f3f` · CLOUD `#9aa7b5`。
**MA 线**：MA50 `#378ADD` · MA150 `#BA7517` · MA200 `#888780`。
**新鲜度**：fresh(≤95d) 绿 · stale(≤160d) 琥珀 · 逾期(>160d) 红+行变暗。
**composite 分数**：≥62 绿 · ≥47 琥珀 · <47 暗灰。

---

*本 PRD 是活文档。任何需求/边界变化先回写本文件，再继续实现（见 §19 工作流）。*
