# Agent State — 三层状态协议入口

> 这是**协议/索引**文件，不是日志。保持简短：用 live readback 命令读真值，不要在此复制会过期的状态。
> 渐进式读取：先读本文，再按任务只打开匹配的那一层。

TickerTide 的状态分三层。每层给出**怎么读真值**，而不是把状态抄在这里。

## L1 — Git 状态（分支 / commit / PR / worktree / merge 边界）

```bash
git status --short && git rev-parse --abbrev-ref HEAD     # 当前分支与脏度
make task-status                                          # worktree 状态、ahead/behind
make route                                                # 本次改动的 lane + 分支建议
gh pr list --state open                                   # 在途 PR（需 gh）
```

- merge 边界 = `branch/PR`，一个 worktree 一个 merge intent（见 `docs/workflow/WORKFLOW.md` §2）。
- 收口：`make task-close` → `open_pr` / `wait_or_merge` / `drop`。

## L2 — 运行时 / 环境状态（服务 / env / secrets / 部署）

TickerTide 是**零常驻后端**：没有长跑 server 或托管 DB。运行时面由三块构成：

| 组件 | 真值在哪 | 怎么读 |
|---|---|---|
| 夜间管道 | GitHub Actions cron（post-US-close） | `gh run list`（实现后）；本地 `make pipeline` |
| 静态站点 | Cloudflare Pages 部署 revision | Pages dashboard / 部署日志（实现后） |
| 本地计算 | DuckDB 单文件（`data/`，gitignored） | `make compute` 产物；不入 git |
| 数据源密钥 | `.env`（gitignored，可选 Tiingo） | 名称登记见下 |

- env/secrets **只登记名称，不写值**：`docs/runtime/Env-Registry.md`（gitignored；模板 `Env-Registry.example.md`）。
- 平面模型与轮换流程：`docs/runtime/Credentials-Management.md`。
- 当前阶段无活跃运行时（pre-M0）；本层在 M0 数据管道落地后填充读法。

## L3 — 任务 / agent 状态（目标 / 约束 / stop 条件 / 验收）

| 维度 | 真值在哪 |
|---|---|
| 产品目标与里程碑 | `docs/PRD.md` §13（M0–M6）、§16（已定死清单） |
| 不可妥协约束 | `docs/PRD.md` §7、`docs/workflow/WORKFLOW.md` §10 |
| 本次任务契约 | 当前 PR/Issue 描述（Objective/Non-goals/Scope/Acceptance/Rollback/Stop） |
| 验收 SoT | PR acceptance comment + gate 输出（`make accept` 生成） |
| 文件级合同 | `docs/runtime/File-Contracts.json` |

- 权威顺序：`User > PR契约 > PRD > File-Contracts > .index/*`（见 WORKFLOW §1）。
- 任何会过期的事实，行动或宣称前从 live 系统重新核验。
