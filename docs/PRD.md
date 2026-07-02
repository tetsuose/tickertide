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

**单一核心筛法 = steady-riser（连续上涨）+ valuation + raw evidence，五个 lens，两个尺度，默认静态分发。**
- **steady-riser（核心筛法，§10.8，2026-07-02 spine pivot）**：把「每天扫几千张 K 线找过去一两周持续走高、回撤少的票」直接数学化——W=10 天的净涨幅 / 上涨天数占比 / 窗口内最大回撤 / 路径效率，全部**图上可逐一核对**。gate=`10 天里 ≥6 天上涨且净涨 >0`、按 10 日净涨幅排序取 top-N。**简单、不易出错、方便验证（与直观相符）；不指向预测收益**（recall 工具，precision 归用户翻财报）。驱动 Risers（连续上涨）榜 + Ocean 纵轴（§9.2）。
- **valuation（横截面估值，§10.5）**：原始倍数（P/S / EV/S / P/E / EV/EBITDA），驱动 Ocean 横轴 + Valuation screener + Rotation/Stock 估值。
- **base→breakout / ignition / composite 均已退役（§10.6、§10.9）**：base→breakout（变点拟合）复杂、难以在图上直接验证、且实测偏向已涨数月的老突破（榜单中位突破在 ~7.5 月前，违背「初期一两周发现」的北极星）；ignition forward edge ≈ 0；composite 系统性滞后。三者皆不再计算/导出/驱动任何 surface；对应章节仅保留为历史与 cross-ref 锚点。

旧表述「base→breakout 是唯一核心探测引擎 / composite 驱动 Ocean / ignition 是项目核心 / 双引擎并列」均已废弃（spine pivot 2026-06-16 → **2026-07-02 二次换芯**）。

核心筛法**与 valuation 共用同一份 per-stock 数据**（C9），离线预计算 + 静态分发。steady-riser 测的是「过去一两周是否持续走高、回撤多深」这一个**直接可观察量**（无变点拟合、无横截面合成分、每个数字在 K 线图上 10 秒内可人工复核；§10.8，实证 `analysis/steady_riser.py` exp 10）。

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
- **要么是滞后的确认引擎** —— 等 RS 进前列 / 创新高 / 趋势变干净才点亮（IBD / Minervini 谱系），那时 emerging leader 已经涨完大半。本工具核心 = steady-riser（§10.8）：过去一两周持续走高即上榜，实证（exp 10）SNDK/SOXL/ARM/MRVL/AAOI/CRDO/SITM 型大涨票全部在起涨低点后 **0–10 个交易日**内进榜。
- **要么是复杂到无法验证的模型** —— 变点拟合 / 机器学习分数，用户无法在图上核对它为什么亮。本工具的每个数字（净涨幅、上涨天数、窗口回撤）都能在 K 线图上人工数出来（**与直观相符**，这是硬要求）。

### 2.2 本工具的立场

- **evidence-first**：默认露原始证据（涨幅、距高点、量比、估值倍数、base/τ/breakout 标注），**永不给 buy / target**。
- **核心是 steady-riser（§10.8，2026-07-02）**：唯一核心筛法 = 过去 10 天净涨幅 + 上涨天数占比 + 窗口内回撤 + 路径效率，**无可调 alpha 参**（W=10、up≥6/10、top-N 是 UX 常数非拟合量，刻意=**买 robustness/stability，不买 alpha**）；recall-first 取 top-N，假阳交由下游基本面/财务 precision（**后期下跌的入选也没关系**——这是 recall 工具的定义而非缺陷）。**base→breakout、ignition、composite 均已退役**（§16）。
- **两个尺度解耦**：用来「逛」的 wide explore 和用来「动手」的 bounded decide 是不同界面，互不取代。
- **相对永远配绝对读**：RS-Ratio 只讲相对，必须与绝对走势（价格 / 连续上涨上下文）并置。

---

## 3. 目标用户与核心用例

### 3.1 用户

核心用户：具备量化/技术分析素养、盘后做美股研究与决策的投资者。当前不做 auth / 支付 / 团队协作。

### 3.2 核心用例

| # | 用例 | 尺度 | 主 surface |
|---|---|---|---|
| UC1 | 盘后扫一遍全市场，找「便宜且在转强」的票 | wide/explore | Ocean |
| UC2 | 看哪些 sector/theme 在轮动换手、谁在 leading | bounded/decide | Rotation |
| UC3 | 拿到一份 evidence-first 候选清单，逐张看证据（净涨幅/上涨天数/窗口回撤）决定动手 | bounded/decide | Risers |
| UC4 | 按估值倍数横截面筛选（在 sector/theme 内比 percentile） | wide/explore | Valuation |
| UC5 | 钻进单只票，看价格↔基本面时间轴对齐、判断「赚到这波 vs 变贵无基本面」 | narrow | Stock |
| UC6 | 看 base→breakout 候选（核心发现引擎：长平台 base → 陡峭 breakout），每卡读原始证据 + base/τ/breakout 标注（无 composite/ignition，均已退役） | bounded/decide | Breakouts |
| UC7 | 锁定一个 sector/theme scope，所有 wide surface 同步过滤到该范围 | 全局 | scope filter |

---

## 4. 产品原则（脊柱，贯穿所有 surface）

**P1 — 单一核心筛法共用一份数据，不写五条独立管线。** steady-riser 筛法（§10.8）与 valuation（§10.5）共用同一份 per-stock 数据（C9）。
- **Risers（连续上涨）** = gate + net10 排序；**Rotation** = RS-Ratio 按 bucket group-by（league 含 riser 候选数聚合）；**Ocean** = 连续上涨强度 × valuation 二维相图（§9.2）；**Valuation** = 估值的 cross-section；**Stock** = 单票展开（riser 窗口标注的价格走势 + 估值时间轴）。

**P2 — 两个尺度。**
- **wide / explore**：Ocean、Valuation screener —— 数千只，用来逛。
- **bounded / decide**：Risers（候选）、Rotation（~10–12 桶）—— 用来动手。

**P3 — 核心引擎参数最小化、无可调旋钮。** base→breakout（§10.8）参数最小（MINSEG、lookback 窗口、recency band、退化守卫），**无任何用户可调旋钮**——刻意=买 robustness/stability，不买 alpha。`early⟷reliable` 旋钮、ignition、composite 均已退役（§16/§17）。

**P4 — evidence-first，永不黑箱。** card/surface 默认露原始数字 + base/τ/breakout 证据（drift_step / fit_gain 等无量纲特征，§10.8）；永不给 buy/target。（composite 可展开角标已随 composite 退役，2026-06-16。）

**P5 — 数据一致性。** 五个 surface 的所有数字必须从同一份 per-stock 数据派生，同一只票在任何 surface 上对得上、可互相追溯（见 §7-9）。

**P6 — 相对配绝对。** RS-Ratio 只讲相对强度，永远与绝对走势（价格 / 连续上涨上下文）并置读。

**P7 — 单核心引擎 + recall-first 漏斗。** base→breakout 答「是否处于 multi-bagger 长期上行的早期（长平台后的陡变点）」（§10.8）——这是项目唯一的核心探测引擎。recall-first：先取 top-N（假阳是预期的），**基本面 / 财务分析是下游 precision 级**（取代旧的「触发→持续→翻财报」persistence 漏斗）。ignition（瞬时 + persistence，forward edge ≈ 0）与 composite（系统性滞后）均已退役；`early⟷reliable` 旋钮亦已取消（§16/§17）。

---

## 5. 系统架构

### 5.1 范式：离线预计算 + 静态分发（fomo5000）

```
GitHub Actions (nightly cron, post-US-close)
  └─ ingest (Python):  Stooq (bulk EOD) + Nasdaq screener (universe/cap/sector/PE) + SEC EDGAR (fundamentals/segment)
  └─ compute (DuckDB): derived_daily + steady-riser(净涨幅/上涨天数/窗口回撤) + RS-Ratio 序列 + theme membership + percentiles(common-vintage) + ASOF valuation
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
- **C9 — 所有 surface 来自单一 per-stock 引擎。** Ocean 的 `(rise_net10_pct, ps)` 位置（连续上涨强度 × P/S，§9.2）、Stock 的价格/财务、Risers（连续上涨）候选卡、Valuation 行必须从同一份底层 per-stock 数据（`derived_daily` / `valuation_daily` / `daily_bars` / `universe`）派生，可互相追溯（前端永不重算引擎；candidate flag 由 compute 一次算出、边界处绝不用舍入值重推——#92–#94 教训）。（mock 现状是两套独立合成系统对不上；真实管线禁止此分裂。）
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
- **五个 tab**（胶囊按钮，选中高亮绿 `#2ec07a`）：`Ocean` · `Risers` · `Rotation` · `Valuation` · `Stock`。单击即切。
- **顶部控制栏两部分**：tab 组 · scope 过滤条（仅 scope≠all 时出现）。（无可拨旋钮——核心是 base→breakout、无可调参；旁附一行引擎说明「BASE→BREAKOUT = 发现核心引擎（长平台 base → 陡峭 breakout，τ 估计，无可调参） · composite/ignition 均已退役」。）
- **字体**：显示用 `Saira Semi Condensed`；数据用 `IBM Plex Mono`。

### 9.1 全局原语

**9.1.1 核心筛法 = steady-riser（无旋钮）**
- 全局**无可拨旋钮**：`early⟷reliable` 旋钮已取消（假 early，§16）；核心 = steady-riser，常数为产品语义常数（W=10、up≥6/10、N=50）、无可调 alpha 参（刻意，买 robustness 不买 alpha）。
- riser 指标与 candidate flag 在引擎离线算好（§10.8），前端**不重算**、直接读导出值（C9）。
- evidence-first（P4）：卡片 / Stock 露 base/τ/breakout 的原始价格行为 + 无量纲特征（drift_step / fit_gain 等），永不黑箱、永不给 buy/target。
- **composite 与 ignition 均已退役**（§16）：不再露角标、不再驱动任何 surface。

**9.1.2 global scope filter（C8、C10）**
- 状态 = `{ all | sector:X | theme:Y | pinned }`，**单一真源**。
- UI：scope≠all 时显示 chip `Scope: ● <名称> ✕`，副标 `filtering Risers · Valuation · Rotation · Ocean`。
- **写入口**（都写同一个 scope，后写覆盖）：Rotation 点表行/线、Valuation 下拉、Ocean 框选/点击。
- **sticky**：切 tab 不 reset；只有显式换或点 `✕` 才清。
- **respond**：Risers / Valuation / Rotation / Ocean；**Stock 是 per-name，不受 scope 影响**。
- **解耦**：「改 scope」与「换 view」是两个独立动作（点 sector 只 set scope + 原地展开 panel，不 auto-jump）。

**9.1.3 evidence-card = Stock 的 collapsed 态（一个对象，两种渲染密度）**
- **collapsed = evidence-card**（扫描态：密、多、浅）：price+volume+MA mini 图（叠加 base/τ/breakout 标注）+ 6 个**原始数字**（摊开，非 percentile）+ 头部 base→breakout 状态（🚀 已突破 + τ 距今 / 否则 brk_pct 角标）+ base→breakout 证据条 + AI「why moving」占位格。**无 composite / ignition 角标（均已退役）。**
- **expanded = Stock**（详情态：全、单、深）：§9.6 完整视图。
- 点任意 card → 展开成 Stock。**不要把两者当两个东西做。**
- card 字段 = **6 个原始数字**：原始涨幅 1M / 3M / 6M、距 52w high %、突破后第几周、量/均量 `×`、（外加 market cap 在头部）。密度 = 一屏 3–4 张大卡（2 列网格）。

### 9.2 Ocean（canvas，wide explore）—— 连续上涨强度 × Valuation 二维相图（海平面图）

> **重构史**：Ocean 从旧的「RS percentile × Valuation percentile 周度散点」（M2）改为 daily 海平面图；M8 纵轴曾是 ignition 百分位、2026-06-16 改 base→breakout 强度。**2026-07-02 二次换芯后**：纵轴改为 **10 日净涨幅的横截面百分位 `rise_net10_pct`**（§10.8）——「过去两周谁涨得多、贵不贵」，纵轴语义直接可读（图上可验证）。旧设计见 ROADMAP history。

- **渲染**：一个 EOD daily cross-section，数千只股票的 canvas 散点。
- **轴固定**：
  - **y = rise_net10_pct**（10 日净涨幅横截面百分位 0–100，§10.8）。一条固定**海平面 = 90**（top decile，仅视觉参考线：过去两周涨幅进全市场前 10%）。海平面以上区域轻微高亮、以下压暗。
  - **x = 原始 trailing P/S TTM**（`ps`），**log 轴**。**不用 valuation percentile 做默认横轴**，不引入估值综合分或隐含阈值参数（§16）。`x_domain` 由导出窗口内所有有效 P/S 自动算出，供 log scale。
- **candidate 语义（2026-07-02 spine pivot）**：candidate = **Risers 榜同一道 gate+排序**（`rise_up10≥0.6 AND rise_net10>0`、net10 排序 top-N，§10.8），**flag 由 compute 层一次算出写 `derived_daily.rise_candidate`，export/前端只读绝不重算**（C9 单一真源——沿 #92–#94 舍入边界教训）。candidate 点与 Risers（连续上涨）榜逐票可追溯；candidate 不等价于「y≥90」（gate 含 up10 条件、且 top-N 截断），海平面线只是视觉参考。**recall-first 刻意放宽：false positive 是预期的，下游 fundamentals/financial 分析才是 precision 阶段。**
- **color**（两模式可切）：sector / theme（选定主题：成员正常、非成员极淡）。candidate 点（连续上涨榜内）加光晕 + 亮环；海平面以上点 solid bright、以下更暗。
- **size** = market cap（半径随 sqrt(mktcap)，clamp 1.6–11px）。
- **时间轴（日期滑杆 + 播放）**：图下方日期 slider 在不同 EOD 之间切换，**默认打开 latest EOD**。Play/Pause + prev/next；**Play 自动播放**时每支股票的点在**相邻真实 EOD 快照之间用视觉插值平滑移动**（rAF，每两日 ~900–1200ms，到最新日自动停）。**插值仅用于视觉动画，不伪造中间交易日数据**：tooltip 与状态恒取真实 snapshot。拖动 slider 暂停播放并切到对应日期（phase 归零）。
- **交互**：
  - hover → nearest-neighbor 显示 tip（ticker / sector / rise_net10_pct / net5·net10·net20 / 上涨天数 up10 / 窗口回撤 ddw10 / 连续在榜天数 / candidate / P/S / EV/S / P/E / EV/EBITDA / valuation freshness / mktcap / themes）。hover 命中用**当前绘制后的插值位置**。其中 rise_net10_pct / candidate / P/S 三个绘制字段来自 bulk 即时可见，其余证据字段按票**懒加载**（见下「payload」，首次 hover 显骨架 `…`）。
  - click → toggle **pin**（pinned 点高亮 + 标签，仅 ≤ cap 时标 ticker，C2）。
  - 框选（lasso）→ **set 全局 scope**（Ocean 是 scope 的第一个写入口，C10）。
- **respect scope**（C10）：非 scope 点 filter 掉或大幅变淡（in-scope ~0.5–0.92 按是否点亮，out ~0.06）。
- **已砍**：旧 RS×Val 轴、(50,50) 十字线、quadrant 配色、周度 WEEK scrubber、pinned 多周 trail/箭头（时间维度由播放动画承担）；更早砍掉的 RRG-axes（`rsr`/`rsm` 字段早已删除）。
- **payload（schema v3，体积裁剪 / 为 M6 扩量铺路）**：每帧绘制只需 3 个字段（`ps` / `rise_net10_pct` / `candidate`），其余仅 tooltip 字段实测占压缩体积 ~79%。故 `ocean.json` 拆两层：**bulk**（`ocean.json`，每票仅三绘制字段的 columnar 数组、与 `dates[]` 同索引、全员前置下载）+ **per-stock detail**（`ocean/<TICKER>.json`，9 个 tooltip 字段 columnar、hover 时按票懒加载——只下你真去看的票）。实测 top-500 bulk brotli ≈ **100KB**（旧 v2 整合 596KB → −83%）。**勘误**：旧文写的「ocean gzip ~1.5MB」是 **board.json** 的数；ocean v2 实测 gzip 866KB / brotli 596KB。**board.json 现已同法拆分（schema v2，见 §9.3）**：full brotli ~1.20MB → bulk ~51KB + 懒加载 90d chart。M6 全量后 bulk 仍只随票数 ×3 字段增长、detail 永远按需，故可扛数千只。两文件 columnar 且按 `dates[]` 同索引对齐、全字段 C9 同源（`derived_daily` / `valuation_daily` / `daily_bars` / `universe`）；`make ocean-c9` 额外校验 bulk↔detail 一致（bulk `cand` == derived `rise_candidate`、detail 证据字段追溯 board）。**渲染行为不变**：海平面图 / 轴 / candidate 高亮 / 插值动画结构完全一致，仅纵轴语义改为 `rise_net10_pct`（2026-07-02 换芯）、candidate 读 `derived_daily.rise_candidate`（不再由 y 值推导）；首次 hover 某票仍多一次取数（tooltip 先显 3 个已知字段 + 骨架）。C9 校验相应改为：bulk `cand` == derived `rise_candidate`、detail 证据字段追溯 board。

### 9.3 Risers（连续上涨）（evidence-first 卡流，bounded decide）

- **渲染**：2 列 evidence-card 网格，**按 10 日净涨幅排序、gate=10 天里 ≥6 天上涨**（§10.8，2026-07-02 spine pivot；recall-first，取 top-N）—— 不是 breakout / composite / ignition 排序（均已退役，§16）。这一屏的本质是 **逐张检视「过去两周持续走高」候选的价格动作**——等价于人工每天扫几千张 K 线，只是数学做了预筛。卡片为 evidence-first（每个数字都能在 mini-chart 上人工数出来）。
- **候选池 = 两级漏斗**（§10.8）：① **recall-first steady-riser 筛选**——gate `rise_up10≥0.6 AND rise_net10>0`、按 `rise_net10` 降序取 top-N（N=50，UX 常数）→ 上榜（**false positive 是预期的，后期下跌的入选也没关系**——刻意 recall-first）；② **基本面/财务终筛（precision，human）**——用户在 Stock 翻财报消化误报。**无任何可调 alpha 参**；平滑度（ker/ddw）**绝不做硬 gate**（exp 10 反例：严平滑 gate 把 SNDK 挡到 d66——真火箭初期不平滑），只做证据列供用户自行收紧。
- **riser 证据列**：卡片突出图上可验证的证据——`10 日净涨 +X%`、`上涨天数 8/10`、`窗口内最大回撤 −Y%`、`路径效率 ker`、`5 日 / 20 日净涨`（短/长两侧参照窗）、`连续在榜 N 天`（streak，描述非过滤）——衔接「为什么现在值得看」→ 接 Stock 翻财报做 precision 级筛选。
- **每张卡** = §9.1.3 evidence-card：
  - 头部：ticker + `(sector · $XXB mktcap)` + riser 状态（📈 连续上涨 + 在榜天数 / 净涨幅角标）。
  - theme tags（若有）。
  - MiniChart：90 日 K 线 + MA50/150/200 + 成交量 + 52w 高虚线，**高亮最近 10 个交易日窗口**（riser 窗口区段着色，用户可直接数上涨天数核对 up10）。卡片渲染时显示骨架占位，chart 到位后填入（懒加载，见下）。
  - 证据字段行：net5 / net10 / net20 / up10（8/10）/ ddw10 / vol×（涨绿跌红）。
  - 「why moving」AI 占位格。
- **payload（schema v2，体积裁剪 —— ocean v3 同法落到 board）**：90d mini-chart 实测占 board.json raw 体积 ~96%，而 Risers 是 bounded（App 截 top-20），同屏只 ~20 张图。故拆两层：**bulk**（`board.json`，每票卡面数据但**不含 chart**、全员前置下载，仍带 Risers 排序「rise_net10 + gate」+ 跨全 universe scope filter 所需的全部字段）+ **per-stock chart**（`board/<TICKER>.json`，仅该票 90d mini-chart，卡片渲染时按票懒加载——只下你真看到的票）。实测 full board brotli ~1.20MB → bulk ~51KB + 20×~2.5KB ≈ **101KB 首屏（−92%）**。bulk 与 chart **同一遍构建、同源 `daily_bars`（C9，拆分只改 chart 存放位置不改其值）**；纯 columnar 不做（chart 本就并列数组、剥离后 bulk 已 ~51KB，再 columnar 收益可忽略——同 ocean 教训）。不复用 `stock/<T>.json`（那是 2y bundle，复用首屏 223KB 且 high_52w 窗口不符要客户端重算）。
- **交互**：点卡任意处 → 打开 Stock。（无 composite 展开面板，M8。）
- **respect scope**：先 filter 再排序。

### 9.4 Rotation（narrow decide）

- **总览（scope=all）**：
  - **所有 sector/theme 的 RS-Ratio 多线图（非散点）**：height=level（>100 跑赢 SPY）、slope=momentum（走平=中性）、线交叉=leadership 换手。基线 y=100。hover 高亮一条、其余变淡；右缘按末值排序贴标签防重叠。
  - **enriched league 表**（按 RS-Ratio level 排序）：`# | bucket | RS-Ratio | Δ4w(=斜率/momentum) | state`，外加 breadth(%>MA50 / %>MA200)、#at-52w-high、# riser 候选、agg EV/S、多 horizon relative return。state 由 level+slope 推回四态：**LEADING**(≥100,↑) / **WEAKENING**(≥100,↓) / **IMPROVING**(<100,↑) / **LAGGING**(<100,↓)。
  - **GICS ↔ Theme 切换**。
- **钻进（点表行/线 → set scope + 钻进该 bucket，inline drawer 非新 tab）**：
  - **N=1 单线放大**：单 bucket 的 RS-Ratio 折线，**线色=斜率**（升绿/降红，N=1 时 color 空出来给斜率）。
  - **sector 聚合 summary**（唯一真正新内容，filter 得不到）：breadth、dispersion、aggregate valuation、#at-52w-high、sector RS trail。
  - **成员预览**：Risers 同款 evidence-card（top-N），每张 → Stock；按钮「在 Ocean / Valuation / Risers 看全部成员」= set scope + 跳转。
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
- **下接**：6 个估值指标卡（P/S · EV/S · EV/EBITDA · P/E · Rev growth · Rule of 40）+ **riser 诊断**（net5 / net10 / net20 · up10 上涨天数 · ddw10 窗口回撤 · ker10 路径效率 · 连续在榜天数；10 日窗口区段标在价格轴上，用户可对图逐项核对）+ theme memberships(+exposure) + 最新 filing AI 摘要。**无 breakout / composite / ignition 分量序列（均已退役）。**
- **头部**：ticker + `sector · $XXB` + theme chips（带 exposure %）+ **10 日净涨幅大数字**（`rise_net10`；发现核心；candidate（榜内）时绿）。
- **入口**：card 点开落地 / 顶部下拉按 ticker 直接查（per-name，**不受 scope 影响**）。

### 9.7 配色与视觉语言

见附录 C。核心：绿 `#2ec07a`(正向/leading) · 红 `#ff5d57`(负向/lagging) · 琥珀 `#e0a02e`(weakening/中性偏弱) · 蓝 `#5197ff`(improving/MA50/weight bar)。象限、11 sector、8 theme 各有固定色；连续上涨强度（rise_net10_pct）海平面以上（≥90）绿 / 接近海平面（≥80）琥珀 / else 暗灰；candidate（榜内）高亮环（breakout / composite 分色均已退役）。

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
- **EBITDA 口径（best-effort，§10.5）**：`EBITDA = EBIT + D&A`。EBIT 优先 `OperatingIncomeLoss`，缺则退 `pretax income + interest`(≈EBIT；KLA 等 2015 后弃用 OperatingIncomeLoss tag、`GrossProfit` 也断档)。D&A 单季由 **YTD 差分**还原(现金流量表 D&A 多为累计 YTD：Q2=H1−Q1、Q3=9M−H1、Q4=FY−9M)，否则季度 EV/EBITDA/margin/rule40 全缺(EBITDA 同时驱动这三者)。D&A 优先**合并** concept(`DepreciationDepletionAndAmortization` 系，跨年同义切换 merge)；合并标签缺则退 **component-sum**(`Depreciation` + `AmortizationOfIntangibleAssets`，如 MSFT 折旧/摊销分项报、无合并标签)——漏现金流 'and other'(~3%、运营/融资租赁等无干净单标签)、EBITDA 略偏小、margin 误差<1%，best-effort。绝不单用 component `Depreciation`(漏摊销失真)。AC=`compute/ebitda_check.py`。
- P/S 看 **level + expansion（相对起点/行业中位）+ percentile**，别只看 level。
- **跨行业比较**优先 EV/EBIT（P/E 受杠杆扭曲）。横截面约束 = 方法一致（全票同算法）。
- **as-of 同步（数据完整性）**：横截面每个倍数用该票**最新可得** trailing-4Q（永不取未来季；ASOF 键 = `effective_eod_date` 而非 `period_end` = anti-lookahead），但各票窗口截止日不同（财报时滞 10-Q ~40/45 天、10-K ~60/75/90 天 + off-calendar 财年）→ **必须暴露 as-of 日并分档上色**（§9.5）：fresh / stale / n.m.。新鲜度按「最新**季末**距今天数」定义（`date − period_end`，>~95 天 = 落后一季 = flag；与披露滞后 `filed − period_end` 是两个量，后者另列 `disclosure_lag_days`）。
- **横截面 percentile = common-vintage**：percentile 是相对统计，只有同 vintage 才有效。**绝对 multiple** 用最新可得（fresh，显示+标记）；**percentile/排名**用「该 peer 集 ≥X%(如 50%)已报出的最近季末」为共同基准，覆盖率没过线则基准停在上一季 → **孤单先发报者不移动基准**。绝不拿先发者的新季数去排别人的旧季数。**当前实现 = fresh-cohort v1**：只在 fresh cohort（as-of ≤~95d）内排名、stale 不进分母；完整的「peer 覆盖率门槛后才切共同 vintage」为后续（§13）。

### 10.6 composite（已退役 — RETIRED）

> **状态（2026-06-16 spine pivot）：composite 已完全退役。** 它是趋势**确认**引擎（5 分量全是长窗口 / 测水平），数学上系统性滞后于「早期」，无法服务北极星。M8 已退出全部用户可见层；本次进一步退役，**不再计算、不再导出、不再驱动任何 surface**。本节仅保留为历史与 cross-ref 锚点，勿据此实现新代码。核心筛法见 §10.8（steady-riser）。

（历史口径，供追溯，**不再生效**）`score = 100 · Σ wᵢ · componentᵢ`，components ∈[0,1] = `rs_pct` / `high_proximity = close/rolling_max(close,252)` / `trend_quality` / `volume` / `rs_accel`；固定 `k=0.5` 权重曲线 `rs=.215, high=.22, trend=.17, vol=.12, accel=.275`。`early⟷reliable` 旋钮早已取消。

### 10.7 (optional) Kalman level+slope

要日间稳定 / 无丑跳变时再上：对 RS line 做 `rs≈level`、`slope` 变化，`slope/√var` 做 z-score。**不是关键路径**，也不是核心筛法的一部分（核心 = §10.8 steady-riser）。

### 10.8 steady-riser 引擎（核心筛法，单引擎，2026-07-02 spine pivot）

> **为什么换 steady-riser、为什么 base→breakout 退役（已定 2026-07-02，用户拍板 + exp 10 实证）：** 用户对算法的三条硬要求——**简单、不易出错、方便验证（与直观相符）**，且**不指向预测收益**；产品语义 = 把「每天扫几千张 K 线找过去一两周持续走高、回撤少的票」数学化提效。base→breakout（变点拟合）违背前三条：分段 OLS + τ 扫描无法在图上人工核对，且实测榜单偏向已涨数月的老突破（候选中位突破在 ~7.5 月前），违背「初期一两周发现」。exp 10（`analysis/steady_riser.py`）实测 steady-riser 把 SNDK/SOXL/ARM/MRVL/AAOI/CRDO/SITM（整段 +245%~+2376%）全部在起涨低点后 **0–10 个交易日**内送进 top-50。**结论**：steady-riser 成为项目**唯一**核心筛法，无任何可调 alpha 参。

**10.8.1 指标（W=10 主窗，全部图上可读、O(W) 算术、无拟合）：** 设 `δ_t` = 日 log return。对每只票每日算：
1. **净涨幅** `rise_net5 / rise_net10 / rise_net20` = `close_t / close_{t−k} − 1`（k=5/10/20；10 为主窗=「过去两周」，5/20 为短/长参照证据列）。
2. **上涨天数占比** `rise_up10` = 近 10 个交易日中 `δ>0` 的天数 ÷ 10（**数绿蜡烛**，最直观的「连续上涨」定义）。
3. **窗口内最大回撤** `rise_ddw10` = 近 10 日窗口（11 个收盘价）内相对窗口滚动峰值的最大回撤（≤0；「回撤少」的直读量）。
4. **路径效率** `rise_ker10` = `|Σδ| / Σ|δ|` ∈[0,1]（Kaufman ER；1 = 直线上行）。

**10.8.2 gate + 排序（榜的定义）：**
- **gate**：`rise_up10 ≥ 0.6 AND rise_net10 > 0`（10 天里至少 6 天在涨且净涨为正）。
- **排序**：gate 通过者按 `rise_net10` 降序，取 **top-N（N=50，UX 常数）** → `rise_candidate = 1`。
- **streak** `rise_streak_days` = 连续处于 candidate 的天数（islands 计数；描述性证据列，**不做过滤**）。
- **横截面百分位** `rise_net10_pct` = `rise_net10` 的每日横截面 percentile（0–100，驱动 Ocean 纵轴 §9.2）。
- **candidate 单一真源（C9）**：flag 在 compute 层一次算出写 `derived_daily.rise_candidate`；export / 前端只读，**绝不在边界用舍入值 / y 轴值重推**（#92–#94 舍入边界教训）。

**10.8.3 平滑度绝不做硬 gate（exp 10 反例，定死）：** 严平滑 gate（`ker≥0.6 & ddw≥−5%`）把 SNDK 挡到 **d66（已涨 +155%）**——真火箭初期往往跳空、急拉、深回踩（SNDK 起涨期 ker .25–.52、窗口回撤 −11%）。`up10` 是最宽容且直观的垃圾地板；`ker10` / `ddw10` 只做**证据列 / 用户自行收紧的 UI 过滤**，引擎层绝不硬编码。

**10.8.4 recall-first 漏斗（产品形态，沿用）：**
1. **steady-riser 筛选**（recall-first）→ 榜单 top-N。**假阳是预期的、后期下跌的入选也没关系**（recall 工具的定义）。
2. **基本面 / 财务 precision**（下游）→ 用户在 Stock 翻财报筛除假阳。

**10.8.5 常数（UX 常数、非拟合量、无旋钮）：** `W=10`（=「一两周」）、参照窗 5/20、gate `up≥6/10`、`N=50`。这些是产品语义常数（exp 10 中 ±几档结果不敏感），**不做回测优化**。实证 `analysis/steady_riser.py`（exp 10，含五变体对比 + SNDK 诊断）。

> **诚实定调（同 §10「买 robustness 不买 alpha」）：** 本筛法**不声称任何前向收益**——exp 10 实测 picks 前向 21d 中位 +1.4% vs 全池 +1.1%（≈无差异）；exp 2 早已证明短窗涨幅排序偏 short-term reversal。它的价值是**效率**（替代人工扫几千张图）与**召回**（大涨票起涨初期必然满足「在涨」这一同义反复式条件——这正是「与直观相符」的含义），不是选股 alpha。edge 归用户的基本面判断（exp 1–9 元结论）。

### 10.9 base→breakout（已退役 — RETIRED）

> **状态（2026-07-02 spine pivot）：base→breakout 已完全退役**——不再计算、不再导出、不再驱动任何 surface。退役理由见 §10.8 引言（复杂/图上不可验证/偏老突破）。本节仅保留为历史与 cross-ref 锚点，勿据此实现新代码。
>
> （历史口径，供追溯，**不再生效**）在 log 价格上以 2 段分段线性 OLS 估计单变点 τ（长平台 base → 陡 breakout），无量纲特征 ÷ 日收益 σ：`base_slope/σ≈0`、`brk_slope/σ`、`drift_step=(s2−s1)/σ`（≳0.13 主判别）、`fit_gain=1−SSE2/SSE1`（≳0.7）、ceiling clearance、bar-level VCP、volume surge；`strength = fit_gain · max(0,drift_step) · exp(−1.5·|base_slope/σ|)` → 横截面 pct `brk_strength_pct`、candidate=pct≥90。常数 H≈504、MINSEG≈40、recency band 15–252 bar。实证原型 `analysis/base_breakout*` 系；OOS `analysis/walkforward_breakout.py`（forward edge 弱且 regime-dependent）。曾于 2026-06-16 pivot 取代 ignition/composite 成为核心（AMENDMENT 见 §16），2026-07-02 由 steady-riser 取代。

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
| FR-8 | Ocean：canvas 散点、固定 rise_net10_pct × P/S(log) 二维相图轴、日期滑杆 + 受控 Play 插值动画、pin/lasso→scope、respect scope | §9.2 |
| FR-9 | Breakouts（突破，原 Discovery）：检视所选候选的价格行为，标注 base / τ / breakout；evidence-first、AI 兜底候选；不露 composite/ignition（均已退役） | §9.3 |
| FR-10 | Rotation：RS-Ratio 多线 + enriched league 表 + GICS/Theme 切换 + 钻进 | §9.4 |
| FR-11 | Valuation：横截面 screener、duckdb-wasm 查询、as-of 上色、scope 过滤 | §9.5 |
| FR-12 | Stock：price↔fundamentals 时间轴对齐 stack + 估值/分量/membership | §9.6 |
| FR-13 | ~~composite 确认副读~~（**已退役**，2026-06-16）：不再驱动任何 surface、不再露角标、不再有旋钮（early⟷reliable 早已取消）；保留条目仅为 cross-ref | §10.6, §16 |
| FR-14 | global scope filter：单一真源、跨 tab 粘滞、可见可一键清、4 surface respond | §9.1.2, C8, C10 |
| FR-15 | evidence-card collapsed ↔ Stock expanded 同一对象两态 | §9.1.3 |
| FR-16 | export：snapshot → Parquet/JSON 分片，不含任何 key | §5, C9 |
| FR-17 | steady-riser 核心筛法：W=10 天四指标（net5/net10/net20、up10、ddw10、ker10，全部图上可验证）→ gate=`up10≥0.6 AND net10>0`、按 net10 排序取 top-N（N=50）→ `rise_candidate` + `rise_streak_days` + `rise_net10_pct`（compute 层单一真源）；Risers（连续上涨）按 net10 排序 + 证据列卡（假阳预期之内，基本面/财务为下游 precision）；平滑度绝不做硬 gate（§10.8.3） | §10.8, §9.3 |

### 11.2 非功能需求

| ID | 需求 |
|---|---|
| NFR-1 | **默认静态分发**：M0–M1 无常驻 server / 托管 DB、client 不暴露 key；零后端非硬约束，视觉/功能需要可引入（§5.2） |
| NFR-2 | **数据一致性**：同一票在所有 surface 数字可互相追溯（C9） |
| NFR-3 | **认知带宽**：DECISION bounded、标签仅 pinned、autoplay 仅用户受控（C1/C2） |
| NFR-4 | **可复现**：纯 trailing、point-in-time、anti-lookahead；无 forward estimate（§10.5） |
| NFR-5 | **可审计**：核心筛法永不黑箱，证据可见——每个数字（净涨幅 / 上涨天数 / 窗口回撤 / 路径效率）都能在 K 线图上人工复核，永不给 buy/target（P4） |
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
              rise_net5, rise_net10, rise_net20,                      -- steady-riser：5/10/20 日净涨幅（§10.8；10 为主窗）
              rise_up10, rise_ddw10, rise_ker10,                      -- 上涨天数占比 · 窗口内最大回撤 · 路径效率（证据列，绝不硬 gate）
              rise_net10_pct, rise_candidate, rise_streak_days);      -- net10 横截面 pct（Ocean 纵轴）· 榜内 flag（单一真源）· 连续在榜天数
              -- brk_*（base→breakout）已随引擎退役删除（2026-07-02，§10.9）
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
| **M7 ✅→⟲✅→⟲** | **核心筛法 + 候选榜**：原 M7 交付 ignition（退役）；2026-06-16 改 base→breakout（`compute/breakout.py`，✅上线后于 **2026-07-02 退役**，§10.9）；**现定义 = steady-riser 筛法**（`compute/riser.py`，§10.8）→ export 候选 → **Risers（连续上涨）榜**（证据列卡）→ Stock 衔接基本面/财务（precision 下游）。 | compute, export, web | AC-M7 |
| **M8 ✅→⟲✅→⟲** | **Ocean = 连续上涨强度 × Valuation 二维相图**（§9.2）：海平面图骨架（60 日 daily、log P/S 横轴、payload v3 bulk+懒加载 detail、插值动画）历经 ign_pct（M8 原版）→ brk_strength_pct（2026-06-16）→ **`rise_net10_pct`（2026-07-02）**；candidate 读 `derived_daily.rise_candidate`（单一真源，不由 y 值推导）。`ocean-draw.ts` / `Ocean.tsx` 复用骨架仅替换纵轴语义。Rotation league 聚合改 # riser 候选。 | export, compute, web | AC-M8 |

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
- **AC-M7**：`derived_daily` 含 steady-riser 字段（`rise_net5` · `rise_net10` · `rise_net20` · `rise_up10` · `rise_ddw10` · `rise_ker10` · `rise_net10_pct` · `rise_candidate` · `rise_streak_days`）；Risers（连续上涨）按 gate（up10≥0.6 & net10>0）+ net10 排序取 top-N（N=50，假阳预期之内），非 breakout/composite/ignition 排序；evidence-card 露图上可验证证据列（净涨幅 5/10/20、上涨天数 x/10、窗口回撤、连续在榜天数）；riser 指标与估值共用同一份 per-stock 数据（C9）；候选 flag 由 compute 单一真源、export/前端不重算；候选榜非空且与 board 同源可追溯。（注：原 AC-M7 校验 base→breakout `brk_*`——已退役，§10.9。）
- **AC-M8**：Ocean = 连续上涨强度 × Valuation 二维相图 —— 默认显示 latest daily snapshot；纵轴 = `rise_net10_pct`（10 日净涨幅横截面百分位）；标记的候选股 == `derived_daily.rise_candidate`（与 Risers 榜同一 flag，C9，不由 y 值推导）；横轴 = 原始 P/S 的 log 轴（非 valuation percentile）；日期 slider 可手动切日；Play 自动播放且点在相邻真实 EOD 间**平滑插值**（不伪造交易日，tooltip 取真实快照）；**breakout / composite / ignition 不再出现在任何用户可见 UI**；`make ocean-c9`（rise_net10_pct/candidate/ps 同源）+ `make web-test` + `make web-build` 全过。（注：原 AC-M8 纵轴 = brk_strength_pct——已退役，§10.9。）
- **横切**：每个 M 通过 `make verify`（两个 gate GATE_PASS）+ acceptance comment（§19）。

---

## 15. 显式 OUT OF SCOPE（防 scope creep）

intraday / real-time；auth / 多用户 / 支付；**非美上市标的**；**中文 cross-language 判定（本期 descoped）**；backtesting 引擎（验证信号有效性是独立的事，别掺进监控管线）；Ocean **无控/常驻全量** autoplay 动画（M8 的用户受控 Play/Pause + 相邻真实快照插值不在此列）；**email digest（暂不做，2026-06）**。

---

## 16. 已定死（code 不要再翻案）

> **AMENDMENT 2026-07-02（二次换芯，用户拍板 + exp 10 实证）：** 核心由 base→breakout 改为 **steady-riser（连续上涨）**——算法必须**简单、不易出错、图上可验证（与直观相符）、不指向预测收益**（§10.8）；**base→breakout 退役**（复杂/图上不可验证/偏 ~7.5 月前的老突破，§10.9）；tab 改名 **Risers（连续上涨）**；Ocean 纵轴 = `rise_net10_pct`。**已拍板（2026-07-02）：ETF（如 SOXL 型杠杆 ETF）纳入 universe**，落地推后到换芯在现有个股数据上跑通之后（§17）。以下各条已就地修订。
> （历史：AMENDMENT 2026-06-16 曾将核心由 ignition 改为 base→breakout；该引擎已再次被取代。）

- spine：**steady-riser 核心筛法（2026-07-02 spine pivot §10.8）+ valuation + raw evidence → 5 surface → 2 scale → 默认静态分发**（零后端从硬约束放宽为默认 §5.2；web 栈 = React+Vite+TS）。**base→breakout / ignition / composite 全部退役**；唯一核心筛法 = steady-riser。
- 数据源：Stooq(EOD) + Nasdaq screener + EDGAR + yfinance(脆弱兜底)。**ETF 纳入 universe 已拍板（2026-07-02）、落地推后**（§17）。
- 5 surface 行为 + evidence-first（**永不给 buy/target**；露原始证据 + riser 指标 + valuation）。
- 数学：vol-normalized EWMAC、RS=双窗超额收益横截面百分位、trend=KER/OLS t 值；**核心筛法数学 = steady-riser（W=10 天净涨幅/上涨天数/窗口回撤/路径效率，全部图上可读，§10.8）**。**base→breakout、composite、ignition 均已退役，不再计算/导出/驱动任何 surface；早⟷reliable 旋钮早已取消。**
- **核心筛法 = steady-riser（§10.8，2026-07-02 定调）**：算法三条硬要求 = **简单、不易出错、方便验证（与直观相符）**，且**不指向预测收益**；语义 = 把「每天扫几千张 K 线找过去一两周持续走高、回撤少的票」数学化。数学 = `rise_net5/10/20`（净涨幅）、`rise_up10`（上涨天数占比）、`rise_ddw10`（窗口内最大回撤）、`rise_ker10`（路径效率）；**gate = `up10≥0.6 AND net10>0`、按 net10 排序取 top-N（N=50）**；`rise_candidate` 由 compute 单一真源。**平滑度绝不做硬 gate**（exp 10：严平滑 gate 把 SNDK 挡到 d66——真火箭初期不平滑；ker/ddw 只做证据列）。**recall-first：false positive 是预期的、后期下跌的入选也没关系**——fundamentals/financial 才是下游 **precision** 阶段。**无任何可调 alpha 参**（W=10、up≥6/10、N=50 是 UX 常数）。**两级漏斗 = steady-riser 筛选 → 基本面/财务终筛（precision）**。**tab 名「Risers（连续上涨）」**。**Ocean 纵轴 = `rise_net10_pct`**（连续上涨强度 × valuation 二维相图，§9.2）。
- **核心是 steady-riser**：不回测优化，买 robustness 不买 alpha；**不声称前向收益**（exp 10 实测 picks ≈ 池中位；价值 = 效率 + 召回，edge 归用户基本面判断）。**base→breakout / ignition / composite 均已退役**；早⟷reliable 旋钮早已取消。
- 估值：price ÷ trailing-4Q 日频、**formal-filing PIT**（分母只用正式 SEC filing、ASOF 键 = `effective_eod_date`、`valuation_basis='formal_filing_pit'`；§10.5）、`E≤0→n.m.` 退 P/S、无 forward、百分位用 **common-vintage**（当前 fresh-cohort v1）；**Ocean = rise_net10_pct（纵）× 原始 P/S log（横，非 percentile）二维相图**（§9.2，2026-07-02 spine pivot）。
- Rotation = **RS-Ratio 多线（非散点）**，league 聚合 **# riser candidates**（非 breakout/composite/ignition 口径）；**Ocean 轴固定 rise_net10_pct × P/S(log) 二维相图**（旧 breakout 海平面 / ignition 海平面 / RS×Val / RRG-axes 均已砍，`rsr`/`rsm` 删）。
- **不把 deep-drawdown / distance-from-high 编码成 Ocean 的看涨轴 / 光晕 / 海平面**（edge-research exp 9 `analysis/drawdown_decomposition.py`）。诚实理由：暴涨股的前期"深跌"是 **idiosyncratic-vol** 现象（与行业/idio-vol 不可分，已由 `colorBy=sector` 承载）+ **survivorship 上界** + **regime 接飞刀**——**不是** beta/随大盘（尾部 +300% beta 深跌 lift<1），也**不是**可交易方向 edge。`distance-from-high / 回撤` 仅可作 **Stock/tooltip 原始 evidence**（露处境），**绝不**编码为方向/买信号（P4 evidence-first，永不给 buy/target）。
- 全局 scope（all|sector|theme|pinned）单一真源、跨 tab 粘滞、可见可一键清，4 surface 全 respond。
- point-in-time membership 硬要求；theme 指数非市值加权。

---

## 17. 留给实现的决策（非翻案）与开放问题

- **已定（2026-07-02 二次换芯）：核心转 steady-riser，base→breakout 退役。** 用户拍板算法三条硬要求（简单/不易出错/图上可验证）+ 不指向预测收益；exp 10（`analysis/steady_riser.py`）实证 V3 形态七只样板票 d0–d10 检出。常数 W=10、up≥6/10、N=50 为 UX 常数、不回测优化（§10.8.5）。
- **已定（2026-07-02）：ETF 纳入 universe，落地推后。** SOXL 型杠杆 ETF 要能上榜需 universe 扩含 ETF；先在现有个股数据上跑通换芯，再落地 ETF ingest（需 ETF 清单源——Nasdaq screener 是股票口径；ETF 无 EDGAR 10-Q 基本面 → 估值面一律 `n.m.`/留空处理，riser 指标只用价格不受影响）。
- **已定（2026-06-14）：early⟷reliable 旋钮取消**；全局不再有可拨旋钮。
- **已定（2026-06-16，历史）：核心曾转 base→breakout，ignition 与 composite 双退役**——base→breakout 本身已于 2026-07-02 退役（§10.9）。
- theme membership 的营收阈值、LLM→human 审核流的具体形态（§8.3）。
- common-vintage 的 coverage 门槛具体 %（mock 用 ≤95 天近似，真实按「末季 ≥X% 已报」）（§10.5）。
- Ocean lasso 框选 set scope 的实现（mock 只做 respect/变淡）（§9.2）。
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
| **steady-riser（连续上涨）** | **核心筛法**（2026-07-02）：W=10 天净涨幅 / 上涨天数占比 / 窗口内最大回撤 / 路径效率，gate=`up10≥0.6 & net10>0`、net10 排序 top-N；全部图上可人工核对、不指向预测收益（§10.8） |
| **rise_up10** | 近 10 个交易日上涨天数占比（数绿蜡烛）；gate 的唯一形态条件——最宽容且直观的垃圾地板（§10.8） |
| **rise_ddw10** | 近 10 日窗口内相对窗口滚动峰值的最大回撤（≤0）；「回撤少」的直读量，证据列、不做硬 gate（§10.8.3） |
| **base→breakout** | 已退役的前核心引擎（2026-06-16 → 2026-07-02 退役）：LOG 价单变点 τ 拟合（§10.9，历史锚点） |
| **fit_gain** | `1−SSE2/SSE1`，2 段相对 1 段 OLS 的 SSE 缩减 = 拐点显著度（kink salience，≳0.7；§10.8） |
| **漏斗（recall→precision）** | steady-riser recall-first 筛选（gate + net10 排序取 top-N，假阳预期之内、后期下跌的入选也没关系）→ 基本面 / 财务作 precision 终筛（§10.8.4） |
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

**steady-riser 字段（§10.8，核心筛法）**：`rise_net5` / `rise_net10` / `rise_net20`(5/10/20 日净涨幅；10 为主窗) · `rise_up10`(上涨天数占比，gate 条件) · `rise_ddw10`(窗口内最大回撤，证据列) · `rise_ker10`(路径效率 |Σδ|/Σ|δ|，证据列) · `rise_net10_pct`(net10 横截面 pct，Ocean 纵轴) · `rise_candidate`(gate ∧ net10 top-N，compute 单一真源) · `rise_streak_days`(连续在榜天数，描述非过滤)。（`brk_*` 字段已随 base→breakout 退役删除，§10.9。）

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
**连续上涨强度（rise_net10_pct）**：≥90（海平面上）绿 · ≥80 琥珀 · <80 暗灰；candidate（榜内）高亮环。（breakout / composite 分色已随各自引擎退役作废。）

---

*本 PRD 是活文档。任何需求/边界变化先回写本文件，再继续实现（见 §19 工作流）。*
