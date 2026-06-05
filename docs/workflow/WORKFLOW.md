---
role: runbook
status: active
scope: repo
---

# TickerTide 工作流 policy（PR 驱动 + 结构门禁）

> 何时读：需要确认长期有效的协作模式、权威顺序、merge 边界、gate 触发或验收标准时。
> 本文是 policy；逐步 recipe 见 `skills/workflow-system/SKILL.md` 与 `skills/devtopology/SKILL.md`。
>
> 本仓库内建两套机制：
> - **devtopology**（`engine/` `gate/` `scripts/worktree.sh` + `docs/runtime/File-Contracts.json`）—— 文件合同 + 硬 gate，防 AI agent drift。
> - **workflow-system 理念**（本文 + `scripts/task_router.py`）—— PR 为合并边界、worktree 隔离、acceptance 为验收 SoT。

默认协作模式：**GitHub 为 SoT、PR 为合并边界、PRD/File-Contracts 驱动实现、静态 bundle 驱动部署。**

---

## 1) 权威顺序

新任务起手，按此顺序建立上下文：

`User Instructions > PR/Issue 契约 > docs/PRD.md(规格) > docs/runtime/File-Contracts.json(合同) > 触发式结构产物(.index/*)`

- `docs/PRD.md` 是产品规格 SoT；`docs/BUILD-PLAN.md` 是其来源与数学细节；`docs/equity-monitor-v2.jsx` 是 UX 合同。
- `.index/` 下的 mirror/atlas/health 都是生成物，不是权威输入。
- 临时笔记、scratch、日志都不是验收 SoT。

## 2) merge 边界与任务分流

- **`branch/PR` 是唯一合并边界；窗口/会话不是。**
- **一个可合并意图 = 一个 branch = 一个 PR = 一个 worktree。** 一个改动需要两个 PR 标题时，先拆。
- 同一 worktree 只承载一个 merge intent；发现第二个任务直接 `make task-open` 新开。

遗留问题分级：
- `A` 强相关 → 可留当前 PR。
- `B` 弱相关、可独立 review → 拆新 branch/PR。
- `C` 历史残留/上下文不清 → 转独立修复流。

路由（`make route` 自动判定）。统一分支形态 **`<prefix>/<date>-<descriptor>`（date-first）**，`make task-open`(worktree.sh) 与 `make route`(task_router.py) 共用同一套前缀规则——前者 descriptor 取 query slug，后者取模块名：
- **docs-only**：全部变更落在 `docs/`（不含 `docs/runtime/File-Contracts.json`）→ `docs/<date>-<descriptor>`。
- **workflow-only**：全部落在 `engine/ gate/ scripts/ skills/ .github/ docs/workflow/ docs/agent-state/` 或顶层入口/配置 → `chore/workflow-<date>-<descriptor>`。
- **product**：落在 `ingest/ compute/ export/ web/ themes/` → `feat/<date>-<descriptor>`（默认前缀；`make task-open` 不带 `TASK_KIND` 即此）。
- 混合（plumbing + product）默认视为可能混了两个任务，优先拆。

## 3) 结构门禁触发（devtopology）

`mirror / atlas / start / writeback / enforce-fill` 只在触发成立时跑（`make route` 输出 `STRUCTURE_TRIGGER`）：
- `A` 结构性改动：engine/ gate/ scripts/ docs/runtime/ Makefile devtopology.yaml、新增/删除模块目录。
- `B` 规划型任务：需用结构产物对齐 PRD / File-Contracts（PRD、BUILD-PLAN、模块 README）。
- `C` 结构 gate：File-Contracts coverage 或 `enforce-fill`。

规则：所有写 SoT 的动作必须显式 `WRITE=1`；所有 writeback 必须**先 preview 再 apply**。
`STRUCTURE_TRIGGER=none` 时不要跑结构命令。

## 4) 合同纪律（硬约束）

- 每个文件在 `docs/runtime/File-Contracts.json` 有一条合同：`purpose`(做什么) / `invariants`(必须为真) / `verification`(怎么确认)。
- 合同写 *what/why*，不写 *how*；禁占位(`TODO`/`TBD`/`none`/空)。
- 新增/删除文件后：`make writeback-apply WRITE=1` 同步账本，再填新条目合同。
- 推进 stage：`scaffolded > baseline > planned > implemented > verified > done`，一次不跨超过一级。
- 提交前 `make verify`，两个 gate 必须 `GATE_PASS`：
  - `structure_contract_coverage`（无 missing/stale）
  - `changed_file_contract_semantics`（变更文件合同非占位）
- **`GATE_FAIL` 是硬停。** 修好再提交，不要跳过。

## 5) 工作区卫生与三端对齐

脏工作区/本地与 GitHub 不齐的根因通常是「同一工作区承载多个未收口任务」。原则：
- **先隔离再修改**：新任务先 `make task-open`。
- **任务必须收口**：默认完成态是 `merged` 或 `drop`；只有真实 blocker / 人工暂停才停在 `PR open`。
- **每步带 SHA**：本地 `HEAD`、PR `head_sha`、acceptance 的 `head_sha` 必须对应同一 revision。
- **push 前干净**：dirty worktree 不 push。

最小检查：
```bash
git status --short
make task-status
make task-close      # 输出 open_pr / wait_or_merge / drop
```

## 6) 验收证据与 PR 标准

- 验收 SoT = **PR acceptance comment + 对应 gate 输出**。
- 每个任务结束在 PR 对话发一条 acceptance comment（`make accept GOAL="..."` 生成），至少含：
  `head_sha`、`goal`、`tests`(如有)、`make verify`、`make health`、`TODO=0`、`changed_files`、`rollback`。
- 只写 names-only / counts-only；禁 secrets/endpoints/password（安全硬线，与合并机制无关）。
- PR 标题描述单一 merge intent。

## 7) 自动合并策略（全自动默认）

本仓库为 GitHub **free + private**，无 branch protection / required checks。

- 合并路径：`gh pr create` 后 `gh pr merge <n> --merge --delete-branch`（立即产生 merge commit）。
- `--auto` 变体在 checks pending 时行为随 gh 版本而变，**依赖前重新确认，不要固化**。
- `.github/workflows/gate.yml` 跑 `make verify` + `make health` 作为 **advisory CI**（红信号不阻塞合并，价值是回看时有客观健康记录）。
- **merge 才是 done**：CI 失败或合并停滞时读 failure → 修码 → push → 循环，不停在 green-pending PR。
- 人工暂停：PR 设 draft 或标题加 `[manual-hold]`。

**首次仓库播种例外**：初始化提交允许直推 `main`；此后产品开发走 worktree + PR。

## 8) Hard stops（仍需用户的话）

- 生产部署 / 合入 auto-deploy 分支（本项目暂无；未来 Cloudflare Pages 部署属此类）。
- force-push `main`。
- 提交含 secrets 或 live `.env` 的文件。

## 9) Decision Gate（每次工作流决策）

1. 先用第一性原理重述 goal / non-goal / 约束 / SoT / 验收 / 根因。
2. 机制不可靠时优先绕开或替换，不要叠补丁机制。
3. 同一类事实只能有一个 SoT。
4. 证据必须有明确消费者；无消费者不生产。
5. 默认选满足 acceptance 的最小改动。
6. 引入新机制必须同时说明退出策略、消费者、最小兜底。
7. **可见性问题先三层分流再动 repo**：定义层(repo 是否有定义) → 注册层(宿主机是否安装) → 活跃会话层(当前会话是否加载)。只有定义层缺失才开 repo task；注册/会话层走本机修复或重启，不升级成产品代码改动。
8. env/credential 变更前先按 `docs/runtime/Credentials-Management.md` 分类目标平面，不要把 runtime secrets 复制进仓库。

## 10) 产品域专属约束（与工作流并列，详见 PRD §7）

- 五个 surface 来自**单一 per-stock 引擎**，数字必须互相追溯（数据一致性硬约束）。
- **point-in-time membership 是硬要求**：membership 改写会回溯改写历史，否则 Ocean trail / RS-Ratio 线是虚构的。
- scope filter 全程可见 + 一键清除，单一真源、跨 tab 粘滞，禁隐式 filtered 状态。
- 数千只放 Ocean(explore) 可以；DECISION 必须 bounded。
