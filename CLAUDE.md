# CLAUDE.md — TickerTide

> Claude Code 的项目入口。**薄入口**：只放约束与导航，不承载滚动状态。
> 权威规格在 `docs/PRD.md`；UX 合同在 `docs/equity-monitor-v2.jsx`；工作流在 `docs/workflow/WORKFLOW.md`。

## 0. 这是什么

一个 **盘后(EOD)、美股专属** 的 momentum + valuation 监控工具。
**脊柱：单一核心筛法 steady-riser（连续上涨，PRD §10.8，2026-07-02）→ 五个 lens，两个尺度(wide explore / bounded decide)，零常驻 backend。**

**SCOPE（不可越界）：** 仅限美股(NYSE/Nasdaq/AMEX，ADR 可纳入；**ETF 已拍板纳入、落地推后**，PRD §17)；中文/cross-language 标的判定本期不做。

## 1. 脊柱原则（贯穿所有 surface，code 不要翻案）

- 核心筛法 = **steady-riser（连续上涨）**：把「每天扫几千张 K 线找过去一两周持续走高、回撤少的票」数学化——W=10 天净涨幅(net5/10/20)/上涨天数占比(up10)/窗口内最大回撤(ddw10)/路径效率(ker10)，gate=`up10≥0.6 & net10>0`、按 net10 排序取 top-N(50)。**算法三条硬要求：简单、不易出错、图上可验证（与直观相符）；不指向预测收益**（recall 工具，precision 归用户翻财报）。
- **五个 lens 共用同一份 per-stock 数据**（C9 硬约束；`rise_candidate` 由 compute 层单一真源，export/前端只读不重算）。
- Risers=连续上涨榜 / Rotation=RS-Ratio group-by / Ocean=rise_net10_pct×估值二维相图 / Valuation=横截面 / Stock=单票展开。
- 两个尺度：wide/explore(Ocean、Valuation screener，数千只) + bounded/decide(Risers、Rotation)。
- **无可调 alpha 参**(W=10、up≥6/10、N=50 是 UX 常数)；**平滑度(ker/ddw)绝不做硬 gate**(exp 10 反例：严平滑 gate 漏 SNDK 到 d66——真火箭初期不平滑)，只做证据列。
- **evidence-first**：默认露原始证据(每个数字在 K 线图上可人工数出来)，永不给 buy/target；不回测优化、不声称前向收益(exp 10 picks≈池中位)，买 robustness 不买 alpha。
- **base→breakout / ignition / composite 全部退役**(PRD §10.6/§10.9 历史锚点)。

## 2. 开工前必读（权威顺序）

1. `docs/PRD.md` — 完整产品需求（**权威规格**，本仓库的 SoT）。
2. `docs/ROADMAP.md` — 里程碑开发方案（PRD §13 的执行展开：当前进度 + 各 M 的 task 拆解；**开工前看你这个 M 的段**）。
3. `docs/BUILD-PLAN.md` — 构建计划 + 数学规格（kickoff prompt 原件）。
4. `docs/equity-monitor-v2.jsx` — UX 合同（锁定 layout/interaction/hierarchy/color；**不是要跑的代码**）。
5. `docs/workflow/WORKFLOW.md` — 工作流 policy（merge 边界、权威顺序、decision gate）。

## 3. 内建工作流（硬约束，不是建议）

本仓库内建两套机制：**devtopology**（文件合同 + 硬 gate）+ **workflow-system 理念**（PR 为合并边界、任务隔离）。

- **新任务起手**：`make route` 读路由 → `make task-open QUERY="..."` 开隔离 worktree。**一个 worktree 一个 merge intent。**
- **改/增文件**：在 `docs/runtime/File-Contracts.json` 更新该文件合同（`purpose`/`invariants`/`verification`，禁占位 `TODO`/`TBD`）。新增文件先 `make writeback-apply WRITE=1` 登记再填合同。
- **提交前**：`make verify` —— 两个 gate 必须 `GATE_PASS`：
  - `structure_contract_coverage`（每个文件有合同条目）
  - `changed_file_contract_semantics`（变更文件合同非占位）
  - **`GATE_FAIL` 是硬停，不是警告。**
- **收口**：`make accept GOAL="..."` 生成验收摘要 → 开 PR → 自动合并(`gh pr merge --merge --delete-branch`) → `make task-close`。**merged 才是 done**，不停在 open PR（除非真实 blocker 或人工暂停）。

## 4. 关键命令

| 命令 | 用途 |
|---|---|
| `make route` | 任务路由：docs-only / branch 建议 / structure-trigger |
| `make task-open QUERY="..."` | 开隔离 worktree + 分支 |
| `make start QUERY="..."` | 加载拓扑 + drift 检测 |
| `make verify` | 跑两个 gate（提交前必须通过） |
| `make writeback-apply WRITE=1` | 同步合同账本（增删文件后） |
| `make enforce-fill MODULE=...` | 限定改动在单一模块 |
| `make accept GOAL="..."` | 生成 acceptance comment |
| `make task-close` | 收口：查 PR 状态 + 下一步 |
| `make pipeline` | 数据管道（M0 占位：ingest→compute→export） |

## 5. 模块拓扑（`make atlas` 看全貌）

`ingest/`(Stooq+Nasdaq+EDGAR 拉取) · `compute/`(DuckDB riser/RS/valuation) · `export/`(Parquet/JSON 分片) · `web/`(canvas + duckdb-wasm 客户端) · `themes/`(主题 membership，LLM+human-in-loop) · `engine//scripts//gate/`(devtopology 工作流) · `docs/`(规格)。

## 6. 三层状态协议

入口 `docs/agent-state/README.md`：L1 Git 状态 / L2 运行时环境 / L3 任务态。按需只读匹配层，不默认全量加载。

## 7. 已定死（code 不要再翻案，详见 PRD §16 / BUILD-PLAN §12）

- spine：**单一核心筛法 steady-riser（连续上涨，2026-07-02）** → 5 surface → 2 scale → 零持久后端。**base→breakout / ignition / composite 全部退役。**
- 数据源：Stooq(EOD) + Nasdaq screener(universe/mktcap/GICS/PE) + EDGAR(权威基本面) + yfinance(脆弱兜底)；ETF 纳入已拍板、落地推后(PRD §17)。
- 数学：**核心 = steady-riser（PRD §10.8）**——`rise_net5/10/20`(净涨幅)、`rise_up10`(上涨天数占比)、`rise_ddw10`(窗口回撤)、`rise_ker10`(路径效率)，gate=`up10≥0.6 & net10>0`、net10 排序 top-50、`rise_candidate` 单一真源(前端读导出值不重算 C9)；辅助：vol-normalized EWMAC、RS=双窗超额收益横截面百分位、trend=KER/OLS t 值。early⟷reliable 旋钮已取消。
- **平滑度绝不做硬 gate**(exp 10：严平滑 gate 把 SNDK 挡到 d66；ker/ddw/up 是证据列)；漏斗=recall-first 筛选→基本面/财务 precision(human)。
- 估值：price ÷ trailing-4Q 日频(分母季度 ASOF)、**formal-filing PIT**(分母只用正式 SEC filing、ASOF 键=`effective_eod_date`(v1==filed_date)非 period_end、`valuation_basis='formal_filing_pit'`；PRD §10.5)、`E≤0→n.m.` 退 P/S、无 forward、百分位用 common-vintage(当前 fresh-cohort v1)。
- Rotation = RS-Ratio 多线(非散点)；Ocean 轴固定 rise_net10_pct×原始 P/S log(**RRG-axes 已砍**)。
- 全局 scope(all|sector|theme|pinned)单一真源、跨 tab 粘滞、可见可一键清。
- point-in-time membership 硬要求；theme 指数非市值加权。

## 8. Rules

- `engine/index.py` **零外部依赖**（Python stdlib only），不要 `pip install`。
- 不写 secrets / 私有 endpoint / 密码到仓库、PR、日志。`.env`、真实 inventory 走 gitignore（见 `docs/runtime/Credentials-Management.md`）。
- 文件系统大小写不敏感（macOS）：目录统一小写；`core.ignorecase=false` 已设，勿引入仅大小写不同的路径。
- 合同描述 *what/why*，不写 *how*；不留占位合同。
- 首次仓库播种允许直推 `main`；此后产品开发遵循 worktree + PR。
