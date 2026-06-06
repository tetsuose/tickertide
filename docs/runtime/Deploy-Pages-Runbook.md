# Deploy Runbook — D.3 Cloudflare Pages 私有上线

> 何时读：首次 go-live、配置/排查 nightly 自动部署、设置私有访问、回滚。
> 范围：D 轨终点。把 D.2 nightly 产出的静态站点（`web/dist`，数据 bundled 自 `web/public/data`）发布到 **Cloudflare Pages**，并用 **Cloudflare Access** 限私有访问（个人自用、不对外分发数据 —— SCOPE / PRD §6.2 / NFR-7 硬线）。
> 配套：`docs/runtime/Credentials-Management.md`（凭证硬线）· `.github/workflows/nightly.yml`（部署接线）· `web/wrangler.jsonc`（Pages 配置）。

## 0. 第一性原理

这是 **EOD 静态前端**：`make web-build` 任何时候能出静态产物，但数据一过夜就死。所以"部署"= 把 nightly **真实数据 + 静态壳**天天推上线。部署只在 nightly pipeline + C9 gate + web build **全绿之后**发生（失败步骤会先中断 job），陈旧/失败不发布（陈旧可见由 D.4 新鲜度 badge 兜底）。

**项目名**：默认 `tickertide`（→ `tickertide.pages.dev`）。改名只需同步三处：`web/wrangler.jsonc` 的 `name`、本 runbook、（Pages 项目创建命令）。`nightly.yml` 的 deploy 从 `wrangler.jsonc` 读名，无需改。

## 1. 前置

- 一个 Cloudflare 账号（免费版即可：Pages + Access ≤50 用户均含免费额度）。
- 本机 `npx wrangler`（4.x，已可用，无需全局安装）。
- `gh` CLI 已登录本仓库（设 Actions secret 用）。

## 2. 凭证（两个独立需求，secrets 绝不入库）

> 硬线（CLAUDE.md §8 / Credentials-Management.md）：API token **绝不**写进 `wrangler.jsonc` / repo / commit / PR / 日志 / acceptance。只存在两处合法位置：本地 `wrangler login` OAuth 凭证、GitHub Actions secret。

### 2A. 首次本地 go-live —— `wrangler login`（推荐，最安全）

```bash
npx wrangler login      # 浏览器 OAuth，凭证存本地 ~/Library/Preferences/.wrangler，不入对话/仓库
npx wrangler whoami     # 验证：显示 email + account id
```

### 2B. CI 自动部署 —— GitHub Actions secret（auto-deploy 必需）

GitHub Actions **不能**用 OAuth，必须用 API token。需要两个 secret：

| secret 名 | 取值 | 来源 |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | 一个 token | dash.cloudflare.com/profile/api-tokens → Create Token → 模板 **"Edit Cloudflare Workers"**（覆盖 Pages） |
| `CLOUDFLARE_ACCOUNT_ID` | 账号 ID | `npx wrangler whoami` 输出，或 dashboard 右栏 |

设置（**在终端交互粘贴，不要把值打进命令行/历史**）：

```bash
gh secret set CLOUDFLARE_API_TOKEN     # 回车后粘贴 token 值，回车
gh secret set CLOUDFLARE_ACCOUNT_ID    # 回车后粘贴 account id，回车
gh secret list                          # 确认两个 secret 在列（只显示名，不显示值）
```

> token 最小权限：账号级 **Workers Scripts:Edit**（"Edit Cloudflare Workers" 模板已含，Pages 直传走此权限）。若另用自定义 token，确保含 Account › Cloudflare Pages › Edit。

## 3. 创建 Pages 项目（一次性）

```bash
cd web
npx wrangler pages project create tickertide --production-branch=main
```

或 dashboard：Workers & Pages → Create → Pages → **Direct Upload**（不连 Git，本仓库走 wrangler 直传）→ 项目名 `tickertide` → 生产分支 `main`。

## 4. 首次 go-live（手动验证）

```bash
# 仓库根目录：产数据 + 构建静态壳（data bundled 进 dist）
make web-build
# 直传到 Pages 生产（从 web/ 读 wrangler.jsonc：name + pages_build_output_dir=dist）
cd web && npx wrangler pages deploy --branch=main
```

部署完打印 `https://tickertide.pages.dev`（及一次性 deployment 子域）。此时站点**公开可访问** —— 立刻做第 5 步上私有锁，再对外暴露任何 URL。

## 5. 私有访问 —— Cloudflare Access（Zero Trust）

> wrangler **不管** Access policy；Access 是 Zero Trust 的 dashboard/API 能力。个人自用最简：self-hosted application + email 白名单 + One-time PIN（邮箱 OTP，无需接 IdP）。

dashboard 步骤：

1. Cloudflare dashboard → **Zero Trust** → Access → **Applications** → Add an application → **Self-hosted**。
2. Application domain：
   - `tickertide.pages.dev`（生产）
   - 再加一条 `*.tickertide.pages.dev`（覆盖每次部署的一次性预览子域，否则可绕过锁）。
3. Identity providers：勾 **One-time PIN**（邮箱验证码，零配置）。
4. Policies → Add a policy：
   - Action = **Allow**
   - Include = **Emails** → 填允许的邮箱（本人）。
   - 其余身份默认拒绝（Access 默认 deny 未匹配者）。
5. Save。之后访问站点会先跳 Access 登录页，仅白名单邮箱收 OTP 后可进 → **私有**。

> 注：免费 Zero Trust 含 Access ≤50 用户，个人足够。Access 配置不入本仓库（dashboard 侧），与 secrets 同理。

## 6. 启用 CI 自动部署

完成第 2B（设两个 gh secret）后，每次 nightly **全绿**运行（`schedule` 或 `workflow_dispatch`）会自动 `wrangler pages deploy` 到生产。`nightly.yml` 的 deploy 步骤在 secret 未设时**自动跳过**（gate 步骤只 echo 布尔、不打印值），所以脚手架合并后、设 secret 前不会报错。

手动触发一次验证：

```bash
gh workflow run nightly.yml -f limit=120     # 小规模冒烟
gh run watch                                  # 跟踪；看 deploy 步骤是否执行/跳过
```

## 7. AC-D 验收清单（D 轨完成）

- [ ] 站点**私有**可访问：白名单邮箱 OTP 后能进；其它邮箱被 Access 挡。
- [ ] Vite `base='./'` 路径正常：JS/CSS 资源在 `tickertide.pages.dev` 下无 404。
- [ ] 数据 fetch 正常：`/data/manifest.json`、`board.json`、`ocean.json`、`rotation.json` 均 200，Discovery/Ocean/Rotation 渲染。
- [ ] 最新 `as_of` 可见：D.4 新鲜度 badge 显示当晚数据龄。
- [ ] nightly 刷新可见：一次 nightly 后 `as_of` 前进。
- [ ] 无 secrets 入库：token 仅在 gh secret + 本地 OAuth；`git log -p` / PR 无 token；`.dev.vars`/`.wrangler/` 已 gitignore。
- [ ] 陈旧/失败可见：pipeline 失败则 job 中断、不发布（D.4 兜底陈旧可见）。

## 8. 回滚

```bash
cd web
npx wrangler pages deployment list --project-name=tickertide   # 看历史部署
# dashboard：项目 → Deployments → 选上一个 good 部署 → Rollback
```

最快兜底：用上一次 good 的 `web/dist` 重跑第 4 步直传覆盖。

## 9. 排查

| 症状 | 因 | 解 |
|---|---|---|
| `Not logged in` / 部署 401 | 无凭证/token 失效 | 本地 `wrangler login`；CI 查 `CLOUDFLARE_API_TOKEN` secret |
| `Missing account` / 选错账号 | 未给 account id | CI 设 `CLOUDFLARE_ACCOUNT_ID` secret；本地 `wrangler whoami` 核对 |
| 资源 404（白屏） | 部署目录错 / base 不对 | 确认直传的是 `web/dist`（含 `index.html` + `data/`）；`vite.config.ts` base 仍 `'./'` |
| 数据 404 | export 没跑 | `make export` 须在 `npm run build` 前（nightly 已排序；本地走 `make web-build`） |
| Access 不生效 / 能绕过 | 漏配预览子域 | Access application 加 `*.tickertide.pages.dev` |
| 部署陈旧数据 | 不会：deploy 在全绿后 | pipeline/C9 失败会中断 job；陈旧另有 D.4 badge |
| sandbox 出站被 block | 本地 wrangler 部署需联网 | 本 harness 下 `wrangler deploy` 走 `dangerouslyDisableSandbox=true`；CI 无此限 |
