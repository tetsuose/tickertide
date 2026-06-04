<div align="center">

# TickerTide

**US equity momentum + valuation monitor — personal, end-of-day, zero-backend.**
**一个个人自用、盘后、美股专属的动量与估值监控工具。**

</div>

---

一套信号，五个 lens，两个尺度。一个 stock-level `composite` 引擎驱动五个 surface(Ocean / Discovery / Rotation / Valuation / Stock)，离线预计算 + 静态分发，零常驻后端。

> **SCOPE：** 仅限美股(NYSE/Nasdaq/AMEX，ADR 可纳入)；个人工具、**不对外分发数据**；中文 cross-language 标的判定本期不做。

## 文档导航

| 文件 | 内容 |
|---|---|
| [docs/PRD.md](docs/PRD.md) | **完整产品需求文档**（权威规格，SoT） |
| [docs/BUILD-PLAN.md](docs/BUILD-PLAN.md) | 构建计划 + 数学规格（kickoff prompt 原件） |
| [docs/equity-monitor-v2.jsx](docs/equity-monitor-v2.jsx) | UX 合同 mock（锁定 layout/interaction/color，非实现） |
| [docs/workflow/WORKFLOW.md](docs/workflow/WORKFLOW.md) | 内建工作流 policy |
| [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) | AI agent 入口 |

## 架构（fomo5000 范式：离线预计算 + 静态分发）

```
GitHub Actions (nightly cron, post-US-close)
  └─ ingest:   Stooq (bulk EOD) + Nasdaq screener (universe/cap/sector/PE) + SEC EDGAR (fundamentals/segment)
  └─ compute:  DuckDB → derived_daily + composite + RS-Ratio + theme membership + percentiles + ASOF valuation
  └─ export:   snapshot → Parquet/JSON shards
  └─ deploy:   Cloudflare Pages (static)
Client (canvas + duckdb-wasm): renders Ocean (thousands of points) + boards; screener queries Parquet in-browser
```

无常驻 server、无托管 DB、不向 client 暴露任何 key。

## 仓库结构

```
docs/                  规格与运行时文档
  PRD.md               完整产品需求（权威）
  BUILD-PLAN.md        构建计划 + 数学规格
  equity-monitor-v2.jsx  UX 合同 mock
  workflow/WORKFLOW.md   工作流 policy
  agent-state/README.md  三层状态协议入口
  runtime/             File-Contracts.json (合同账本) + 凭证管理模板
ingest/  compute/  export/  web/  themes/   产品模块（pre-M0，见各自 README）
engine/  scripts/  gate/                     内建工作流（devtopology，零依赖）
skills/                devtopology + workflow-system skill 定义
Makefile  devtopology.yaml                   编排与配置
```

## 内建工作流（devtopology + workflow-system）

本仓库从第一天就用**文件合同 + 硬 gate** 防止 AI agent drift，用 **PR 为合并边界 + worktree 隔离** 保证任务收口。

```bash
make help            # 所有命令
make route           # 新任务路由（docs-only / branch / structure-trigger）
make verify          # 提交前两个 gate（structure coverage + contract semantics）
make atlas           # 模块/kind/stage 拓扑全貌
```

详见 [docs/workflow/WORKFLOW.md](docs/workflow/WORKFLOW.md)。零依赖：Python 3.10+ stdlib + bash + git，无 `pip install`。

## 里程碑

`M0` 数据+引擎(~500 只跑通) → `M1` Leaders+digest → `M2` Ocean → `M3` Rotation → `M4` 主题分类 → `M5` Valuation screener+Stock → `M6` 扩量至数千。详见 [PRD §13](docs/PRD.md)。

## 状态

**Pre-M0** — 规格与工作流脚手架已就绪，产品模块为规划态(`planned`)。
