# themes/ — 语义主题分类（营收锚定）

> 模块职责：用 LLM + EDGAR 营收锚定生成 ticker↔theme 的 point-in-time membership。**Pre-M0（planned）。**

## 职责

标准底（GICS-ish，直接用 Nasdaq screener 的 sector/industry）之上，叠加**概念主题**的多对多 membership，带连续 exposure 权重。

本期主题清单：**AI、智能机器人、太空算力、光模块**，加 半导体 / 核能 / 网安 / 云。NVDA 同进 AI 和 Semis 是 feature 不是 bug（绝不强加 MECE）。

## 核心方法（语义 + 营收锚定）

1. LLM 读 **EDGAR 10-K/10-Q 的 business + segment 段**（英文）。
2. 抽取该主题的**营收暴露** → `membership.exposure = revenue_share`（连续，非二元）。把 fuzzy 主题钉在可证伪的数字上。
3. **human-in-loop 审批**：LLM 当 candidate generator + revenue extractor，**不当权威 classifier**。
4. **point-in-time**：`t` 时刻 membership 只反映 as-of `t` 已披露信息。

## 输入 → 输出

- 输入：`ingest/` 的 `segment_revenue` + EDGAR filings 文本。
- 输出：`theme_membership(ticker, theme, exposure, as_of_date, source, approved_by)`（schema 见 PRD §12）。

## 约束（硬要求）

- **point-in-time membership 是硬要求**：membership 改写会回溯改写历史，否则 Ocean trail / theme RS-Ratio 线虚构（PRD §7 item 3）。
- **EDGAR segment 很脏**：大量公司不单列主题营收线 → LLM 抽取必然部分/近似，human-in-loop，别宣称精确（PRD §7 item 6）。
- **主题指数非市值加权**：否则「AI 主题」≈ NVDA 一只 → equal/capped-weight（PRD §7 item 4）。

## 规格来源

PRD §8（分类本体）、§12（schema）、BUILD-PLAN §5。营收阈值与审核流形态是实现级决策（PRD §17）。

## 未来文件

`run.py`（候选生成 + 抽取）、`extract.py`（LLM segment 营收抽取）、`review.py`（human-in-loop 审批）、`themes.yaml`（主题定义）。

## Milestone

M4（EDGAR + LLM 营收锚定 membership → theme RS-Ratio 线 / theme 上色）。
