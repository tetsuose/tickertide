# Deploy Runbook — D.3 Cloudflare Pages 私有上线

> 何时读：首次 go-live、配置/排查 nightly 自动部署、设置私有访问、回滚。
> 范围：D 轨终点。把 D.2 nightly 产出的静态站点（`web/dist`，数据 bundled 自 `web/public/data`）发布到 **Cloudflare Pages**，并用 **Cloudflare Access** 限私有访问；数据源条款复核按 PRD §6.2 / NFR-7 处理。
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

> wrangler **不管** Access policy；Access 是 Zero Trust 的 dashboard/API 能力。个人自用最简：self-hosted application + email 白名单 + One-time PIN（邮箱 OTP）。⚠️ One-time PIN **本身就是一个 login method/IdP，必须显式启用**——纯 API 启用 Zero Trust org 不会自动开任何 login method，漏掉则登录页报「no login methods available」。

dashboard 步骤：

1. Cloudflare dashboard → **Zero Trust** → Access → **Applications** → Add an application → **Self-hosted**。
2. Application domain：
   - `tickertide.pages.dev`（生产）
   - 再加一条 `*.tickertide.pages.dev`（覆盖每次部署的一次性预览子域，否则可绕过锁）。
3. Identity providers：启用 **One-time PIN**（邮箱验证码）。**必须至少启用一个 login method**，否则登录页报「no login methods available」。dashboard 的 Enable Access 通常会引导建 OTP；纯 API 启用 ZT 则需单独建（见第 10 节）。
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
| 登录页 `no login methods available` | ZT org 无 login method（API 启用 ZT 不自动建 IdP） | 建 One-time PIN IdP：`POST accounts/{id}/access/identity_providers {name,"type":"onetimepin","config":{}}`（或 dashboard Zero Trust → Settings → Authentication 加 One-time PIN）；app `allowed_idps` 留空=允许全部 IdP |
| sandbox 出站被 block | 本地 wrangler 部署需联网 | 本 harness 下 `wrangler deploy` 走 `dangerouslyDisableSandbox=true`；CI 无此限 |

## 10. 已执行的 go-live 记录（2026-06-10，DONE）

首次上线**没有**走第 2~5 节的「dashboard 手建 token / wrangler login」路径，而是用 **AWS SSM 里的 token-minting seed 凭证全自动完成**（密钥已迁 SSM）。复现/DR 按此：

**前提**：`aws sso login --profile codex-admin`（acct 504508176569、ap-northeast-1、SSO Identity Center）。CF 资源在 SSM `ap-northeast-1`。

1. **凭证（mint 而非手建）**：SSM `/agentops/global/cloudflare/agent-seed-token` 是 token-minting 凭证（有 `User>API Tokens` 权限）。用它经 CF API `POST /user/tokens` mint 一个**最小权限** token（permission group `Pages Write` `8d28297797f24fb8a0c332fe0866ec89`，scoped 到账号），存进 SSM `/cyberbridge/prod/cloudflare/tickertide-pages-token`（SecureString）。**全程不打印 token 值**（临时文件 600 + 用后删）。account-id 取 SSM `/cyberbridge/prod/discovery/cloudflare/account-id`（CF 账号 = cyberbri）。
2. **gh secret**：`CLOUDFLARE_API_TOKEN`（= 上面 minted token）/`CLOUDFLARE_ACCOUNT_ID` 经 `printf %s | gh secret set`（stdin，不入 argv）。
3. **Pages 项目**：`wrangler pages project create tickertide --production-branch=main`。
4. **私有锁（Cloudflare Access，API 全自动）**：账号原本未启用 Zero Trust → 用 seed token mint 一个 Access-setup token（`Apps and Policies Write` + `Organizations/IdP/Groups Write`）→ `POST access/organizations` 启用 ZT（team **`cyberbrid.cloudflareaccess.com`**）→ **`POST access/identity_providers` 建 One-time PIN（`type=onetimepin`）—— ⚠️ 必需：ZT org 创建不会自动开任何 login method，漏这步登录页报「no login methods available」** → 建 self-hosted app（`tickertide.pages.dev` + `*.tickertide.pages.dev`；`allowed_idps` 留空 = 允许全部 IdP，自动含 OTP）→ allow policy（email `sejonep@gmail.com`）→ 回读验证 → **撤销 Access-setup token**（一次性、最小留存）。脚本范式见 session 记录。
   - 实际踩坑：首版自动化漏了建 OTP IdP，第一次登录报「no login methods available」；补 `POST access/identity_providers {type:onetimepin}`（IdP id `74514fc3-b182-47b8-834c-69d3ba3f1bd8`）后解决。
5. **首次部署**：`gh workflow run nightly.yml -f limit=500`（真实数据，走 nightly 的 deploy step）。**注意**：mid-week 跑曾因 rotation `as_of_date` 取周线 Friday 标签 → C9 GATE_FAIL（已修，PR #42：as_of 改用 `max(derived_daily.date)`）。
6. **验证（AC-D 全过）**：`curl -I tickertide.pages.dev/` 与 `/data/manifest.json` 均 **302 → cyberbrid.cloudflareaccess.com**（未登录被挡、数据不公开）；production deployment = main `5fce5e8`；deploy 日志 token 显示 `***`（无泄露）；deploy 仅在 pipeline+C9+build 全绿后跑（前一 run C9 失败→deploy 被挡，验证「陈旧不发布」）。
7. **最后人工 check（用户）**：浏览器开 https://tickertide.pages.dev → OTP 登录 `sejonep@gmail.com` → 确认 Discovery/Ocean/Rotation 渲染 + D.4 新鲜度 badge 显当日 as_of。

> 轮换：minted Pages token 无 expiry；轮换 = 重跑第 1~2 步覆盖 SSM + gh secret（Overwrite=True）。Access 改邮箱 = ZT dashboard 或重跑第 4 步 policy。
