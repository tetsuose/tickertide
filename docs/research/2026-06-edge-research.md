# Edge research (2026-06) — 能不能比 evidence-first 更会"预测/择时"？

> **渐进式披露决策文档**。L0 入口=一屏看完裁决 + 元结论 + 决策；L1=每个实验一节；L2=复现 + 纪律。
> 全部实验在 `analysis/*.py`，参数无拟合、防前视、对 trivial baseline 比增量。脚本 docstring 是最细一层。

## L0 · 一屏结论

**起因**：用户要"比盯涨跌榜发现更动量更稳定的上涨"、并横向评估若干"预测/择时"思路（含 LightGBM risk-regime、火箭择时）。本轮把每个思路当**可证伪假设**严格实测（不拿教义否决；merit 评判）。

**8 个实验的裁决：**

| # | 实验 (脚本) | 问题 | 裁决 | commit |
|---|---|---|---|---|
| 1 | `method3_regime` | LightGBM 预测美股 risk-regime(p_bad)能否当板块轮动指标 | **否**：ΔAUC over 一行 VIX/HAR ≈0~负；2020-COVID 留出 AUC≈0.05(劣于随机);且 p_bad 是市场层标量、无板块横截面信息→当轮动唯一指标是范畴错误 | `6c8d1a5` |
| 2 | `stable_momentum` | "更动量更稳定"排序能否胜过涨跌榜 | **能(温和)**：盯涨跌榜=显著负IC(反转);稳定动量(12-1+KER+低波动)正IC且前向更稳(vol 38-42% vs 53-54%、回撤更浅)。但量级弱、regime-dependent | `3a6ad2a` |
| 3 | `momentum_vs_breakout` | 稳定动量相对现有 base→breakout 引擎加不加价值 | **冗余**：同池同选择度下条件IC≈0(CI跨0)、各项几乎相同；Jaccard 0.16=随机3.4x(偏冗余非互补)。现有引擎已体现"更动量更稳定" | `e3e219e` |
| 4 | `smooth_winners` | 反推"半年平滑大涨赢家"的起涨形态 | **赢家极稀有**：64年/721票仅51个达标→平滑大涨是小概率;人在环看图+提取形态的工具 | `28209cf` |
| 5 | `theme_washout` | "买深度 washout 主题、转向入场"有无 edge | **否**：FF49行业百年 n=1015,lift +0.9% CI[−0.9,+2.7]跨0;强regime依赖(2020s+15% vs 1930s/2000s≤0)、46%接飞刀。2025半导体反弹=百年最旺regime的一次抽样 | `47efa60` |
| 6 | `rocket_launch_signature` | 用户10个火箭模板的起涨形态能否预测火箭 | **否**：朴素2x lift 经 vol-matched 控制塌成0.97x=纯波动率选择(+幸存者);washout+turn 真增量≈0、转向那步还负 | `886647a` |
| 7 | `vix_riskoff` | "VIX高→risk-off"是不是领先卖信号 | **不是**:VIX 同步/滞后(corr trailing −0.42),高VIX后前向收益反而更高(contrarian);唯一可靠预测=前向波动更高;唯一合法用法=vol-targeting/sizing/context 非方向 | `4a6337f` |
| 8 | `sector_vol` | 能否算各板块 VIX | **能(realized-vol版)**:真隐含VIX需期权历史无免费源;板块 realized-vol 指数 corr市场VIX 0.73-0.84,可用作 sizing/context(当前 XLK 40%/91分位最颠) | `908ac7a` |

**元结论（8 次实测反复钉死）**：**在美股 EOD 这个域，"预测哪个会涨 / 择时进出"没有稳健的前向 edge——个股、主题、市场三个层面都验证过。** 看似有 edge 的结果，剥掉 confound 后都塌：survivorship(深跌归零者缺席)、volatility-selection(高波动票方差大、易摸大数)、regime luck(2020s 是百年最旺)。唯一稳健的是：

- **evidence-first / recall-first**：工具负责把处境+赔率透明摊开(recall+证据)，precision 交给用户+基本面。edge 来自用户判断，不是信号。
- 这**反向验证了现有脊柱**(base→breakout 召回优先、不回测买 alpha、evidence-first)——注意是 merit 实测验证、非教义假设。

**产品决策：**
- **不做**：method3 p_bad 过滤器/轮动指标;recency-decay 修复;新增 stable-momentum 排序轴(冗余);把火箭/washout 择时当 edge;任何"高VIX就 risk-off"的方向闸门。
- **可做(唯一落地正产出)**：`sector_vol` 的**板块/主题 realized-vol "湍流"层**——只读 evidence(当前值+历史分位+对大盘比)，明确用作 **sizing/context 非方向**;同法可上 evidence-first 的原始证据露出(distance-from-high / 转向 / 回撤 / 赔率)。

---

## L1 · 每个实验

> 共同纪律(见 L2)：信号只用 ≤t 数据、label 严格前向;对**正确的 baseline**比增量(trivial 规则 / vol-matched / 行业内均值);幸存者偏差用 rank/lift/episode-CI 抗;regime 拆解;参数无拟合。

### 1. method3_regime — LightGBM 美股 risk-regime（Tier A 决定性首测）
- **Q**：p_bad_20/60 能否预测"不利交易环境"、并当板块轮动唯一指标？
- **法**：ETF(SPY/QQQ/IWM/RSP+9 SPDR 行业,幸存者免疫)+免key FRED(VIX/BAA10Y/国债曲线);label=SPY forward vol/drawdown;purged+embargoed walk-forward + leave-one-crisis-out;**headline=ΔAUC over 一行 VIX-pct / HAR-RV**。
- **数**：4 配置 wf ΔAUC −0.07~0.00、胜率≤0.67;headline AUC(vol20 0.79)≈VIX-pct(0.77);`vix_pct` 是压倒性 #1 特征=AUC 多为免费 vol persistence;**2020-COVID 留出 LGBM AUC≈0.05(劣于随机)** vs VIX-pct 0.45-0.58。
- **裁决**：无可靠增量,不迁移。**且 p_bad 是市场层标量、无"哪个板块更强"的横截面信息→当板块轮动唯一指标是范畴错误**。STOP,不买 Tier B 成分股数据($630/yr)。

### 2. stable_momentum — "更动量更稳定" vs 盯涨跌榜
- **Q**：按趋势质量/平滑排序，能否胜过"过去N日涨最多"？
- **法**：721 真实美股、1962-2026、552 formation dates、forward 21/63d;信号 ret_5/21/63(涨跌榜) vs slope×R²(Clenow)/KER/vol-adj Sharpe;判 forward 收益(IC/top-bot)+ forward 稳定性(vol/回撤/ret-vol)。
- **数**：ret_5(周涨幅榜)IC=−0.036/−0.021(t≈−7/−4,**显著反转**);mom_12_1 IC+0.028/+0.030、ker_63+0.017/+0.018(t>4);稳定动量 top-decile 前向 vol 38-42% vs 涨幅榜 53-54%、worst drawdown −6/−11% vs −8/−14%。
- **裁决**：**初衷成立但温和**——盯涨跌榜反生产;稳定动量主要买"更稳的上涨"(更低波动/回撤)非超额收益。最有效成分=12-1 momentum+KER+低波动,**仓库 derived_daily 已算好**(trend_quality/vol_ratio)。

### 3. momentum_vs_breakout — 稳定动量 vs 现有 base→breakout（v2 fair）
- **Q**：stable-momentum 相对现有引擎是补充/替换/冗余？
- **法**：经对抗审查修掉 v1 致命不公平(breakout 只在 ~20% 合格池选 vs stable 全池真前10%、且门槛自带低波动 buff);**决定性=池内同选择度 + 条件IC**(stable_mom 排名能否在 breakout 已筛过票里加价值,同总体可比)+ block-bootstrap CI + chance-null Jaccard。
- **数**：池内 stable/breakout/combo 各项几乎相同;条件 IC stable≈+0.002/−0.000、breakout≈−0.005,**CI 全跨0**;Jaccard 0.16=随机(0.05)的 **3.4x**(比随机更重叠=偏冗余)。
- **裁决**：**REDUNDANT**。现有 base→breakout 已体现"更动量更稳定";momentum 的价值在 eligibility 门槛(剔涨跌榜垃圾)非细排名。**别新增/替换排序轴**。

### 4. smooth_winners — 反推"半年平滑大涨"赢家的起涨形态
- **Q**：找"半年连续高增长+低回撤+平滑"的票,看图认可,提取起涨形态。
- **数**：64年/721票仅 **51 个**达标(base rate 0.0014%/stock-day)→平滑大涨极稀有;中位 ret126 +58%/maxDD −6%/KER 0.62。NVDA/SNDK 等热门半导体**不达标**(KER 0.34-0.47 不平滑、深回撤)=另一原型(火箭)。
- **裁决**：人在环看图+提取形态的工具;"平滑复利"原型与"爆发火箭"原型互斥,后者→实验 5/6。

### 5. theme_washout — 主题 washout 反弹择时（archetype B：主题层）
- **Q**：火箭一起launch off 板块 washout→"买深度washout主题、转向入场"有edge吗？
- **法**：Ken French 49 行业 VW 日频(1926-2026,幸存者免疫);信号=行业过去一季≥35%回撤 + 站回50日线;lift=前向126d 收益 − 行业无条件均值;by-decade + block-bootstrap + 接飞刀诊断。
- **数**：n=1015,**LIFT +0.9% [CI −0.9%,+2.7%] 跨0**;强 regime 依赖(1980s+8%/1990s+11%/**2020s+15.1%(百年最旺)** vs 1930s−5.4%/2000s−0.4%),仅45%decade为正;**46%信号后续跌>15%**(接飞刀);turn 确认反更差。
- **裁决**：**无可靠 edge**;是 regime 赌注。2025 半导体反弹=最旺 regime 的一次抽样 + 记忆幸存者偏差(记得 NVDA、忘了 2022 软件washout买家−24%)。

### 6. rocket_launch_signature — 用户10个火箭模板的起涨形态（archetype B：个股层）
- **Q**：用户认可的 MU/CRDO/COHR/SITM/LRCX/MTSI/KLAC/TSM/AVGO/NVMI,其起涨共同形态能否预测火箭？
- **法**：提取起涨签名(因果≤launch)=高波动~60%+深washout~−40%+站回50日线近200日线;label=forward 252d max-drawup≥+100%;**关键控制=vol-matched 基准**。
- **数**：朴素 lift 1.97x(base 9.1%→signal 17.9%)**看着像edge,但 vs 同等高波动同侪=0.97x**——P(rocket|高波动)本就18.4%(高波动票方差大、易摸+100%);washout 之上仅1.08x、+reclaim 转向 0.94x(负)。+幸存者偏差(深跌归零者缺席)。
- **裁决**：**无真 edge**;模板签名本质="挑波动大的暴跌票"。当前 screen(NNE/CRSP/biotech 等9只)=高方差 watchlist 非 edge。**坑:测 rare 大涨 label 务必用 vol-matched 基准,否则波动率选择伪装成 2x**。

### 7. vix_riskoff — "VIX高→risk-off"是不是领先指标
- **数**(VIXCLS vs ^GSPC,1990-2026,n=9182)：corr(VIX,trailing21d)=−0.42(同步/滞后,随跌而起)、corr(VIX,forward21d)=+0.10;分桶 VIX<13 前向年化+8% vs **>40 前向+34%(contrarian)**;前向 vol 单调 9%→45%;vol-targeting(高波动减仓)Sharpe 0.46→0.57、max log-dd −0.84→−0.70。
- **裁决**：**不是领先卖信号**(卖高VIX=卖在底);高VIX唯一可靠预测=**前向波动更高**。用法=**vol-targeting/sizing/context + 极值 contrarian tilt,非方向择时**。澄清 method3 的"VIX→risk-off"指同步风险态。

### 8. sector_vol — 各板块"VIX"
- **数**(asof 2026-06-17)：realized-vol 板块指数(真隐含VIX需期权历史,无免费源);各板块 rv21 + 自身历史分位 + 对SPY比 + 对市场VIX corr(0.73-0.84,代理成立);**XLK 科技 40%/91分位/2.47×SPY 最颠**(AI-semi),金融XLF/通讯XLC 最静(15%/~40分位)。
- **裁决/产出**：**唯一可落地的市场层产出**。读作湍流/sizing/context(高vol=该板块减小仓,非"卖该板块");同法可上 theme 篮子。输出 `data/sector_vol_summary.json` 可喂 UI。

---

## L2 · 复现 + 纪律

**环境(研究专用,绝不进 repo requirements.txt、绝不被 engine/compute/export import)**：
```
pip install "lightgbm>=4.6" "scikit-learn>=1.7" "statsmodels>=0.14" "scipy>=1.11" "matplotlib>=3.8"
# 仓库已有 pandas/numpy/duckdb/yfinance;venv 为主仓库 .venv(Python 3.14)
/Users/.../.venv/bin/python analysis/<script>.py
```
**数据源(全免费、网络)**：yfinance(ETF/个股,survivorship-immune ETF / still-listed 个股有幸存者偏差) · 免key FRED `fredgraph.csv`(VIX/BAA10Y/国债;BAML OAS 被 3 年上限卡→用 BAA10Y) · Ken French 49 行业(幸存者免疫)。产出落 gitignore 的 `data/`(缓存 pkl/JSON/PNG)。

**方法学纪律(每个实验都守)**：
- **防前视**:特征只用 ≤t;label 只用严格前向 (t, t+H];vol-label 阈值用 expanding 分位;fitted 模型用 purged+embargo(消标签重叠泄漏)。
- **对的 baseline**:不报绝对数,报相对**正确对照**的增量——trivial 一行规则(VIX/HAR)、vol-matched 同侪、行业内无条件均值、chance-null Jaccard。
- **幸存者偏差**:still-listed 池抬高所有动量/火箭;靠 rank-IC、top-bot、episode-CI、vol-matched 抗;绝对水平不可作 live-tradable。
- **少 episode**:危机/赢家稀有→报 per-fold/per-decade/per-crisis spread 与 block-bootstrap CI,不靠点估计。

**与脊柱关系**：以上结论从反面验证了 PRD §16 已定死的脊柱(base→breakout 召回优先、不回测买 alpha、evidence-first)——但这是 merit 实测的验证、不是把教义当公理。
