# US Equity Momentum Monitor — BUILD PLAN

> 这份文件既是 **code mode 的开工 prompt**,也可作为 `CLAUDE.md` 的种子。
> 配套 UX 参照:`equity-monitor-v2.jsx`(mock,定义五个 surface 的布局与交互;**不是要跑的代码,是视觉契约**)。

---

## 0. 一句话定义 / Scope

一个 **盘后(EOD)、美股专属** 的 momentum + valuation 监控工具。
**Spine:** 一个 stock-level composite 引擎 → 五个 lens,两个尺度(wide explore / bounded decide),零常驻 backend。

**SCOPE — 不可越界:**
- **仅限美股(US-listed:NYSE / Nasdaq / NYSE American)。** ADR 因在美上市可纳入;非美上市标的一律 out。
- 中文/cross-language 标的判定本期 **不做**(已显式 descoped);主题语义判定只读 **英文 EDGAR filings**。

---

## 1. 脊柱原则(贯穿所有 surface)

**两台互补引擎(composite 确认 + ignition 发现),五个 lens,两个尺度。** 不要写五条独立管线。

- **composite** = stock-level 确认引擎(§4.6);**ignition** = 早期发现引擎(§4.8,2026-06-13 立项,实证 `analysis/`)。两台共用同一份 per-stock 数据。
- **Discovery** = ignition「持续点火」排序;**Rotation** = composite 按 bucket group-by;**Ocean** = composite 的二维相图;**Valuation** = 估值的 cross-section;**Stock** = 单票展开。
- **两个尺度**(产品成立的前提):
  - **wide / explore**:Ocean、Valuation screener —— 数千只,用来逛。
  - **bounded / decide**:Leaders(固定 top-N)、Rotation(~10–12 桶)—— 用来动手。
- composite = 辅助确认引擎,用 **固定权重**(`k=0.5`,§4.6),不删任何 component、5 分量原始值可展开看。曾经的 `early ⟷ reliable` 旋钮 **已取消**(诊断为假 early——只在 composite 那些都滞后的分量间重配权;核心是 ignition、ignition 无可调参,PRD §16/§17)。

---

## 2. 架构(fomo5000 范式:离线预计算 + 静态分发)

```
GitHub Actions (nightly cron, post-US-close)
  └─ Python ingest:  Stooq (bulk EOD bars) + Nasdaq screener (universe/cap/sector/PE) + SEC EDGAR (fundamentals/segment)
  └─ DuckDB compute: derived_daily + composite + RS-Ratio 序列 + theme membership + percentiles(common-vintage)+ ASOF valuation
  └─ export:         snapshot → Parquet/JSON shards
  └─ deploy:         Cloudflare Pages (static)
Client (canvas + duckdb-wasm):  renders Ocean (thousands of points) + boards; screener filters query Parquet shards in-browser
(optional) private Streamlit cockpit for server-side interactive work
```

- **无常驻 server、无托管 DB、不向 client 暴露任何 key。** GitHub Actions = cron。这与 SCOPE 的零后端 spine 一致,也复用既有 Cloudflare/Actions 经验。
- DuckDB 选型理由:列存 OLAP(rolling window / 聚合 / 横截面 percentile 是全列扫描型 workload)+ 嵌入式(single-writer、offline batch,不需要 Postgres 的 client-server/MVCC/并发写)+ 原生 `ASOF JOIN`/`QUALIFY`/`PIVOT` + 整库单文件可移植 + duckdb-wasm 可在浏览器查 Parquet。**(若以后变多用户事务型 app 才考虑 Postgres——那是另一个 ontology。)**

---

## 3. 数据源(免费,支持每日更新,US-only filter)

| source | 用途 | 备注 |
|---|---|---|
| **Stooq** | bulk EOD OHLCV(价格主干) | CSV 批量,**无 per-symbol 限速** → 数千只的最佳免费源;校验覆盖,补缺口 |
| **Nasdaq screener** (`api.nasdaq.com/api/screener/stocks`) | universe + market cap + GICS-ish sector/industry + trailing P/E + last sale | 一次拿全美股清单;半官方 |
| **SEC EDGAR** (`data.sec.gov` companyfacts / submissions) | revenue / shares / debt / cash / **segment** → P/S, EV/S, Rule-of-40,**以及主题营收锚定** | 官方权威;需 descriptive `User-Agent` header,~10 req/s |
| **(opt) Tiingo** | 干净补缺 | 便宜付费;yfinance 仅作 fallback(非官方、ToS 灰、会断) |

- **US-only 过滤**:Nasdaq screener 限 NYSE/Nasdaq/AMEX 上市;EDGAR 天然是 US filers。
- **Licensing:** 公开展示 / 再分发 / 商业化前必须复核数据源条款：Stooq/EDGAR 条款最友好;其余多数禁止 redistribute,需 display license。
- **IEX Cloud 已退役(2024-08),勿用。** 别信仍在列它的旧对比文。

---

## 4. 数学规格(优雅化,逐项替掉粗糙件)

> 诚实定调:以下大多 **买 robustness/stability,不买 alpha**。EWMAC 是 80/20;KER/t-stat 值得加;Kalman 锦上添花,别当成提升收益的关键路径。

**4.1 趋势 / return —— vol-normalized EWMAC(替 boxcar 窗口)**
- `forecast = (EMA_fast − EMA_slow) / σ`,σ = price-change 的 EWMA 标准差。无窗口跌落跳变、频域干净一阶低通、自比例。
- 多 horizon:混几对 fast/slow(对应原 63/126;**不跳近期**,因为目标是 emerging leader 要早)。
- Minervini Trend Template 处 **保留 SMA**(`close>MA50>MA150>MA200`、`MA200` slope≥1mo via `MA200[t]>MA200[t−21]`、距 `low_252d`≥+30%),与 EWMAC 并算两套。

**4.2 RS percentile**
- `rs_raw = (ret_63 − SPX_63) + (ret_126 − SPX_126)`(相对 SPY/`^GSPC`)。
- **每个交易日做 cross-sectional percentile**(池内横截面,非跨时间)。这是 IBD RS Rating 思路。

**4.3 趋势质量(给方向 + 干不干净)**
- KER:`ER = |P_t − P_{t−n}| / Σ|P_i − P_{i−1}|` ∈[0,1];或 log-price OLS 的 **slope t-stat**(`slope/resid_σ`)。

**4.4 RRG / Rotation 算法(RS-Ratio = x 轴, RS-Momentum = y 轴)**
对 security S(sector ETF 或 theme index)与 benchmark B(SPY),weekly 为主:
- **RS line(price relative,≠ RSI ≠ IBD RS Rating):** `RS = 100 × P_S / P_B`,上升=跑赢基准。
- **RS-Ratio(JdK RS-Ratio = 相对强度的 level):** `M = EMA(RS, n1)`(n1 短);`RS-Ratio = 100 + k·(M − SMA(M, n2))/σ(M, n2)`(n2 长,z-score recenter 到 100)。>100 = 跑赢自身近期趋势。
- **RS-Momentum(= RS-Ratio 的一阶导):** `R = RS-Ratio − RS-Ratio[t−m]`(ROC);`RS-Momentum = 100 + k·(R − SMA(R, n3))/σ(R, n3)`。>100 = 在加速;**领先 RS-Ratio**。
- **plot:** 点=(RS-Ratio, RS-Momentum),tail=最近 N 期(weekly,N~6–12)。象限(原点 100/100):**Leading**(右上,两者>100)/ **Weakening**(右下,Ratio>100,Mom<100)/ **Lagging**(左下,两者<100)/ **Improving**(左上,Ratio<100,Mom>100);健康轮动=**顺时针** Improving→Leading→Weakening→Lagging。
- **专有警告:** de Kempenaer 确切常数未公开 → 上式是**透明 reconstruction**,定性一致、可审计,**别声称复刻 StockCharts 数值**。
- **z-score 基准:** 固定 11 GICS sector 用 temporal(对自身历史);theme 成分会变 → **point-in-time** 否则尾迹虚构。基准换 equal-weight/全球则图变。
- **= level+slope:** RS-Ratio≈相对强度 level、RS-Momentum≈其 slope,与 §4.7 Kalman level+slope 同源,只是画成 2D 相图。
- **N=1 drill-down = RS-Ratio 时间序列线(已定):** 单只 bucket 直接画 RS-Ratio 折线 —— 高度=level、斜率=momentum、**走平=中性**(比 RRG 归一 y 的"100≠走平"更直读),全历史可见。**RS-Momentum 归一量整个砍掉**——momentum 就是 RS-Ratio 的斜率(N=1 单线可按短窗平滑斜率着色:升=转强、降=转弱)。
- **总览也用折线、不用散点(已定):** 所有 sector/theme 的 RS-Ratio 叠**一张大图**(height=level、slope=momentum、线交叉=leadership 换手),与 N=1 同一种视觉语言。**砍掉 RRG 散点**——它唯一强项是同屏比 N 个的斜率,用 ① 各线自身可见的斜率 + ② **league 表按 level 排序的 Δ(=斜率)列** 补回(state 由 level+slope 推回 Leading/Weakening/Improving/Lagging 四态)。**总览的线 color = bucket 身份,故不能再按斜率着色**(斜率着色只用于 N=1 单线)。多线拥挤 → hover 高亮一条、其余变淡;右缘按末值排序贴标签防重叠。
- **只讲相对(§7):** 熊市可 Leading 却绝对跌 → 配 composite/regime 读。standard sector 用 **11 SPDR Select Sector ETF**(XLK/XLF/XLE/XLV/XLY/XLP/XLI/XLB/XLU/XLRE/XLC)对 SPY = 零分类;theme 用合成 index(equal/capped、point-in-time)。league 表 = composite group-by(成员中位数 + breadth)。

**4.5 估值对齐 —— ASOF JOIN(解决 "P/S 非日频")**
- 季度营收(TTM)用 `ASOF JOIN` 对齐日线 → 日频 P/S(阶变只在营收更新时)。
- `EV = mktcap + total_debt − cash`;EV/S, EV/EBITDA 同理。
- P/S 看 **level + expansion(相对起点/行业中位)+ percentile**,别只看 level。
- **估值倍数统一规则(已定):** 所有倍数 = **price(或 mktcap/EV)÷ 过往 4 个季度的对应财务指标**,逐日计算(分母按季 ASOF 阶进、分子日频),季度边界取值即得季度序列(日频含季度)。**不纠结 TTM/动态/forward 命名** —— 方法就是「价 ÷ trailing-4Q」,不引入任何 analyst estimate(forward 不做:付费、provider-divergent、不可复现、乐观偏差)。统一套用 P/E(净利)、P/S(营收)、EV/EBITDA(EBITDA)等。取数默认 **diluted GAAP 归母**,**point-in-time**(用 as-of-date 实报、不用 restated,防 lookahead);`E≤0 → n.m.`,回退 P/S/EV/S。**纯后看的代价**:高增长/刚转盈的票 P/E 会显得很贵或 n.m. —— 设计如此,用并列 growth 对冲,不靠 forward 修。横截面约束 = **方法一致**(全票同算法);跨行业比较优先 **EV/EBIT**(P/E 受杠杆扭曲)。

- **as-of 同步(数据完整性,已定):** 横截面每个倍数用该票**最新可得** trailing-4Q(永不取未来季 = anti-lookahead),但各票窗口截止日不同(财年末 + 报告时滞:10-Q 40/45 天、10-K 60/75/90 天,加 off-calendar 财年)→ **必须暴露 as-of 日并分档上色**:已报当期 fresh / 落后一季 stale·待报 / n.m.。新鲜度按「最新季末距今天数」定义(非财季标签;>~95 天 = 落后一季 = flag)。陈旧分母**可选不进** percentile(污染横截面)。普遍时滞(人人都旧 40–90 天)只用全局脚注、不逐行上色。

- **横截面 percentile = common-vintage(已定,处理季度交界):** percentile 是相对统计,只有同 vintage 才有效。**绝对 multiple** 用最新可得(fresh,显示+标记);**percentile/排名**用「该 peer 集 ≥X%(如 50%)已报出的最近季末」为共同基准,覆盖率没过线则基准停在上一季 → **孤单先发报者不移动基准**(其新季 on-deck 等同行跟上,期间它的 percentile 按对齐的上一季算或显示 pending)。绝不拿先发者的新季数去排别人的旧季数(增长的先发者会被算得 spuriously cheap,纯属数据更新非重定价;误差集中在先发那几行=用户最爱盯的行)。

**4.6 composite**
- `score = 100 · Σ w_i · component_i`,components ∈[0,1]:`rs_pct`、`high_proximity=close/rolling_max(close,252)`、`trend_quality`、`volume`(`SMA(vol,50)/SMA(vol,200)` 抬升 **AND** up-vol>down-vol;另加快脉冲 `today_vol>1.5×SMA(vol,50)`)、`rs_accel`(`rs_pct[t]−rs_pct[t−21]`)。
- **固定权重(无旋钮)**:权重曲线 `w_high,w_trend` 随 k↓、`w_accel,w_rs` 随 k↑(Σ=1 全 k),但 `early⟷reliable` 旋钮 **已取消**,k **固定 0.5**(compute/run.py 默认 `--k 0.5`)→ `rs=.215,high=.22,trend=.17,vol=.12,accel=.275`。前端读引擎导出的 composite、不重算(C9);这条固定曲线只用来在角标里显每分量权重 %。

**4.7 (optional) Kalman level+slope**:要日间稳定/无丑跳变时再上;`rs≈level`,`rs_accel≈slope` 变化,`slope/√var` 做 z-score。

**4.8 ignition 引擎(早期发现,第二台引擎;2026-06-13 立项,权威规格见 PRD §10.8)**
- **动机**:composite(§4.6)是趋势确认,长窗口(rs 63/126、high 252、trend 63、vol 50/200)系统性滞后;曾经的 `early⟷reliable` 旋钮只在滞后分量间重配权,k=1「early」仍滞后(=诊断出的假 early)。早期发现 = 不同物理量(加速/拐点 vs 水平)→ 第二台并列引擎。**定调(2026-06-14)**:ignition 升为项目核心(无可调参)、composite 退辅助确认(固定 k=0.5),假 early 旋钮取消。
- **5 短窗口分量**(per-stock → 每日横截面 percentile → 等权):加速 `ret10/10−ret50/50`、波动收缩→扩张 `mean(|Δp|,10)/mean(|Δp|,60)`、放量 `vol5/vol60`、突破收复 `clamp(close/max(close,60))·1[close>MA50]`、RS 拐点 `slope10−slope30/3`(of `P/P_spx`)。
- **persistence = 精度关键**:点火 = `ign_pct` 跨入 top decile;**瞬时点火无 lift(≈随机入场),唯连续 ~5 日仍在 top decile 把 60–120d 中位 LIFT 转正 +2.5~3.1pp**(实证 `analysis/precision_ignition.py`,中性 800 只 Nasdaq habitat 池)。机理:真突破赖在强势区、假突破速熄。
- **三级漏斗**:ignition 触发(recall,早)→ persistence 确认(precision,去假突破)→ 翻财报终筛(human)。**Discovery = 「持续点火」榜(非 composite 排序)。**
- **诚实**:lift 温和、买 robustness 不买 alpha;persistence 是结构性去噪非调参买 alpha;caveat 幸存者偏差 + 牛市底噪(LIFT=event−base 抗偏差)。timing 实证 `analysis/verify_ignition.py`(ignition 早 14–45 周)。

---

## 5. 分类:标准底 + 营收锚定的语义主题

**Ontology:** 一只票没有内在板块,桶是提问 lens 的函数 → 数据模型 **ticker↔(sector,theme) many-to-many + 连续 exposure 权重 + point-in-time**。

**5.1 标准底(GICS-ish):** 直接用 Nasdaq screener 的 sector/industry。标准板块轮动用 **11 SPDR sector ETF 对 SPY** 的 RS-Ratio(相对强度)→ 零分类管线。

**5.2 概念主题(人工提需求,多对多,绝不强加 MECE):**
本期清单:**AI、智能机器人、太空算力、光模块**,加 半导体 / 核能 / 网安 / 云。NVDA 同时进 AI 和 Semis 是 feature 不是 bug。

**5.3 新概念成员判定 = 语义 + 营收锚定(核心方法):**
1. LLM 读 **EDGAR 10-K/10-Q 的 business + segment** 段(英文)。
2. 抽取该主题的 **营收暴露** → `membership.exposure = revenue_share`(连续,不是二元)。把 fuzzy 主题钉在近似可证伪的数字上。
3. **human-in-loop 审批**;LLM 当 **candidate generator + revenue extractor**,**不当权威 classifier**。
4. **point-in-time**:`t` 时刻的 membership 只反映 as-of `t` 已披露的信息。

---

## 6. 五个 Surface(对照 `equity-monitor-v2.jsx`)

1. **Ocean**(canvas,wide):数千只;**轴固定 x=RS pct,y=Valuation pct(底=便宜)**,color=sector/theme,size=mktcap;**时间 scrubber(周度快照,无 autoplay)**;**点击 pin → 画箭头 trail**(仅 pinned,不全量)。"右移 + 留在低估区(绿象限)" = cheap & strengthening = 要找的 emerging leader。(**RRG-axes 模式已砍**:per-stock RRG 散点冗余、1800 点是噪音云,且 Rotation 已改折线;momentum 维度在 composite / Rotation / Stock 已有。`rsr`/`rsm` 一并删。)
2. **Discovery**(原 "Emerging Leaders"):**evidence-first 证据卡流**(非分数榜),**按 ignition「持续点火」排序**(§4.8:跨入横截面 top decile 且持续 ~5 日;**非 composite 排序**)。候选池 = 三级漏斗前两级(ignition 触发 → persistence 确认)+ AI 兜底筛;bound = 持续点火名单,非硬 top-20。每卡 = **Stock 的 collapsed 态**,头部露点火证据(突破/放量/步速/MA50 收复)+ composite 角标作「是否已确认」副读(固定权重,无旋钮);候选池阈值离线定死(ignition 无可调参);d/d 仍标。
3. **Rotation**(narrow):**所有 sector/theme 的 RS-Ratio 多线图(非散点)** + **enriched league 表**(rank、RS-Ratio level、**Δ(=斜率/momentum)**、**breadth %>MA50 / %>MA200**、#at-52w-high、member composite 中位数、agg EV/S、多 horizon relative return,按 level 排序);**GICS↔Theme 切换**。**点表行/线 → set scope + 钻进该 bucket**(N=1 RS-Ratio 单线放大 + 成员 evidence-cards,见 §6.1)。
4. **Valuation**(screener,wide):cross-sectional 表 P/E·P/S·EV/S·EV/EBITDA·PEG·Rule-of-40·growth·margin + **sector/theme 内 percentile**;可排序筛选(duckdb-wasm 在浏览器查 Parquet)。
5. **Stock**(narrow,= evidence-card 的 expanded 态):**核心 = 时间轴对齐的 price↔fundamentals stack** —— 日线 K 线 + MA50/150/200 + 成交量 / **季度营收 bars** / **P/S over time**,各格共用同一 x 轴对齐(季度网格线贯穿),直接可视化 P/S expansion(价↑营收平 = 变贵无基本面)vs 赚到这波(价↑营收↑)。下接估值快照(P/S·EV/S·EV/EBITDA·P/E·growth·Rule40)+ composite component 序列 + theme memberships+exposure + 最新 filing AI 摘要。**保留为独立 tab**:既是 card 点开的落地详情,也支持按 ticker 直接查。

### 6.1 导航与 scope(top-down 核对,2026-06)

**核心 IA 原则:bucket→members 是 scope 收窄,不是新 surface。** 五个 tab 确认保留;**不建第 6 个 sector-detail surface**(会重复 Valuation/Ocean/Discovery 已有的列表与指标 = DRY/Occam 违例)。

- **新增 cross-cutting 原语:global scope filter** ∈ `{ all | sector:X | theme:Y | pinned }`。所有 wide / stock-level surface(Ocean、Valuation、Discovery board)respect 它;Stock 是 per-name,不受 scope 影响。Valuation 现有的 sector/theme 下拉 = **就是 scope 的 UI**,Rotation 点击只是去 set 它。
- **从 Rotation 点 sector/theme → set scope + 开 sector panel(inline drawer,非新 tab):**
  - **上半 = sector 聚合指标 summary(唯一真正新内容,filter 得不到):** breadth(%>MA50 / %>MA200)、dispersion、aggregate valuation、#at-52w-high、sector RS trail。
  - **下半 = members,复用不重建:** 用 Discovery 同款 evidence-card,scope 到该 sector,放 top-N 预览;每张卡 → Stock tab;按钮「在 Ocean / Valuation / Discovery 看全部成员」= set scope + 跳转。
- 同机制套 **theme**(点 theme → scope=theme → 全部 wide surface filter 到 theme 成员)。

**scope 语义(已定):**
- **single source of truth:** 只有一个 scope 状态;Rotation 点击 / Valuation 下拉 / Ocean 框选都是**写同一个 scope**,不是各 tab 各存一份 filter。后写覆盖前者,无「谁赢」歧义。
- **sticky:** scope 一直保持,直到显式换成别的或点 `✕` 清除。**切 tab 绝不偷偷 reset 成 all**(隐式 reset = 隐式 filter,同属 IA 失败)。
- **选 A — 点击只 set scope,不 auto-jump:** 点 sector → 改 scope + 在 Rotation 原地展开 sector panel;**不自动跳 tab**。换 view 由 sector panel 里那三个按钮显式触发。即「改 scope」与「换 view」是两个解耦的独立动作。

### 6.2 evidence-card = Stock 的 collapsed 态(已定)

**一个数据对象,两种渲染密度,沿 detail 光谱:**
- **collapsed = evidence-card**(扫描态:密、多、浅):price+volume+MA mini 图 + 几个**原始数字**(摊开,非 percentile)+ 角落 composite 角标(点开看 5 component 原始值 + 权重,无黑箱)+ AI「why moving」占位格。
- **expanded = Stock**(详情态:全、单、深):§6.5 那套完整视图。
- **点任意 card → 展开成 Stock。** Discovery 流 = 一堆 collapsed card;sector panel 成员预览 / scope 跳转落点 = collapsed card → 点开 expand。
- **不要把两者当两个东西做** —— 做成同一对象的 collapsed/expanded 两态。Stock tab 因此既是 expand 落地处,也是直接 ticker 查询入口。

**已定:** card 字段 = **6 个原始数字**(原始涨幅 1M/3M/6M、距 52w high %、突破后第几周、量/均量 `×`、market cap);**密度 = 一屏 3–4 张大卡**(2 列网格,图看得清细节)。每个 raw field 来自 bars 计算 → 图与数字内部一致。AI「why moving」一格占位待接入。

---

## 7. 不可妥协的约束(informed consent,非偏好)

1. **数千只放 Ocean(explore)可以;DECISION 必须 bounded。** 别让漂亮地图取代去 act 那 N 只。
2. **trail/箭头必须 selective(仅 pinned);Ocean static-per-snapshot + scrubber,永不 autoplay 全量。** 认知带宽硬约束。
3. **point-in-time membership 是硬要求**:membership 一改会 **回溯改写历史** → 否则 Ocean trail 和 RS-Ratio 线是 **虚构的**。
4. **主题指数别纯 cap-weight**(否则 "AI 主题"≈ NVDA 一只)→ equal/capped-weight;轮动视图 ~10–12 桶封顶。
5. **RS-Ratio(相对图)只讲相对**:熊市能 "Leading" 却绝对在跌 → **永远配绝对 regime(composite)一起读**。
6. **EDGAR segment 很脏**:大量公司不单列主题那条营收线 → LLM 抽取必然 **部分/近似**,human-in-loop,别宣称精确。
7. **P/S 是 TTM 滞后近似**(营收季度更新),界面别假装日频精确。
8. **scope filter 必须全程可见 + 一键清除**(dismissable chip,如 `Scope: Industrials ✕`);禁止「隐式 filtered 状态」—— 经典 IA 失败。
9. **所有 surface 来自单一 per-stock 引擎(数据一致性,已定):** Ocean 的 `(rs,val)` 位置、Stock 的价格/财务、Discovery 卡、Valuation 行**必须从同一份底层 per-stock 数据派生** —— 同一只票在任何 surface 上的数字都对得上、可互相追溯。(现状:mock 里 Ocean 序列与 Stock 的 `genBars` 是两套独立合成系统、对不上;真实管线禁止此分裂。)
10. **Ocean 必须 respect global scope(§6.1,原型 TODO):** scope = sector/theme 时,Ocean 应把非 scope 点 filter 掉或大幅变淡(框选/点 → 写同一个 scope)。当前原型 Ocean 尚未接 scope —— 待补。

---

## 8. DuckDB schema(起点,可演进)

```sql
universe(ticker PK, name, exchange, sector, industry, mktcap, is_active, first_seen, last_seen);
daily_bars(ticker, date, open, high, low, close, adj_close, volume, PRIMARY KEY(ticker,date));
fundamentals_q(ticker, period_end, filed_date, revenue_ttm, shares, total_debt, cash, ebitda_ttm, eps_ttm);
segment_revenue(ticker, period_end, segment, revenue);            -- from EDGAR, dirty
theme_membership(ticker, theme, exposure, as_of_date, source, approved_by);  -- many-to-many, point-in-time
derived_daily(ticker, date, ret_63, ret_126, rs_pct, rs_accel, high_prox,
              ma50, ma150, ma200, trend_quality, vol_ratio, ud_vol_ratio,
              ewmac_fast, ewmac_slow, composite, rank_in_universe);
valuation_daily(ticker, date, pe, ps, evs, ev_ebitda, peg, growth, margin, rule40);  -- ASOF-aligned
bucket_rrg(bucket_type, bucket, date, rs_ratio, rs_mom);          -- sectors + themes
spx_daily(date, close);
```
- 估值对齐核心:`valuation_daily` 由 `daily_bars` `ASOF JOIN fundamentals_q ON ticker AND date>=period_end` 生成。
- export:把 `derived_daily` + `valuation_daily` 最新快照 + `bucket_rrg` 拆成 Parquet/JSON 分片给 client。

---

## 9. 建议构建顺序(milestones)

- **M0 — 数据 + 引擎(先窄):** Stooq+Nasdaq+EDGAR ingest → DuckDB → 对 ~500 只(S&P 500 + 人工种子清单)算 composite + valuation。先证明数据拉得动、composite 直观。
- **M1 — Leaders + digest:** bounded top-N board + d/d + 每日 email digest(保证你真的会看)。(M1 期建过 early⟷reliable 旋钮,M7 后取消——核心转 ignition、composite 退固定权重确认。)
- **M2 — Ocean:** canvas + scrubber + pin→trail,轴固定 valuation×RS(无 RRG 模式);respect global scope(非 scope 点变淡)。
- **M3 — Rotation:** 11 SPDR ETF 的 RS-Ratio 多线图 + RS-rank 表 + breadth;点 bucket → N=1 单线 + 成员。
- **M4 — 主题分类:** EDGAR + LLM 营收锚定 membership(point-in-time,human-in-loop)→ theme RS-Ratio 线 / theme 上色。
- **M5 — Valuation screener + Stock detail:** duckdb-wasm 浏览器查询;per-name 面板。
- **M6 — 扩量:** universe 由 ~500 扩到数千(Stooq bulk 已支撑)。

---

## 10. 显式 OUT OF SCOPE(防 scope creep)

intraday / real-time;auth / 多用户 / 支付;**非美上市标的**;**中文 cross-language 判定(本期 descoped)**;backtesting 引擎(验证信号有效性是独立的事,别掺进监控管线);Ocean 全量 autoplay 动画。

---

## 11. 怎么用这份文件

- 把全文当 **Claude Code 的开工 prompt** 贴进去;或抽 §0–§7 + §10 作 **`CLAUDE.md`** 的核心约束。
- `equity-monitor-v2.jsx` 作 UX 参照对照 §6(布局/交互/配色已定)。
- 从 **M0** 起,先把 ~500 只跑通再扩量。

---

## 12. 交付就绪状态(handoff)

**`equity-monitor-v2.jsx` = UX 合同,不是实现**:合成数据(`mulberry32` 种子)、纯 inline SVG/canvas、无真实管线。它锁的是**布局 / 交互 / 信息层级 / 配色**;数据契约与算法以 §1–§5 为准。code 不要照抄它的造数逻辑。

**已定死(code 不要再翻案):**
- spine:**2 台 per-stock 引擎(composite 确认 + ignition 发现,§4.8/PRD §10.8)→ 5 surface → 2 scale → 零持久后端**(§0)。
- 数据源:Stooq(EOD)+ Nasdaq screener(universe/mktcap/GICS/PE)+ EDGAR(权威基本面)+ yfinance(脆弱兜底)(§2)。
- 5 surface 行为 + evidence-first(默认露原始证据,composite 只是可展开角标,永不给 buy/target)(§6、§6.2)。
- 数学:vol-normalized EWMAC、RS=双窗超额收益的横截面百分位、trend=KER/OLS t 值、composite=Σwᵢ·分量,权重 **固定 k=0.5**(曾经的 early↔reliable **旋钮已取消**——核心是 ignition、ignition 无可调参,§4/PRD §16)。
- **ignition(§4.8/PRD §10.8,已定;2026-06-14 定调为项目核心)**:早期发现第二台引擎、**项目核心技术指标**,5 短窗口分量→横截面 top decile;**瞬时无精度,唯 persistence(持续 ~5 日)有 lift**(实证 analysis/) → Discovery=「持续点火」榜;三级漏斗 = 触发→持续→翻财报。**无任何可调参**(刻意=买 robustness 不买 alpha);composite 退辅助确认(固定权重)。
- **核心是 ignition、composite 退辅助确认**:不回测优化、买 robustness 不买 alpha;ignition 无可调参、composite 用固定权重,全程暴露 composite 分量条(可看不可拨,§4.6),旋钮已取消。
- 估值统一规则:price ÷ trailing-4Q,日频(分母季度 ASOF、分子日频),`E≤0→n.m.` 退 P/S,无 forward;**百分位用 common-vintage**(只在当期 cohort 内排名,stale 不进)(§4.5)。
- Rotation = **RS-Ratio 多线(非散点)**;Ocean 轴固定 RS×估值(**RRG-axes 已砍**)(§4.4、§6)。
- 全局 scope(all|sector|theme|pinned)单一真源、跨 tab 粘滞、可见可一键清,Discovery/Valuation/Rotation/**Ocean** 全respond(§6.1、§7 item 10)。
- point-in-time membership 硬要求;theme 指数非市值加权(§7)。

**留给 code 的实现级决策(非翻案):**
- 权重具体常数、trend 取 KER 还是 OLS t 值、Kalman 是否上(§4.3、§4.7)。
- theme membership 的营收阈值、LLM→human 审核流的具体形态(§5.2)。
- common-vintage 的 coverage 门槛具体 %(mock 用 ≤95 天近似,真实按"末季 ≥X% 已报")(§4.5)。
- **Ocean lasso 框选 set scope**(mock 只做了 respect/变淡,框选是真实版功能)。
- 客户端框架、duckdb-wasm 接法、shard 切分粒度(§1、§3)。

**怎么开工**:全文当 kickoff prompt → 从 **M0**(~500 只跑通端到端)起。
