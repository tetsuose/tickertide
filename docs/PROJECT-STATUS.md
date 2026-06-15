# TickerTide — 项目现状 & 算法 Handoff

> **写于 2026-06-14,M8 更新 2026-06-15,给新 session 接手用。** 这是现状快照 + 算法精要 + 文件/工作流导航。
> **算法权威规格(SoT)仍是 `docs/PRD.md` §10.8**;本文自包含到「读完能继续开发」,细节冲突以 PRD §16「已定死」为准。
> 上手顺序:本文 → `CLAUDE.md`(入口约束)→ PRD §10.8(算法)→ ROADMAP「M7」(里程碑)。

---

## 0. 一句话

盘后(EOD)、美股专属的 momentum 监控工具。**脊柱 = `ignition`(核心发现)+ valuation + raw evidence;`composite` 自 M8 起退为计算层暂存、不再用户可见。Ocean 已重构为 Ignition × Valuation 海平面图(y=ign_pct、海平面 90、x=log P/S + 日期滑杆动画)。5 个 surface → 生产上线 `tickertide.pages.dev`(Cloudflare Pages,nightly 自动部署)。**

---

## 1. 怎么走到今天(脉络)

- **初衷**:从几千只美股里**早期(起涨 1–2 周)**发现快涨股(SNDK / ARM / MRVL / AAOI 型数倍股),再翻财报做基本面。痛点:这些票早期没注意到,等上榜已涨完大半。
- **诊断**:原来的 `composite` 是趋势**确认**引擎——5 个分量全是长窗口 / 测「水平多高」(rs 63/126、high 252、trend 63、vol 50/200),**数学上系统性滞后**。`early⟷reliable` 旋钮只在这些都滞后的分量间重配权,k=1「early」也是**假 early**。
- **转向(2026-06-13)**:**双引擎**。新增 `ignition`(短窗口 / 拐点 / 突破)为**核心发现引擎**,`composite` 退为**辅助确认**。早晚不是一个旋钮的两端,是两台不同物理量的引擎。
- **路径**:诊断 → 双重实证(timing + precision)→ 规格立法(PRD §10.8)→ M7 实现 → 真实数据验证 → 取消旋钮 → **生产部署上线**。

---

## 2. 算法详解(核心 — 新 session 重点读这节)

### 2.1 为什么是两台引擎,不是一个旋钮

早期发现测的是**加速度 / 拐点**(短窗口),趋势确认测的是**水平**(长窗口)——不同物理量。把「早 vs 稳」做成一个标量旋钮(旧 `composite` 的 k)在数学上做不出真早期。所以并列两台引擎,「要早看 ignition,要确认看 composite」由**引擎切换**承担,旋钮已取消(见 §3)。

### 2.2 ignition 引擎(项目核心,PRD §10.8;实现在 `compute/ignition.py` + `compute/run.py`)

**5 个短窗口分量**(per-stock 计算,源码 `compute/ignition.py`):

| 分量 | 公式 | 抓什么 |
|---|---|---|
| `ig_accel` | `ret_10/10 − ret_50/50` | 动量加速:短窗步速超过中窗(斜率变陡,不是已经高) |
| `ig_expand` | `mean(\|Δp\|,10) / mean(\|Δp\|,60)` | 波动收缩→扩张:低波动 base 后区间放大 |
| `ig_vsurge` | `mean(vol,5) / mean(vol,60)` | 放量:短窗对自身近月基线(非 50/200 慢量比) |
| `ig_breakout` | `clamp(close/max(close,60),0,1)·1[close>MA50]` | 突破 / 收复:逼近 60 日高 + 站上 MA50(从底部抬升) |
| `ig_rsturn` | `slope₁₀(P/P_spx) − slope₃₀(P/P_spx)/3` | RS 拐点:相对强度线短期斜率由负转正 / 加速 |

**合成与点亮**(`compute/run.py` 做横截面):
- 每个分量每日做**横截面 percentile-rank** → **等权平均** = `ignition`(0–100)。
- `ignition` 再每日横截面 percentile = `ign_pct`(0–100)。
- **点亮** = `ign_pct ≥ 90`(top decile)。
- **persistence** = 连续位于 top decile 的天数 `ign_persist_days`(islands 技法,非 lit 行=0)。
- **持续点火 candidate** = `ign_pct ≥ 90 AND ign_persist_days ≥ 5`。 ← Discovery 排序 key。

**关键:ignition 无任何可调参**(5 分量等权、阈值 90 / persist 5 固定)。这是刻意的——「买 robustness 不买 alpha」,不给实时调参旋钮(诱导 overfitting);persist 天数等离线用 `analysis/` 定 final。

### 2.3 persistence 是精度的关键(实证支撑,别去掉)

`analysis/precision_ignition.py`(中性 800 只 Nasdaq habitat 池)实测:
- **瞬时点火**(刚跨入 top decile)的 forward LIFT ≈ 0 —— **不胜过随机入场**。
- 提高强度阈值(top 1%)无效甚至更差。
- **唯 persistence(连续 ~5 日仍在 top decile)** 把 60–120 日中位 LIFT 转正 **+2.5~3.1pp**。
- 机理:真突破赖在强势区、假突破速熄。persistence 仅延迟 ~5 天,仍远早于 composite 的 14–45 周。

### 2.4 三级漏斗(ignition 的产品形态)

`ignition 触发`(recall,早)→ `persistence 确认`(precision,去假突破)→ `翻财报终筛`(human)。**Discovery = 持续点火榜**。

### 2.5 composite(辅助确认,固定权重)

`score = 100·Σ wᵢ·componentᵢ`,5 分量 ∈[0,1]:`rs_pct`、`high_proximity`、`trend_quality`、`volume`、`rs_accel`(长窗口,源码 `compute/signals.py`)。**固定 k=0.5**(权重 `rs=.215, high=.22, trend=.17, vol=.12, accel=.275`)。**自 M8 起 composite 退出全部用户可见层(Discovery / Stock / Rotation / 顶栏都不再显示),仅作计算层暂存**(`compute/run.py` 的 composite 列、`derived_daily.composite`、`board.json` 字段、`web/src/lib/composite.ts` 保留但 UI/文案不暴露)。`early⟷reliable` 旋钮已取消。

### 2.6 实证数字(都在 `analysis/`)

- **timing**(`analysis/verify_ignition.py`):ignition 比 composite **早 14–45 周**点亮 ARM/MRVL/AAOI/SNDK(composite 点亮时票已涨 +84%~+732%)。
- **precision**(`analysis/precision_ignition.py`):见 §2.3。
- **真实生产**(nightly,506 票):10 个 candidate,榜首 MRVL(persist 9)/ AMAT(persist 8)/ FITB / ODFL / ARGX / KLAC —— 跨半导体 / 金融 / 医药 / 工业,candidate composite 仅 ~52–74(未达确认区)→ ignition 确实早于 composite。
- **诚实边界**:实证有幸存者偏差(yfinance 仅现存票)+ 2023–26 牛市底噪;LIFT(event−base)对两者相对稳健;lift 量级温和,真 alpha 在用户的基本面环节。

### 2.7 数据流(C9 单一真源)

```
compute/ignition.py (5 分量 per-stock)
  → compute/run.py (横截面 percentile + ignition + ign_pct + persistence islands)
  → derived_daily 扩列: ig_accel,ig_expand,ig_vsurge,ig_breakout,ig_rsturn, ignition, ign_pct, ign_persist_days
  → export/board.py (ignition 块 + candidate + 点火证据) → board.json
  → export/ocean.py (ign_pct × raw P/S 日频快照, schema v2) → ocean.json   ← M8
  → web Discovery (持续点火排序) / Stock (点火诊断小节) / Ocean (海平面图 + Play 动画)
```
**C9 同源守卫**:`export/check_ignition.py`(`make ignition-c9`)+ `compute/check_ac_m7.py`(`make ac-m7`,AC-M7 五条门禁)。ignition 永不在 export / 前端重算,一律读 `derived_daily` 导出值。

---

## 3. 当前状态(2026-06-14,main = `963045c`)

| 阶段 | 状态 | PR |
|---|---|---|
| M0–M6(数据+引擎+5 surface+部署+主题) | ✅ DONE | #1–#62 |
| **M7 ignition 双引擎** | ✅ DONE | #64–#68 |
| 取消 early⟷reliable 旋钮(ignition 核心、composite 固定 k=0.5) | ✅ | #69 |
| cleanup(nightly 加 ignition-c9 + board.py 去 knob 残留) | ✅ | #70 |
| **M8 Ocean 重构(Ignition 海平面图 + 动画;composite 退出 UI)** | ✅ DONE | `feat/m8-ocean-ignition-sea-level` |
| **生产上线** | ✅ `tickertide.pages.dev`(Access 锁 sejonep)|nightly 自动部署 |

线上现状:Discovery 是真正的 ignition 持续点火榜(506 票 / 10 candidate),前端无旋钮(IGNITION 引擎说明替代)。**M8 起 composite 退出全部用户可见层(仅计算层暂存 k=0.5);Ocean 重构为 Ignition × Valuation 海平面图 + 日期滑杆/Play 插值动画(注:M8 在 `feat/m8-ocean-ignition-sea-level` 分支,上表 main SHA 为 M8 前)。**

---

## 4. 文件地图(改算法看这些)

- **compute**:`ignition.py`(5 分量)·`run.py`(横截面+persist 接线)·`signals.py`(composite 数学)·`check.py`(AC 抽查)·`check_ac_m7.py`(AC-M7 门禁)
- **export**:`board.py`(Discovery 数据+ignition 块)·`stock_bundle.py`(Stock per-name+ignition)·`ocean.py`(M8 Ocean 海平面图 schema v2,ign_pct × log P/S 日频)·`check_ignition.py`(C9)·`check_ocean.py`(M8 Ocean↔board C9)
- **web**:`src/views/Discovery.tsx`(持续点火排序)·`src/views/Stock.tsx`(点火诊断)·`src/views/Ocean.tsx`(M8 海平面图 + 日期滑杆/Play 动画)·`src/lib/ocean-draw.ts`(M8 Ocean 纯绘制+插值)·`src/components/EvidenceCard.tsx`(点火证据卡)·`src/lib/composite.ts`(固定权重,**M8 起仅计算层保留、UI 不暴露**)·`src/App.tsx`(顶栏,已无旋钮、已无 composite 说明)
- **analysis**(实证,非管线):`verify_ignition.py`(timing)·`precision_ignition.py`(precision)
- **schema**:`ingest/schema.sql`(derived_daily 扩列)

---

## 5. 工作流 & 验证(硬约束,CLAUDE.md §3)

- **新任务**:`make task-open QUERY="..."`(worktree)或主仓库分支;**一个分支一个 merge intent**。
- **改/增文件**:更新 `docs/runtime/File-Contracts.json` 合同(禁占位);新增文件先 `make writeback-apply WRITE=1`。
- **提交前**:`make verify` 两 gate 必 `GATE_PASS`(`structure_contract_coverage` + `changed_file_contract_semantics`)。
- **行为验证 VERIFY**(行为正确性,非合同 gate):
  ```
  source .venv/bin/activate && make fixture-pipeline && make check && make web-test && make web-build
  ```
  另:`make ac-m7`(AC-M7 五条门禁)、`make ignition-c9`(ignition 同源)。**无 pytest**,compute 行为靠 `make check`;web 靠 vitest(`make web-test`)+ tsc(`make web-build`)。
- **环境**:系统 python3 无 duckdb → make 命令**必须 `source .venv/bin/activate`**;web 需 `make web-install`(含 `@duckdb/duckdb-wasm`)。

---

## 6. 部署机制(关键,别再踩坑)

- **`deploy-web.yml`**:push `main` 且改了 `web/**` 触发。「快前端 lane」——**不重算数据,复用最近一次成功 nightly 的数据 artifact** + 重 build 前端 + 部署 Pages。
- **`nightly.yml`**:cron(周二–六 07:00 UTC)+ workflow_dispatch。跑**真实 pipeline**(ingest top-500 → compute 含 ignition → export → build → 部署)。
- **⚠️ 教训**:**数据层改动(`export/`、`compute/`)不触发 deploy-web,必须靠一次 nightly 才上线**。否则会出现「新前端 + 旧数据」错配(M7 上线时踩过:前端有 ignition UI 但 board.json 无 ignition 块,跑一次 nightly 才修)。手动触发:`gh workflow run nightly.yml`(~25–30 min)。
- R2 只托管 Valuation 的 duckdb-wasm(超 Pages 25MiB),与 ignition 无关(ignition 数据在 Pages 的 board.json)。

---

## 7. 未决 / 下一步候选(PRD §17)

- **M8 Ocean 接手说明**:新 Ocean = **Ignition × Valuation 海平面图**——y=`ign_pct`、固定海平面线 `ign_pct=90`(=Discovery 点亮阈值)、x=**原始 trailing P/S TTM 的 log 刻度**(非百分位、无隐含阈值参数);海平面之上的点 = 持续点火 candidate(`ign_pct≥90 AND ign_persist_days≥5`,与 Discovery 同一道 gate,C9)。日期滑杆 scrub EOD 快照(默认开最新),Play 用 rAF 在相邻**真实** EOD 快照间 tween(900–1200ms/段);**插值仅视觉,tooltip/状态永读真实快照、绝不读伪造中间值**。砍掉旧象限色/(50,50) 十字线/周 scrubber/pin 多周尾迹。数据契约见 `export/ocean.py`(`ocean.json` schema v2)+ ROADMAP「M8」段。
- **M8 payload 后续(未做)**:生产 `ocean.json` 较大(60 天 × ~500–6766 票 × 12 字段 pt;top-500 约 ~6MB,gzip ~1.5MB)→ 分片 / 裁剪是后续优化。
- **persist 天数**:默认 5,用 `analysis/precision_ignition.py` 复核 5/7/10 定 final。
- **全 universe**:nightly 默认 top-500 by mktcap(偏大中盘);ignition habitat 在中小盘,扩到全 ~6766 只 candidate 会更多(M6 扩量)。
- **是否叠加估值过滤**(ignition ∩ 不贵):PRD §17 未决。
- **Valuation R2**:duckdb-wasm 走 R2(operator 待配,现 fallback jsDelivr)。
- **AI「why moving」**:Discovery 卡 + Stock 的 filing 摘要占位待接(复用 M4.5 的 claude CLI plan 额度范式)。

---

## 8. 权威文档导航

| 文档 | 作用 |
|---|---|
| `docs/PRD.md` | 产品规格 SoT;**§10.8 = ignition 算法权威**;§16 已定死 |
| `docs/BUILD-PLAN.md` | 数学规格出处;§4.8 ignition |
| `docs/ROADMAP.md` | 里程碑;「M7」段 = ignition 落地方案、「M8」段 = Ocean 重构(海平面图 + composite 退出 UI)+ 进度 |
| `CLAUDE.md` | 项目薄入口(约束 + 导航) |
| `docs/progress/M7-ignition.md` | M7 执行细节 / subagent 交接(**gitignore,仅本地**) |
| `docs/runtime/File-Contracts.json` | 文件合同账本(gate 用) |
| `analysis/*.py` | ignition 实证脚本(timing + precision),可复跑 |
