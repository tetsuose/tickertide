# web/ — 静态客户端（5 个 surface）

> 模块职责：渲染五个 lens 的浏览器端 UI。**UX 合同 = `docs/equity-monitor-v2.jsx`**（锁 layout/interaction/hierarchy/color）。**Pre-M0（planned）。**

## 职责

零后端 client：canvas 渲染 Ocean（数千点）+ 各 board；Valuation screener 用 **duckdb-wasm** 在浏览器查 `export/` 的 Parquet 分片。

## 五个 surface（详见 PRD §9）

1. **Ocean**（canvas，wide）：x=RS pct, y=Valuation pct（底=便宜），color=sector/theme，size=mktcap；周度 scrubber（无 autoplay）；点击 pin→箭头 trail（仅 pinned）。
2. **Discovery**（evidence-first 卡流）：候选池 + AI 兜底筛；每张卡 = Stock 的 collapsed 态（6 个原始数字 + composite 角标）。
3. **Rotation**（narrow）：所有 sector/theme 的 **RS-Ratio 多线图（非散点）** + enriched league 表；点 bucket→N=1 单线 + 成员卡。
4. **Valuation**（screener，wide）：横截面表 + sector/theme 内 percentile（common-vintage）；duckdb-wasm 查询。
5. **Stock**（narrow，expanded 态）：时间轴对齐的 price↔fundamentals stack（K线 + MA + 量 + 季度营收 bars + P/S over time，季度网格贯穿）。

## 全局原语

- `early⟷reliable` 旋钮（k 值，重配 composite 权重 + 分量条）。
- **global scope filter**（all|sector|theme|pinned）：单一真源、跨 tab 粘滞、可见可一键清；Ocean/Discovery/Valuation/Rotation 全 respond，Stock 不受影响。
- evidence-card collapsed/expanded 同一对象两态。

## 配色与视觉语言

暗色唯一方案（`--bg #080b11`）；象限/sector/theme/freshness 上色见 PRD §9 配色表（直接取自 UX 合同）。

## 约束

- **trail/箭头仅 pinned；Ocean static-per-snapshot + scrubber，永不 autoplay 全量**（认知带宽）。
- 所有 surface 数字从同一 per-stock 引擎派生（禁止 mock 里那种两套合成系统对不上）。

## 未来文件

框架/duckdb-wasm 接法是实现级决策（PRD §17）。预期：`index.html`、`src/`（5 surface 组件）、`src/ocean-canvas.*`、`src/duckdb-client.*`。

## Milestone

M2（Ocean）→ M3（Rotation）→ M5（Valuation screener + Stock detail）。
