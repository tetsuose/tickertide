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

**单一核心探测引擎 = base→breakout + valuation + raw evidence，五个 lens，两个尺度，默认静态分发。**
- **base→breakout（核心探测引擎，§10.8）**：在 log 价格上估计单个变点 τ（长平台 base → 陡峭 breakout），用无量纲特征（÷ 日收益 σ）打分。北极星 = 在 multi-bagger 长期上行的**早期阶段**捕捉异常。recall-first：取 top-N、容忍假阳，基本面/财务在下游做 precision。驱动 Breakouts（突破）榜 + Ocean 纵轴（§9.2）。
- **valuation（横截面估值，§10.5）**：原始倍数（P/S / EV/S / P/E / EV/EBITDA），驱动 Ocean 横轴 + Valuation screener + Rotation/Stock 估值。
- **ignition / composite 均已退役（§10.6、§10.8）**：全宇宙实测 ignition（瞬时 + persistence）forward edge ≈ 0（无因果），composite 早被诊断为系统性滞后。两者皆不再驱动任何 surface、不再出现在任何用户可见层；§10.6/§10.8 仅保留为历史与 cross-ref 锚点。

旧表述「composite 驱动 Ocean / composite 副读 / ignition 是项目核心 / 双引擎并列」均已废弃（本次 spine pivot 2026-06-16）。

核心引擎**与 valuation 共用同一份 per-stock 数据**（C9），离线预计算 + 静态分发。base→breakout 测的是「长平台后的陡变点」这一个物理量（log 价格的单变点 + 无量纲斜率/增益特征），不是滞后水平、也不是瞬时加速度的横截面排名（§10.8，实证 `analysis/`）。

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
- **要么是滞后的确认引擎** —— 等 RS 进前列 / 创新高 / 趋势变干净才点亮（IBD / Minervini 谱系），那时 emerging leader 已经涨完大半。本工具核心 = base→breakout（§10.8）：在长平台 base 后的陡变点处、即 multi-bagger 上行**早期**就捕捉。

### 2.2 本工具的立场

- **evidence-first**：默认露原始证据（涨幅、距高点、量比、估值倍数、base/τ/breakout 标注），**永不给 buy / target**。
- **核心是 base→breakout（§10.8）**：唯一核心探测引擎 = log 价上估计单变点 τ（长平台 base → 陡突破）+ 无量纲特征，**无可调参**（参数离线定死，刻意=**买 robustness/stability，不买 alpha**）；recall-first 取 top-N，假阳交由下游基本面/财务 precision。**ignition 与 composite 均已退役**（§16）。
- **两个尺度解耦**：用来「逛」的 wide explore 和用来「动手」的 bounded decide 是不同界面，互不取代。
- **相对永远配绝对读**：RS-Ratio 只讲相对，必须与绝对走势（价格 / base→breakout 上下文）并置。

---

## 3. 目标用户与核心用例

### 3.1 用户

核心用户：具备量化/技术分析素养、盘后做美股研究与决策的投资者。当前不做 auth / 支付 / 团队协作。

### 3.2 核心用例

| # | 用例 | 尺度 | 主 surface |
|---|---|---|---|
| UC1 | 盘后扫一遍全市场，找「便宜且在转强」的票 | wide/explore | Ocean |
| UC2 | 看哪些 sector/theme 在轮动换手、谁在 leading | bounded/decide | Rotation |
| UC3 | 拿到一份 evidence-first 候选清单，逐张看证据（base/τ/breakout 标注）决定动手 | bounded/decide | Breakouts |
| UC4 | 按估值倍数横截面筛选（在 sector/theme 内比 percentile） | wide/explore | Valuation |
| UC5 | 钻进单只票，看价格↔基本面时间轴对齐、判断「赚到这波 vs 变贵无基本面」 | narrow | Stock |
| UC6 | 看 base→breakout 候选（核心发现引擎：长平台 base → 陡峭 breakout），每卡读原始证据 + base/τ/breakout 标注（无 composite/ignition，均已退役） | bounded/decide | Breakouts |
| UC7 | 锁定一个 sector/theme scope，所有 wide surface 同步过滤到该范围 | 全局 | scope filter |

---

## 4. 产品原则（脊柱，贯穿所有 surface）

**P1 — 单一核心引擎共用一份数据，不写五条独立管线。** base→breakout 探测引擎（§10.8）与 valuation（§10.5）共用同一份 per-stock 数据（C9）。
- **Breakouts（突破）** = base→breakout strength 排序；**Rotation** = RS-Ratio 按 bucket group-by（league 含 base→breakout 候选数聚合）；**Ocean** = base→breakout strength × valuation 二维相图（§9.2）；**Valuation** = 估值的 cross-section；**Stock** = 单票展开（base/τ/breakout 标注的价格走势 + 估值时间轴）。

**P2 — 两个尺度。**
- **wide / explore**：Ocean、Valuation screener —— 数千只，用来逛。
- **bounded / decide**：Breakouts（候选）、Rotation（~10–12 桶）—— 用来动手。

**P3 — 核心引擎参数最小化、无可调旋钮。** base→breakout（§10.8）参数最小（MINSEG、lookback 窗口、recency band、退化守卫），**无任何用户可调旋钮**——刻意=买 robustness/stability，不买 alpha。`early⟷reliable` 旋钮、ignition、composite 均已退役（§16/§17）。

**P4 — evidence-first，永不黑箱。** card/surface 默认露原始数字 + base/τ/breakout 证据（drift_step / fit_gain 等无量纲特征，§10.8）；永不给 buy/target。（composite 可展开角标已随 composite 退役，2026-06-16。）

**P5 — 数据一致性。** 五个 surface 的所有数字必须从同一份 per-stock 数据派生，同一只票在任何 surface 上对得上、可互相追溯（见 §7-9）。

**P6 — 相对配绝对。** RS-Ratio 只讲相对强度，永远与绝对走势（价格 / base→breakout 上下文）并置读。

**P7 — 单核心引擎 + recall-first 漏斗。** base→breakout 答「是否处于 multi-bagger 长期上行的早期（长平台后的陡变点）」（§10.8）——这是项目唯一的核心探测引擎。recall-first：先取 top-N（假阳是预期的），**基本面 / 财务分析是下游 precision 级**（取代旧的「触发→持续→翻财报」persistence 漏斗）。ignition（瞬时 + persistence，forward edge ≈ 0）与 composite（系统性滞后）均已退役；`early⟷reliable` 旋钮亦已取消（§16/§17）。

---

## 5. 系统架构

### 5.1 范式：离线预计算 + 静态分发（fomo5000）

```
GitHub Actions (nightly cron, post-US-close)
  └─ ingest (Python):  Stooq (bulk EOD) + Nasdaq screener (universe/cap/sector/PE) + SEC EDGAR (fundamentals/segment)
  └─ compute (DuckDB): derived_daily + base→breakout(τ/特征) + RS-Ratio 序列 + theme membership + percentiles(common-vintage) + ASOF valuation
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
- **C5 — RS-Ratio 只讲相对**：熊市能「Leading」却绝对在跌 → 永远配绝对走势（价格 / base→breakout 上下文，composite 已退役）一起读。
- **C6 — EDGAR segment 很脏**：大量公司不单列主题营收线 → LLM 抽取必然部分/近似，human-in-loop，别宣称精确。
- **C7 — 估值是 trailing 滞后近似**（财务季度更新），界面别假装日频精确。
- **C8 — scope filter 必须全程可见 + 一键清除**（dismissable chip，如 `Scope: Industrials ✕`）；禁止隐式 filtered 状态。
- **C9 — 所有 surface 来自单一 per-stock 引擎。** Ocean 的 `(brk_strength_pct, ps)` 位置（base→breakout STRENGTH × P/S，§9.2）、Stock 的价格/财务、Breakouts（突破）候选卡、Valuation 行必须从同一份底层 per-stock 数据（`derived_daily` / `valuation_daily` / `daily_bars` / `universe`）派生，可互相追溯（前端永不重算引擎）。（mock 现状是两套独立合成系统对不上；真实管线禁止此分裂。）
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
- **五个 tab**（胶囊按钮，选中高亮绿 `#2ec07a`）：`Ocean` · `Breakouts` · `Rotation` · `Valuation` · `Stock`。单击即切。
- **顶部控制栏两部分**：tab 组 · scope 过滤条（仅 scope≠all 时出现）。（无可拨旋钮——核心是 base→breakout、无可调参；旁附一行引擎说明「BASE→BREAKOUT = 发现核心引擎（长平台 base → 陡峭 breakout，τ 估计，无可调参） · composite/ignition 均已退役」。）
- **字体**：显示用 `Saira Semi Condensed`；数据用 `IBM Plex Mono`。

### 9.1 全局原语

**9.1.1 核心引擎 = base→breakout（无旋钮）**
- 全局**无可拨旋钮**：`early⟷reliable` 旋钮已取消（假 early，§10.8/§16）；核心 = base→breakout，参数离线定死、无可调参（刻意，买 robustness 不买 alpha）。
- base→breakout 在引擎离线算好（log 价单变点 τ + 无量纲特征，§10.8），前端**不重算**、直接读导出值（C9）。
- evidence-first（P4）：卡片 / Stock 露 base/τ/breakout 的原始价格行为 + 无量纲特征（drift_step / fit_gain 等），永不黑箱、永不给 buy/target。
- **composite 与 ignition 均已退役**（§16）：不再露角标、不再驱动任何 surface。

**9.1.2 global scope filter（C8、C10）**
- 状态 = `{ all | sector:X | theme:Y | pinned }`，**单一真源**。
- UI：scope≠all 时显示 chip `Scope: ● <名称> ✕`，副标 `filtering Breakouts · Valuation · Rotation · Ocean`。
- **写入口**（都写同一个 scope，后写覆盖）：Rotation 点表行/线、Valuation 下拉、Ocean 框选/点击。
- **sticky**：切 tab 不 reset；只有显式换或点 `✕` 才清。
- **respond**：Breakouts / Valuation / Rotation / Ocean；**Stock 是 per-name，不受 scope 影响**。
- **解耦**：「改 scope」与「换 view」是两个独立动作（点 sector 只 set scope + 原地展开 panel，不 auto-jump）。

**9.1.3 evidence-card = Stock 的 collapsed 态（一个对象，两种渲染密度）**
- **collapsed = evidence-card**（扫描态：密、多、浅）：price+volume+MA mini 图（叠加 base/τ/breakout 标注）+ 6 个**原始数字**（摊开，非 percentile）+ 头部 base→breakout 状态（🚀 已突破 + τ 距今 / 否则 brk_pct 角标）+ base→breakout 证据条 + AI「why moving」占位格。**无 composite / ignition 角标（均已退役）。**
- **expanded = Stock**（详情态：全、单、深）：§9.6 完整视图。
- 点任意 card → 展开成 Stock。**不要把两者当两个东西做。**
- card 字段 = **6 个原始数字**：原始涨幅 1M / 3M / 6M、距 52w high %、突破后第几周、量/均量 `×`、（外加 market cap 在头部）。密度 = 一屏 3–4 张大卡（2 列网格）。

### 9.2 Ocean（canvas，wide explore）—— base→breakout 强度 × Valuation 二维相图（海平面图）

> **重构史**：Ocean 从旧的「RS percentile × Valuation percentile 周度散点」（M2）改为 daily 海平面图；M8 的纵轴曾是 ignition 横截面百分位。**2026-06-16 脊柱转向后**：纵轴改为 **base→breakout 强度**（§10.8），即「长平台 base → 陡峭 breakout」的强度横截面百分位；横轴仍是 valuation。理由：核心已转 base→breakout，Ocean 作为 wide/explore 入口应直接呈现「谁刚从平台突破、贵不贵」；ignition / composite 均已退役、不进任何用户可见层。旧 RS×Val 设计见 ROADMAP「M2」段（history）。

- **渲染**：一个 EOD daily cross-section，数千只股票的 canvas 散点。
- **轴固定**：
  - **y = brk_strength_pct**（base→breakout 强度横截面百分位 0–100，§10.8）。一条固定**海平面 = brk_strength_pct 90**（top decile）。海平面**以上 = 已突破**（长平台 base 后陡峭 breakout：drift_step/τ 拐点 + ceiling clearance + 量能扩张），跃出高度 ∝ `brk_strength_pct − 90`；海平面以上区域轻微高亮、以下压暗。
  - **x = 原始 trailing P/S TTM**（`ps`），**log 轴**。**不用 valuation percentile 做默认横轴**，不引入估值综合分或隐含阈值参数（§16）。`x_domain` 由导出窗口内所有有效 P/S 自动算出，供 log scale。
- **candidate 语义（2026-06-16 spine pivot）**：海平面以上（= `brk_strength_pct ≥ 90`，base→breakout 强度 top decile）= Breakouts（突破）候选 —— Ocean 上层点与 Breakouts candidate **同一总体、逐票可追溯**（C9）。**recall-first 刻意放宽：false positive 是预期的，下游 fundamentals/financial 分析才是 precision 阶段；不再用 `ign_persist_days ≥ 5` 的 persistence gate（ignition 已退役，§10.8）。**
- **color**（两模式可切）：sector / theme（选定主题：成员正常、非成员极淡）。candidate 点（base→breakout 已突破）加光晕 + 亮环；海平面以上点 solid bright、以下更暗。
- **size** = market cap（半径随 sqrt(mktcap)，clamp 1.6–11px）。
- **时间轴（日期滑杆 + 播放）**：图下方日期 slider 在不同 EOD 之间切换，**默认打开 latest EOD**。Play/Pause + prev/next；**Play 自动播放**时每支股票的点在**相邻真实 EOD 快照之间用视觉插值平滑移动**（rAF，每两日 ~900–1200ms，到最新日自动停）。**插值仅用于视觉动画，不伪造中间交易日数据**：tooltip 与状态恒取真实 snapshot。拖动 slider 暂停播放并切到对应日期（phase 归零）。
- **交互**：
  - hover → nearest-neighbor 显示 tip（ticker / sector / brk_strength_pct / base 时长 + τ + drift_step + candidate / P/S / EV/S / P/E / EV/EBITDA / 10d·1m return / volume surge / valuation freshness / mktcap / themes）。hover 命中用**当前绘制后的插值位置**。其中 brk_strength_pct / candidate / P/S 三个绘制字段来自 bulk 即时可见，其余证据字段按票**懒加载**（见下「payload」，首次 hover 显骨架 `…`）。
  - click → toggle **pin**（pinned 点高亮 + 标签，仅 ≤ cap 时标 ticker，C2）。
  - 框选（lasso）→ **set 全局 scope**（Ocean 是 scope 的第一个写入口，C10）。
- **respect scope**（C10）：非 scope 点 filter 掉或大幅变淡（in-scope ~0.5–0.92 按是否点亮，out ~0.06）。
- **已砍**：旧 RS×Val 轴、(50,50) 十字线、quadrant 配色、周度 WEEK scrubber、pinned 多周 trail/箭头（时间维度由播放动画承担）；更早砍掉的 RRG-axes（`rsr`/`rsm` 字段早已删除）。
- **payload（schema v3，体积裁剪 / 为 M6 扩量铺路）**：每帧绘制只需 3 个字段（`ps` / `brk_strength_pct` / `candidate`），其余仅 tooltip 字段实测占压缩体积 ~79%。故 `ocean.json` 拆两层：**bulk**（`ocean.json`，每票仅三绘制字段的 columnar 数组、与 `dates[]` 同索引、全员前置下载）+ **per-stock detail**（`ocean/<TICKER>.json`，9 个 tooltip 字段 columnar、hover 时按票懒加载——只下你真去看的票）。实测 top-500 bulk brotli ≈ **100KB**（旧 v2 整合 596KB → −83%）。**勘误**：旧文写的「ocean gzip ~1.5MB」是 **board.json** 的数；ocean v2 实测 gzip 866KB / brotli 596KB。**board.json 现已同法拆分（schema v2，见 §9.3）**：full brotli ~1.20MB → bulk ~51KB + 懒加载 90d chart。M6 全量后 bulk 仍只随票数 ×3 字段增长、detail 永远按需，故可扛数千只。两文件 columnar 且按 `dates[]` 同索引对齐、全字段 C9 同源（`derived_daily` / `valuation_daily` / `daily_bars` / `universe`）；`make ocean-c9` 额外校验 bulk↔detail 一致（bulk `cand` == brk_strength_pct≥90、detail.evs 追溯 board）。**渲染行为不变**：海平面图 / 轴 / candidate gate / 插值动画结构完全一致，仅纵轴语义改为 base→breakout 强度、candidate gate 改为 brk_strength_pct≥90（去 persistence）；首次 hover 某票仍多一次取数（tooltip 先显 3 个已知字段 + 骨架）。

### 9.3 Breakouts（突破）（evidence-first 卡流，bounded decide）

- **渲染**：2 列 evidence-card 网格，**按 base→breakout STRENGTH 排序**（§10.8，2026-06-16 spine pivot；recall-first，取 top-N）—— **不是 composite、也不是 ignition 排序**（两者均已退役，§16）。这一屏的本质是 **逐张检视被选中候选的价格动作（price action），并在 mini-chart 上标注 base / τ / breakout**（长平台 → 拐点 → 陡峭突破），而非「持续点火」持续度排行榜。卡片为 evidence-first（原始数字 + base/τ/breakout 证据），**不显示 composite / ignition 角标**。
- **候选池 = 两级漏斗**（§10.8，2026-06-16 spine pivot）：① **recall-first base→breakout 检测**——在 log price 上估计单变点 τ（2 段分段线性 OLS、τ 自适应、无固定 base/breakout 窗口），按 base→breakout STRENGTH（drift_step、fit_gain、breakout 陡度、ceiling clearance、bar-level VCP、volume surge 等无量纲特征，÷ 日收益 σ）做横截面排序、取 top-N（**false positive 是预期的，刻意 recall-first**）→ 上榜；② **基本面/财务终筛（precision，human）**——用户在 Stock 翻财报消化误报。bound = base→breakout STRENGTH top-N 名单而非硬 top-20；漏斗参数（MINSEG、回看窗、recency band、退化守卫）离线定死、**无旋钮可调**。**ignition（含瞬时点火 + persistence）已退役**（full-universe 实测其 forward edge ≈ 0 causal，§10.8/§16）。
- **base→breakout 标注**：卡片头部突出 base→breakout 证据（base 平台时长 / 估计拐点日 τ / drift_step=(s2−s1)/σ 步陡度 / fit_gain 拐点显著度 / 是否清越平台高点 ceiling / 突破放量 ×），衔接「为什么现在值得看」→ 接 Stock 翻财报做 precision 级筛选。
- **每张卡** = §9.1.3 evidence-card：
  - 头部：ticker + `(sector · $XXB mktcap)` + base→breakout 状态（🚀 已突破 + τ 距今天数 / 否则 brk_strength_pct 角标）。
  - theme tags（若有）。
  - MiniChart：90 日 K 线 + MA50/150/200 + 成交量 + 52w 高虚线，**叠加 base→breakout 标注**：log-price 上的 base 平台区段、估计拐点 τ 竖线、breakout 段斜率、平台高点 ceiling 线。卡片渲染时显示骨架占位，chart 到位后填入（懒加载，见下）。
  - 6 字段行：1M / 3M / 6M / from-high / weeks-since-breakout（自 τ 起算）/ vol×（涨绿跌红，量≥1.5× 绿）。
  - 「why moving」AI 占位格。
- **payload（schema v2，体积裁剪 —— ocean v3 同法落到 board）**：90d mini-chart 实测占 board.json raw 体积 ~96%，而 Breakouts 是 bounded（App 截 top-20），同屏只 ~20 张图。故拆两层：**bulk**（`board.json`，每票卡面数据但**不含 chart**、全员前置下载，仍带 Breakouts 排序「base→breakout 强度」+ 跨全 universe scope filter 所需的全部字段）+ **per-stock chart**（`board/<TICKER>.json`，仅该票 90d mini-chart，卡片渲染时按票懒加载——只下你真看到的票）。实测 full board brotli ~1.20MB → bulk ~51KB + 20×~2.5KB ≈ **101KB 首屏（−92%）**。bulk 与 chart **同一遍构建、同源 `daily_bars`（C9，拆分只改 chart 存放位置不改其值）**；纯 columnar 不做（chart 本就并列数组、剥离后 bulk 已 ~51KB，再 columnar 收益可忽略——同 ocean 教训）。不复用 `stock/<T>.json`（那是 2y bundle，复用首屏 223KB 且 high_52w 窗口不符要客户端重算）。
- **交互**：点卡任意处 → 打开 Stock。（无 composite 展开面板，M8。）
- **respect scope**：先 filter 再排序。

### 9.4 Rotation（narrow decide）

- **总览（scope=all）**：
  - **所有 sector/theme 的 RS-Ratio 多线图（非散点）**：height=level（>100 跑赢 SPY）、slope=momentum（走平=中性）、线交叉=leadership 换手。基线 y=100。hover 高亮一条、其余变淡；右缘按末值排序贴标签防重叠。
  - **enriched league 表**（按 RS-Ratio level 排序）：`# | bucket | RS-Ratio | Δ4w(=斜率/momentum) | state`，外加 breadth(%>MA50 / %>MA200)、#at-52w-high、# base→breakout 候选、agg EV/S、多 horizon relative return。state 由 level+slope 推回四态：**LEADING**(≥100,↑) / **WEAKENING**(≥100,↓) / **IMPROVING**(<100,↑) / **LAGGING**(<100,↓)。
  - **GICS ↔ Theme 切换**。
- **钻进（点表行/线 → set scope + 钻进该 bucket，inline drawer 非新 tab）**：
  - **N=1 单线放大**：单 bucket 的 RS-Ratio 折线，**线色=斜率**（升绿/降红，N=1 时 color 空出来给斜率）。
  - **sector 聚合 summary**（唯一真正新内容，filter 得不到）：breadth、dispersion、aggregate valuation、#at-52w-high、sector RS trail。
  - **成员预览**：Breakouts 同款 evidence-card（top-N），每张 → Stock；按钮「在 Ocean / Valuation / Breakouts 看全部成员」= set scope + 跳转。
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
  3. **REVENUE**：季度营收 bars（YoY 增绿降红），bar 放在**财季 `period_end`**（业务期），并在每季 **`effective_eod_date`** 处画一条 formal-filing 标记（数据从这天才入 P/S；§10.5 formal-filing PIT）——避免「`period_end` 当天市场就知道营收」的错觉。只画已正式 filing 生效（`effective_eod ≤ snap`）的季。
  4. **P/S over time**：每日 P/S 线（= mktcap / TTM revenue）；线**在 `effective_eod_date` 阶进，绝不在 `period_end` 阶进**（读 `valuation_daily`，前端不重算）。
  - 直接可视化：价↑营收平 = P/S 扩 = **变贵无基本面**；价↑营收↑ = **赚到这波**。
  - hover「某日的有效营收」取 `effective_eod_date ≤ 游标日` 的最新季（非 `period_end ≤ 游标日`），与 P/S 阶进一致、反 lookahead。
- **下接**：6 个估值指标卡（P/S · EV/S · EV/EBITDA · P/E · Rev growth · Rule of 40）+ base→breakout 诊断（log-price 2 段分段线性拟合：base_slope/σ · brk_slope/σ · drift_step=(s2−s1)/σ · fit_gain=1−SSE2/SSE1 · ceiling clearance · bar-level VCP · 量能放大，τ 标在价格轴）+ theme memberships(+exposure) + 最新 filing AI 摘要。**无 composite / ignition 分量序列（均已退役）。**
- **头部**：ticker + `sector · $XXB` + theme chips（带 exposure %）+ **BRK PCT 大分数**（base→breakout 强度横截面百分位；发现核心；candidate 时绿）。
- **入口**：card 点开落地 / 顶部下拉按 ticker 直接查（per-name，**不受 scope 影响**）。

### 9.7 配色与视觉语言

见附录 C。核心：绿 `#2ec07a`(正向/leading) · 红 `#ff5d57`(负向/lagging) · 琥珀 `#e0a02e`(weakening/中性偏弱) · 蓝 `#5197ff`(improving/MA50/weight bar)。象限、11 sector、8 theme 各有固定色；base→breakout 强度（brk_strength_pct）海平面以上（≥90，已突破）绿 / 接近海平面（≥80）琥珀 / else 暗灰（composite 分色已退役，仅计算层 history）。

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

- **统一规则**：所有倍数 = price（或 mktcap/EV）÷ **过往 4 个季度的对应财务指标**，逐日计算（分母按季 ASOF 阶进、分子日频）。方法就是「价 ÷ trailing-4Q」，**不引入任何 analyst estimate**（forward 不做）。统一套用 P/E（净利）、P/S（营收）、EV/EBITDA 等。默认 diluted GAAP 归母，**formal-filing point-in-time**（见下；用正式 filing 实报、不用 restated，防 lookahead）；`E≤0 → n.m.`，回退 P/S/EV/S。
- **formal-filing PIT（口径定死，§16）**：所有倍数分母 **只用正式 SEC filing（10-Q / 10-K / 20-F / 40-F）的 trailing-4Q**，不接 earnings release / press release / 8-K 预披露 / analyst estimate / forward。三个日期分工：`period_end` = 财务归属的会计期末（**业务期，绝不作可得性对齐**）；`filed_date` = 正式 filing 日；`effective_eod_date` = 该 filing 从哪个 EOD 快照起进入 `valuation_daily`（**ASOF 键**）。v1：`effective_eod_date = filed_date`；后续引入 EDGAR accepted-timestamp 后，盘后受理顺延到 `next_trading_day(filed_date)`。**因此 3 月末结束、4 月才报的财季，P/S 在 4 月（filing 生效日）才阶进，不回填到 3 月。** `valuation_daily.valuation_basis = 'formal_filing_pit'` 标该口径，防与未来 market-reaction PIT 混用。名称用 *formal-filing P/S*，不叫 real-time / market-known / first-disclosure P/S。
- **split-alignment（拆股口径自洽，定死）**：价格序列（`daily_bars`，yfinance）在拆股**生效当日即**回溯调整到拆股后口径，但 EDGAR 的 per-share（`eps_ttm`）与股本（`shares`）要等**下一份正式 filing 才阶进**到拆股后口径（10-Q/10-K 节奏，可滞后数月）。这段窗口内 `shares × adj_close ÷ revenue`（及 `adj_close ÷ eps`）会把**拆股后价**乘**拆股前股本**，使 P/S·P/E·EV/S·EV/EBITDA·PEG 整体塌掉一个拆股比（KLAC 10-for-1 ex-2026-06-12 → 倍数 ~10× 偏小，PE 67→6.7）。**口径**：每条 filing 带 `split_adj = ∏ ratio`（`splits` 表中 `ex_date ∈ (effective_eod, 价格基准日]` 的拆股累乘），分子里把 `eps/shares` 抬到价格口径；`revenue/ebitda/debt/cash` 是绝对额、**拆股不变**、不动。无滞后拆股 → `split_adj = 1` → 与旧行为逐字节一致。这是 formal-filing PIT 框架内的**自洽性修正**（仍 trailing-4Q、仍 anti-lookahead、仍无 forward），非新口径。`splits` 源 = yfinance `.splits`；AC = `compute/split_check.py`（split 滞后 filing / 无 split / filing 已含 split 三态）。
- `EV = mktcap + total_debt − cash`。
- **EBITDA 口径（best-effort，§10.5）**：`EBITDA = EBIT + D&A`。EBIT 优先 `OperatingIncomeLoss`，缺则退 `pretax income + interest`(≈EBIT；KLA 等 2015 后弃用 OperatingIncomeLoss tag、`GrossProfit` 也断档)。D&A 单季由 **YTD 差分**还原(现金流量表 D&A 多为累计 YTD：Q2=H1−Q1、Q3=9M−H1、Q4=FY−9M)，否则季度 EV/EBITDA/margin/rule40 全缺(EBITDA 同时驱动这三者)。D&A 只取**合并** concept(`DepreciationDepletionAndAmortization` 系，跨年同义切换 merge)、**不掺** component `Depreciation`(漏无形摊销，对收购密集股如 MSFT 失真)→ 仅有 component tag 的票 EBITDA **留缺**(EV/EBITDA 退 EV/S)，缺失优于错值。AC=`compute/ebitda_check.py`。
- P/S 看 **level + expansion（相对起点/行业中位）+ percentile**，别只看 level。
- **跨行业比较**优先 EV/EBIT（P/E 受杠杆扭曲）。横截面约束 = 方法一致（全票同算法）。
- **as-of 同步（数据完整性）**：横截面每个倍数用该票**最新可得** trailing-4Q（永不取未来季；ASOF 键 = `effective_eod_date` 而非 `period_end` = anti-lookahead），但各票窗口截止日不同（财报时滞 10-Q ~40/45 天、10-K ~60/75/90 天 + off-calendar 财年）→ **必须暴露 as-of 日并分档上色**（§9.5）：fresh / stale / n.m.。新鲜度按「最新**季末**距今天数」定义（`date − period_end`，>~95 天 = 落后一季 = flag；与披露滞后 `filed − period_end` 是两个量，后者另列 `disclosure_lag_days`）。
- **横截面 percentile = common-vintage**：percentile 是相对统计，只有同 vintage 才有效。**绝对 multiple** 用最新可得（fresh，显示+标记）；**percentile/排名**用「该 peer 集 ≥X%(如 50%)已报出的最近季末」为共同基准，覆盖率没过线则基准停在上一季 → **孤单先发报者不移动基准**。绝不拿先发者的新季数去排别人的旧季数。**当前实现 = fresh-cohort v1**：只在 fresh cohort（as-of ≤~95d）内排名、stale 不进分母；完整的「peer 覆盖率门槛后才切共同 vintage」为后续（§13）。

### 10.6 composite（已退役 — RETIRED）

> **状态（2026-06-16 spine pivot）：composite 已完全退役。** 它是趋势**确认**引擎（5 分量全是长窗口 / 测水平），数学上系统性滞后于「早期」，无法服务北极星。M8 已退出全部用户可见层；本次进一步退役，**不再计算、不再导出、不再驱动任何 surface**。本节仅保留为历史与 cross-ref 锚点，勿据此实现新代码。核心探测引擎见 §10.8（base→breakout）。

（历史口径，供追溯，**不再生效**）`score = 100 · Σ wᵢ · componentᵢ`，components ∈[0,1] = `rs_pct` / `high_proximity = close/rolling_max(close,252)` / `trend_quality` / `volume` / `rs_accel`；固定 `k=0.5` 权重曲线 `rs=.215, high=.22, trend=.17, vol=.12, accel=.275`。`early⟷reliable` 旋钮早已取消。

### 10.7 (optional) Kalman level+slope

要日间稳定 / 无丑跳变时再上：对 RS line 做 `rs≈level`、`slope` 变化，`slope/√var` 做 z-score。**不是关键路径**，也不是核心探测引擎的一部分（核心 = §10.8 base→breakout）。

### 10.8 base→breakout 引擎（核心探测，单引擎）

> **为什么是 base→breakout、为什么 ignition 退役（已定 2026-06-16，实证支撑）：** 北极星 = 在 multi-bagger **长期上行的早期阶段**捕捉异常。全宇宙实测表明 ignition（瞬时点火 + persistence）的 forward edge ≈ 0（无因果）——瞬时无精度，persistence 也未带来可归因的 lift；composite（§10.6）则是滞后的确认引擎。两者皆退役。服务北极星的形态是「**长平台 base → 陡峭 breakout**」：用 log 价格上的单变点拟合直接刻画「先长期平、再突然陡」这一个物理量。**结论**：base→breakout 成为项目**唯一**的核心探测引擎，参数最小、**无任何用户可调旋钮**（刻意=买 robustness/stability，不买 alpha）。

**10.8.1 变点估计（核心，单引擎、无固定窗口）：** 对每只票，在 **log 价格** `y_t = ln(close_t)` 上、于 lookback 窗口内估计**单个变点 τ**，做 **2 段分段线性（OLS）拟合**：τ 之前一段斜率 `s1`、之后一段斜率 `s2`。**τ 是被估计出来的**（扫所有合法切点取总 SSE 最小者），**不预设固定的 base 窗口 / breakout 窗口**。`SSE1` = 单段线性（无变点）残差平方和；`SSE2` = 2 段拟合残差平方和。退化守卫：每段长度 ≥ `MINSEG`；τ 落在 recency band 内（要求 breakout 段足够近期）；样本不足 / 近乎单调 / 拟合退化的票剔除。

**10.8.2 无量纲特征（÷ 日收益 σ，全部 per-stock）：** 设 `σ` = 日 log-return 标准差。
1. **base 平坦度** `base_slope/σ ≈ 0`（其中 `base_slope ≡ s1`）—— τ 之前接近水平的长平台。
2. **breakout 陡度** `brk_slope/σ`（其中 `brk_slope ≡ s2`）—— τ 之后的陡峭上行（越大越陡）。
3. **drift step** `drift_step = (s2 − s1)/σ`（**最强判别特征**，经验阈值 ≳ 0.13；全宇宙中位 ≈ 0）—— 斜率的跳变幅度。
4. **fit gain** `fit_gain = 1 − SSE2/SSE1`（拐点显著度 / kink salience，经验阈值 ≳ 0.7）—— 引入变点相对单段拟合的改善。
5. **ceiling clearance** `clearance = close_now / max(close over base) − 1`（> 0 = 已清越 base 段高点，确认是突破而非仍在平台内震荡）。
6. **bar-level VCP** `vcp = ATR(τ:τ+20) / ATR(base)`（base 段 ATR 收缩 → breakout 段放大）。
7. **volume surge** `vsurge = mean(vol, τ:τ+20) / mean(vol, base)`（breakout 段放量）。

`base→breakout strength` = 上述无量纲特征的**固定**组合（参考式见 10.8.4，drift_step 为主判别量、平 base 与显著拐点加权；**非用户旋钮**）；每日再做横截面 percentile-rank → `brk_strength_pct`（驱动 Ocean 纵轴 / Breakouts 排序，§9.2/§9.3）。

**10.8.3 recall-first 漏斗（产品形态，已定）：**
1. **base→breakout 探测**（recall-first）→ 按 strength 排序、取 top-N。**假阳是预期的**（recall 优先于 precision）。
2. **基本面 / 财务 precision**（下游）→ 用户在 Stock 翻财报做业务 / 财务，作为 precision 级筛除假阳（**取代**旧的 ignition「触发→持续→翻财报」persistence 漏斗）。

**10.8.4 参考实现常数（离线定死、无旋钮；具体取值留 §17）：** lookback 窗 `H ≈ 504` bar（~2y）；`σ` = 窗内日 log-return 标准差；变点扫描 `MINSEG ≈ 40` bar；recency band = τ 落在最近 ~15–252 bar（≈3 周–1 年，太老不算「当前突破」）。综合强度参考式 `strength = fit_gain · max(0, drift_step) · exp(−1.5·|base_slope/σ|)`。退化护栏：`clearance ∈ (0, 2.5]`、`brk_slope/σ` 设上限、base 段中位价 `> $3`（剔仙股 / SPAC / 跳空）。这些常数离线定死、**非用户旋钮**（§17）。实证原型 `analysis/`（`base_breakout` / `live_screen` / `full_screen`）。

> **诚实定调（同 §10「买 robustness 不买 alpha」）：** recall-first 取宽、容忍假阳，下游基本面才是 precision；不回测调参买 alpha。实证 caveat：yfinance 仅含现存票 → 幸存者偏差；2023–26 是 AI 牛市 → base 偏高。**ignition / composite 均已退役**：全宇宙实测 ignition forward edge ≈ 0（实证脚本 `analysis/verify_ignition.py` timing + `analysis/precision_ignition.py` precision，保留为退役依据），composite 系统性滞后。**OOS 校验（`analysis/walkforward_breakout.py`，时间 holdout）**：base→breakout 自身的 forward 收益 edge **弱且 regime-dependent**（TRAIN 2023–24 尾部为负、TEST 2025–26 为正）——**这正是 recall-first 的依据：它是高召回的形状发现器、不是买入信号；precision 交给下游基本面/财务**（买 robustness/stability，不买 alpha）。

---

## 11. 功能需求 (FR) 与非功能需求 (NFR)

### 11.1 功能需求

| ID | 需求 | 关联 |
|---|---|---|
| FR-1 | 每日(EOD)从 Stooq/Nasdaq/EDGAR 拉取并落地 US-only universe 的价格、universe、基本面、segment | §6 |
| FR-2 | 由单一 per-stock 引擎计算 base→breakout 特征（τ 单变点 2 段 OLS + 无量纲特征）+ derived_daily（composite/ignition 均已退役，§10.6/§10.8） | §10.8, C9 |
| FR-3 | 每日 cross-sectional RS percentile + rs_accel | §10.2 |
| FR-4 | ASOF 对齐的日频估值倍数（P/E·P/S·EV/S·EV/EBITDA·PEG·Rule40），E≤0→n.m. | §10.5 |
| FR-5 | common-vintage 横截面 percentile，stale 不进排名 | §10.5 |
| FR-6 | sector(11 SPDR) + theme 的 RS-Ratio 周序列 | §10.4 |
| FR-7 | theme membership：LLM 营收锚定 + human-in-loop + point-in-time | §8.3, C3, C6 |
| FR-8 | Ocean：canvas 散点、固定 base→breakout-strength × P/S(log) 二维相图轴、日期滑杆 + 受控 Play 插值动画、pin/lasso→scope、respect scope | §9.2 |
| FR-9 | Breakouts（突破，原 Discovery）：检视所选候选的价格行为，标注 base / τ / breakout；evidence-first、AI 兜底候选；不露 composite/ignition（均已退役） | §9.3 |
| FR-10 | Rotation：RS-Ratio 多线 + enriched league 表 + GICS/Theme 切换 + 钻进 | §9.4 |
| FR-11 | Valuation：横截面 screener、duckdb-wasm 查询、as-of 上色、scope 过滤 | §9.5 |
| FR-12 | Stock：price↔fundamentals 时间轴对齐 stack + 估值/分量/membership | §9.6 |
| FR-13 | ~~composite 确认副读~~（**已退役**，2026-06-16）：不再驱动任何 surface、不再露角标、不再有旋钮（early⟷reliable 早已取消）；保留条目仅为 cross-ref | §10.6, §16 |
| FR-14 | global scope filter：单一真源、跨 tab 粘滞、可见可一键清、4 surface respond | §9.1.2, C8, C10 |
| FR-15 | evidence-card collapsed ↔ Stock expanded 同一对象两态 | §9.1.3 |
| FR-16 | export：snapshot → Parquet/JSON 分片，不含任何 key | §5, C9 |
| FR-17 | base→breakout 发现引擎：LOG 价上估计单变点 τ（2 段分段线性 OLS，τ 估计、无固定窗口）→ 无量纲特征（base_slope/σ≈0、brk_slope/σ、drift_step=(s2−s1)/σ、fit_gain=1−SSE2/SSE1、ceiling clearance、bar-level VCP、volume surge）→ recall-first 取 top-N（假阳预期之内，基本面/财务为下游 precision）；Breakouts（突破）按 base→breakout 强度排序 + base/τ/breakout 标注卡 | §10.8, §9.3 |

### 11.2 非功能需求

| ID | 需求 |
|---|---|
| NFR-1 | **默认静态分发**：M0–M1 无常驻 server / 托管 DB、client 不暴露 key；零后端非硬约束，视觉/功能需要可引入（§5.2） |
| NFR-2 | **数据一致性**：同一票在所有 surface 数字可互相追溯（C9） |
| NFR-3 | **认知带宽**：DECISION bounded、标签仅 pinned、autoplay 仅用户受控（C1/C2） |
| NFR-4 | **可复现**：纯 trailing、point-in-time、anti-lookahead；无 forward estimate（§10.5） |
| NFR-5 | **可审计**：base→breakout 永不黑箱，证据可见——露 base / τ / breakout 的原始价格行为 + 无量纲特征（drift_step / fit_gain 等），永不给 buy/target（P4） |
| NFR-6 | **US-only**：非美标的不进 universe（§1.3） |
| NFR-7 | **Licensing 合规**：公开展示 / 再分发 / 商业化前复核数据源条款（§6.2） |
| NFR-8 | **Ocean 性能**：数千点 canvas 流畅 scrub / hover / pin（§9.2） |

---

## 12. 数据模型（DuckDB schema，起点可演进）

```sql
universe(ticker PK, name, exchange, sector, industry, mktcap, is_active, first_seen, last_seen);
daily_bars(ticker, date, open, high, low, close, adj_close, volume, PRIMARY KEY(ticker,date));
fundamentals_q(ticker, period_end, filed_date, effective_eod_date, source_type, source_form,  -- formal-filing PIT (§10.5)
               revenue_ttm, shares, total_debt, cash, ebitda_ttm, eps_ttm);
segment_revenue(ticker, period_end, segment, revenue);            -- from EDGAR, dirty
theme_membership(ticker, theme, exposure, as_of_date, source, approved_by);  -- many-to-many, point-in-time
derived_daily(ticker, date, ret_63, ret_126, rs_pct, rs_accel, high_prox,
              ma50, ma150, ma200, trend_quality, vol_ratio, ud_vol_ratio,
              ewmac_fast, ewmac_slow, rank_in_universe,             -- composite 已退役（§10.6），不再导出
              brk_tau_date, brk_base_slope, brk_brk_slope,             -- base→breakout：估计单变点 τ + 两段斜率（无量纲，÷ daily-return σ，§10.8）
              brk_drift_step, brk_fit_gain, brk_clearance, brk_vcp, brk_vsurge,  -- drift_step=(s2−s1)/σ · fit_gain=1−SSE2/SSE1 · ceiling clearance · bar-level VCP · volume surge
              brk_strength, brk_strength_pct);                        -- base→breakout 综合强度 + 横截面 pct
valuation_daily(ticker, date, pe, ps, evs, ev_ebitda, peg, growth, margin, rule40,
                as_of_period_end, as_of_filed, as_of_effective_eod, valuation_basis);  -- formal-filing PIT, ASOF on effective_eod (§10.5)
bucket_rrg(bucket_type, bucket, date, rs_ratio, rs_mom);          -- sectors + themes
spx_daily(date, close);
```

- 估值对齐核心：`valuation_daily` 由 `daily_bars ASOF JOIN fundamentals_q ON ticker AND date>=effective_eod_date` 生成（formal-filing PIT，ASOF 键是 `effective_eod_date` 而非 `period_end`，§10.5；v1 `effective_eod_date = filed_date`）。
- export：把 `derived_daily` + `valuation_daily` 最新快照 + `bucket_rrg` 拆成 Parquet/JSON 分片给 client。**board（schema v2）/ ocean（schema v3）均 payload 拆分**：bulk（前置下载、不含重数据）+ per-stock 懒加载分片（board=90d mini-chart `board/<T>.json`；ocean=9 个 tooltip 字段 `ocean/<T>.json`），分片与 bulk 同一遍构建、同源 C9。

---

## 13. 里程碑与构建顺序

| M | 目标 | 主要模块 | 验收（见 §14） |
|---|---|---|---|
| **M0** | 数据 + 引擎（先窄）：Stooq+Nasdaq+EDGAR ingest → DuckDB → 对 ~500 只(S&P 500 + 人工种子)算 valuation + 早期 trend 特征（composite 历史口径，已退役——见 M7/M8 转 base→breakout） | ingest, compute | AC-M0 |
| **M1** | Web 客户端起步 + 证据卡 board：React 证据卡流 + composite 排序 + d/d（历史口径：M1 期建过 early⟷reliable 旋钮，M7 取消；M7/M8 后核心转 base→breakout、composite 与 ignition 均已退役；board 即后来的 Breakouts/突破。email digest 已移出，见 §15） | export, web | AC-M1 |
| **M2** | Ocean v1（已被 M8 取代）：canvas + 周 scrubber + pin→trail，轴固定 valuation×RS | export, web | AC-M2 |
| **M3** | Rotation：11 SPDR RS-Ratio 多线 + RS-rank 表 + breadth；点 bucket → N=1 + 成员 | compute, web | AC-M3 |
| **M4** | 主题分类：EDGAR + LLM 营收锚定 membership（point-in-time, human-in-loop）→ theme RS-Ratio 线 / 上色 | themes, compute | AC-M4 |
| **M5** | Valuation screener + Stock detail：duckdb-wasm 浏览器查询；per-name 面板 | export, web | AC-M5 |
| **M6** | 扩量：universe 由 ~500 扩到数千（Stooq bulk 已支撑） | ingest, compute | AC-M6 |
| **M7 ✅→⟲** | **base→breakout 发现引擎 + Breakouts（突破）榜**（§10.8）：原 M7 交付 ignition 发现引擎（`compute/ignition.py`，5 短窗口分量 + 横截面 + persistence + Discovery 持续点火榜），全 universe 实证 forward edge ≈ 0 因果 → **2026-06-16 转向 base→breakout**（LOG 价单变点 τ + 无量纲特征 + recall-first），ignition 退役。本 M 重定义为：base→breakout 引擎（`compute/breakout.py`）→ export top-N 候选 → Breakouts（突破）改造（base/τ/breakout 标注卡）→ Stock 衔接基本面/财务（precision 下游）。 | compute, export, web | AC-M7 |
| **M8 ✅→⟲** | **Ocean 重构 = base→breakout-strength × Valuation 二维相图**（§9.2）：原 M8 交付 Ignition × Valuation 海平面图（`export/ocean.py` v3、60 日 daily、海平面 ign_pct 90、log P/S 横轴、payload 拆分 bulk + per-stock 懒加载 detail，bulk brotli −83%）；**2026-06-16 随核心转 base→breakout**，Ocean 纵轴由 ign_pct 改为 base→breakout 强度（`brk_strength_pct`），candidate gate 由 ignition persistence 改为 base→breakout top-N。`ocean-draw.ts` / `Ocean.tsx` 复用既有 log 轴 + 插值 + payload 拆分骨架，仅替换纵轴语义与 candidate gate。**composite 早在 M8 退出用户可见层、现已完全退役**；Rotation league 聚合改 # breaking-out / # candidates。 | export, compute, web | AC-M8 |

**起手**：把 BUILD-PLAN 全文 + 本 PRD 当 kickoff，从 **M0**（~500 只跑通端到端）起，先证明数据拉得动、价格↔基本面 stack 直观（composite 为历史口径、已退役），再扩量；核心引擎按 §10.8 base→breakout 落地。

---

## 14. 验收标准 (Definition of Done)

- **AC-M0**：~500 只的 `daily_bars` + `fundamentals_q` 落地；`derived_daily`（趋势特征）与 `valuation_daily` 生成；抽查 5 只票，趋势特征方向与人工心算一致；估值 E≤0 正确退 n.m.。（注：原 AC-M0 校验 `derived_daily.composite` 5 分量——composite 已退役，§10.6。）
- **AC-M1**：web 静态构建成功；证据卡 board 渲染 evidence-card（≥18 张）；evidence-card 6 字段 + d/d（day-over-day）标注。（历史口径：M1 期 board 按 composite 排序、带 early⟷reliable 旋钮 + composite 角标；旋钮 M7 取消、composite 角标/d/d M8 移除，composite 与 ignition 此后均已退役——现 board 即 Breakouts/突破，按 base→breakout 强度排序，§9.3。）
- **AC-M2**（已被 AC-M8 取代）：Ocean v1 渲染 ≥500 点流畅；scrubber 切周；pin 一只 → trail+箭头；scope=sector 时非成员变淡（C10）；Ocean 点位与 Stock 数字一致（C9）。
- **AC-M3**：≥11 条 sector RS-Ratio 线叠图；league 表 4 态正确；点 bucket → N=1 单线（斜率着色）+ 成员卡。
- **AC-M4**：≥4 个主题有 point-in-time membership（含 exposure + approved_by）；改一条 membership 的 as_of → 历史不被回溯污染（C3）；theme RS-Ratio 线非市值加权（C4）。
- **AC-M5**：Valuation 表 duckdb-wasm 浏览器查询可排序；as-of 三档上色正确；percentile 仅 current-vintage（stale=vint）；Stock stack 四格共用 x 轴、季度网格贯穿。
- **AC-M6**：universe 扩到 ≥2000 只仍满足 AC-M2 性能（NFR-8）。
- **AC-M7**：`derived_daily` 含 base→breakout 特征（`brk_tau_date` · `brk_base_slope` · `brk_brk_slope` · `brk_drift_step` · `brk_fit_gain` · `brk_clearance` · `brk_vcp` · `brk_vsurge` · `brk_strength` · `brk_strength_pct`）；Breakouts（突破）按 base→breakout 强度 recall-first 排序取 top-N（假阳预期之内），非 composite/ignition 排序；evidence-card 头部露 base/τ/breakout 标注（flat base 段、估计变点 τ、陡突破段 + ceiling clearance / volume surge）；base→breakout 引擎与估值共用同一份 per-stock 数据（C9）；候选榜非空且与 board 同源可追溯。（注：原 AC-M7 校验 ignition 5 分量 + persistence「持续点火」——ignition 已退役，§10.8。）
- **AC-M8**：Ocean = base→breakout-strength × Valuation 二维相图 —— 默认显示 latest daily snapshot；纵轴 = base→breakout 强度（`brk_strength_pct`）；标记的候选股与 Breakouts（突破）候选语义一致（C9）；横轴 = 原始 P/S 的 log 轴（非 valuation percentile）；日期 slider 可手动切日；Play 自动播放且点在相邻真实 EOD 间**平滑插值**（不伪造交易日，tooltip 取真实快照）；**composite 与 ignition 不再出现在任何用户可见 UI**（Breakouts/Stock/Rotation/App）；`make ocean-c9`（brk_strength_pct/candidate/ps 同源）+ `make web-test` + `make web-build` 全过。（注：原 AC-M8 纵轴 = ign_pct 90 海平面——ignition 已退役，§10.8。）
- **横切**：每个 M 通过 `make verify`（两个 gate GATE_PASS）+ acceptance comment（§19）。

---

## 15. 显式 OUT OF SCOPE（防 scope creep）

intraday / real-time；auth / 多用户 / 支付；**非美上市标的**；**中文 cross-language 判定（本期 descoped）**；backtesting 引擎（验证信号有效性是独立的事，别掺进监控管线）；Ocean **无控/常驻全量** autoplay 动画（M8 的用户受控 Play/Pause + 相邻真实快照插值不在此列）；**email digest（暂不做，2026-06）**。

---

## 16. 已定死（code 不要再翻案）

> **AMENDMENT 2026-06-16（spine pivot）：** 核心引擎由 ignition 改为 **base→breakout**（log-price 单变点 τ + 无量纲特征、recall-first、无可调参，§10.8）；**ignition 与 composite 双双退役**；漏斗改为 **recall-first base→breakout 检测 → fundamentals/financial precision**（取代『触发→持续(persistence)→翻财报』）；Discovery tab 改名 **Breakouts（突破）**；Ocean trend 轴 = base→breakout STRENGTH。以下各条已就地修订反映此 pivot。

- spine：**base→breakout 发现引擎（核心，2026-06-16 spine pivot §10.8）+ valuation + raw evidence → 5 surface → 2 scale → 默认静态分发**（零后端从硬约束放宽为默认 §5.2；web 栈 = React+Vite+TS）。**composite 自 M8 退出全部用户可见层，2026-06-16 起与 ignition 一并全面退役**；唯一发现引擎 = base→breakout。
- 数据源：Stooq(EOD) + Nasdaq screener + EDGAR + yfinance(脆弱兜底)。
- 5 surface 行为 + evidence-first（**永不给 buy/target**；不露 composite，露原始证据 + ignition + valuation）。
- 数学：vol-normalized EWMAC、RS=双窗超额收益横截面百分位、trend=KER/OLS t 值；**核心发现数学 = base→breakout（log-price 2 段分段线性单变点 τ + 无量纲特征，§10.8）**。**composite=Σwᵢ·分量 与 ignition 均已退役（2026-06-16），不再驱动任何 surface；早⟷reliable 旋钮早已取消。**
- **核心引擎 = base→breakout（§10.8，2026-06-16 spine pivot 定调）**：NORTH STAR = 在 multi-bagger 长期上行的**早期**捕捉异动。数学 = 在 **log price** 上以 2 段分段线性 OLS 估计**单变点 τ**（τ 自适应估计，**无固定 base/breakout 窗口**），导出无量纲特征（÷ 日收益 σ）：base_slope/σ≈0（平台）、brk_slope/σ（陡升）、drift_step=(s2−s1)/σ（≳0.13，最强判别量、全市场中位≈0）、fit_gain=1−SSE2/SSE1（拐点显著度，≳0.7），外加 ceiling clearance、bar-level VCP、volume surge。**recall-first**：按 STRENGTH 排序取 top-N，**false positive 是预期的**——fundamentals/financial 才是下游 **precision** 阶段。参数最小（MINSEG、回看窗、recency band、退化守卫），**无任何用户可调旋钮**。**两级漏斗 = recall-first base→breakout 检测 → 基本面/财务终筛（precision）**（取代旧『触发→持续(persistence)→翻财报』）。**ignition（项目原『核心技术指标』，含瞬时点火 + persistence）已全面退役**——full-universe 实测其 forward edge ≈ 0 causal。**Discovery tab 改名「Breakouts（突破）」**。**Ocean trend 轴：ignition → base→breakout STRENGTH**（Ocean = base→breakout-strength × valuation 二维相图，§9.2）。
- **核心是 base→breakout**：不回测优化，买 robustness 不买 alpha；base→breakout **无可调参**（recall-first，false positive 交由下游基本面 precision 消化）。**ignition 与 composite 均已退役**——composite 自 M8 退出 UI，2026-06-16 起两台引擎一并全面退役；早⟷reliable 旋钮早已取消。
- 估值：price ÷ trailing-4Q 日频、**formal-filing PIT**（分母只用正式 SEC filing、ASOF 键 = `effective_eod_date`、`valuation_basis='formal_filing_pit'`；§10.5）、`E≤0→n.m.` 退 P/S、无 forward、百分位用 **common-vintage**（当前 fresh-cohort v1）；**Ocean = base→breakout STRENGTH（纵）× 原始 P/S log（横，非 percentile）二维相图**（§9.2，2026-06-16 spine pivot）。
- Rotation = **RS-Ratio 多线（非散点）**，league 聚合 **# breakout candidates**（非 composite 中位、非 # igniting——ignition 已退役）；**Ocean 轴固定 base→breakout STRENGTH × P/S(log) 二维相图**（2026-06-16 spine pivot；旧 ignition 海平面 / RS×Val / RRG-axes 均已砍，`rsr`/`rsm` 删）。
- 全局 scope（all|sector|theme|pinned）单一真源、跨 tab 粘滞、可见可一键清，4 surface 全 respond。
- point-in-time membership 硬要求；theme 指数非市值加权。

---

## 17. 留给实现的决策（非翻案）与开放问题

- **base→breakout 的实现级参数（开放）**：MINSEG（最小段长）、回看窗长度、recency band、退化守卫的具体取值，以及 STRENGTH 的特征组合方式（drift_step / fit_gain / brk_slope / ceiling clearance / VCP / volume surge）、top-N 的 N（§10.8）。trend 辅助量取 KER 还是 OLS t 值、Kalman 是否上（§10.3、§10.7）。（composite 固定权重常数已随 composite 退役而作废，2026-06-16。）
- **已定（2026-06-14）：early⟷reliable 旋钮取消。** 诊断为「假 early」（只在 composite 都滞后的分量间重配权、不引短窗口信号，§10.8）；全局不再有可拨旋钮。
- **已定（2026-06-16 spine pivot）：核心转 base→breakout，ignition 与 composite 双退役。** ignition（曾被定为项目核心，2026-06-14）实测 forward edge ≈ 0 causal（瞬时点火 + persistence 皆然），退役；composite 自 M8 退 UI、此次彻底退役。核心 = base→breakout（recall-first、无可调参，§10.8），false positive 由下游基本面/财务 precision 消化。
- theme membership 的营收阈值、LLM→human 审核流的具体形态（§8.3）。
- common-vintage 的 coverage 门槛具体 %（mock 用 ≤95 天近似，真实按「末季 ≥X% 已报」）（§10.5）。
- Ocean lasso 框选 set scope 的实现（mock 只做 respect/变淡）；Ocean 纵轴 = base→breakout STRENGTH 的归一/分箱与 candidate top-N gate 的客户端呈现（2026-06-16 spine pivot，§9.2）。
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
| **base→breakout** | **核心发现引擎**（2026-06-16）：LOG 价上估计单变点 τ（2 段分段线性 OLS）→ 长平 base 后陡突破；无量纲特征 + recall-first 取 top-N，假阳预期之内、基本面为下游 precision（§10.8） |
| **kink τ** | base→breakout 的估计单变点（changepoint）日期，2 段 OLS 拟合的转折点（τ 估计、无固定窗口；§10.8） |
| **drift_step** | `(s2−s1)/σ`，两段斜率差 ÷ daily-return σ；base→breakout 最强判别特征（≳0.13，universe 中位 ≈0；§10.8） |
| **fit_gain** | `1−SSE2/SSE1`，2 段相对 1 段 OLS 的 SSE 缩减 = 拐点显著度（kink salience，≳0.7；§10.8） |
| **漏斗（recall→precision）** | base→breakout recall-first 检测（取 top-N，假阳预期之内）→ 基本面 / 财务作 precision 终筛（§10.8；取代旧「ignition 触发 → persistence → 翻财报」三级漏斗） |
| **composite** ~~(已退役 2026-06-16)~~ | per-stock 综合分 `100·Σwᵢ·分量`（§10.6）；曾为确认引擎，**已完全退役**（先于 M8 退 UI，2026-06-16 退计算层）；保留仅 cross-ref |
| **ignition** ~~(已退役 2026-06-16)~~ | 曾为发现引擎：5 短窗口分量横截面综合（瞬时 + persistence，§10.8）；实证 forward edge ≈ 0 因果 → 由 base→breakout 取代；保留仅 cross-ref |
| **persistence** ~~(随 ignition 退役)~~ | 曾为 ignition 点火后连续 ~5 日仍在 top decile 的精度过滤（§10.8）；不再使用，保留仅 cross-ref |
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

**base→breakout 字段（§10.8，核心引擎）**：`brk_tau_date`(估计单变点 τ 日期) · `brk_base_slope`(base 段斜率/σ，≈0 flat) · `brk_brk_slope`(breakout 段斜率/σ，陡) · `brk_drift_step`((s2−s1)/σ，最强判别，≳0.13) · `brk_fit_gain`(1−SSE2/SSE1，拐点显著度，≳0.7) · `brk_clearance`(ceiling clearance：价是否清越 base 高) · `brk_vcp`(bar-level VCP：base ATR 收缩 → breakout 扩张) · `brk_vsurge`(volume surge) · `brk_strength`(综合强度) · `brk_strength_pct`(横截面 pct)。

**~~composite 5 分量~~（已退役 2026-06-16，§10.6）**：`rs_pct` · `high_proximity` · `trend_quality` · `volume` · `rs_accel`。

**~~ignition 5 分量~~（已退役 2026-06-16，§10.8）**：`ig_accel` · `ig_expand` · `ig_vsurge` · `ig_breakout` · `ig_rsturn` → `ignition` / `ign_pct` / `ign_persist_days`。

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
**base→breakout 强度（brk_strength_pct）**：≥90（已突破，海平面上）绿 · ≥80 琥珀 · <80 暗灰。（composite 分色已随 composite 退役作废。）

---

*本 PRD 是活文档。任何需求/边界变化先回写本文件，再继续实现（见 §19 工作流）。*
