# GitHub、Supabase 与 Render 部署

## 需要配置的变量

生产环境只使用以下变量名，值不得写入 Git：

- `DATABASE_URL`：Supabase PostgreSQL 连接串；
- `AILINDO_BASE_URL`：ailindo 的 OpenAI 兼容 API 根地址；
- `AILINDO_API_KEY`：ailindo 密钥；
- `AILINDO_MODEL`：当前密钥对应的准确模型名；
- `API_FOOTBALL_KEY`：API-Football 免费账户密钥；
- `HTTP_TIMEOUT_SECONDS`：可选，默认 12；
- `AI_TIMEOUT_SECONDS`：可选，默认 45。

聊天中曾出现过的 ailindo 密钥应在正式上线前轮换。新密钥只录入 Render 和 GitHub Secrets。

## 1. Supabase

1. 创建免费 Supabase 项目并复制 PostgreSQL 连接串；
2. 使用 SQL Editor 执行 `app/migrations/001_initial.sql`，脚本可重复执行；
3. 用只读查询确认 `analyses`、`odds_snapshots`、`tracked_fixtures` 和 `collection_jobs` 已创建；
4. 将连接串保存为 Render 与 GitHub Actions 的 `DATABASE_URL`，不要写入文件。

如本机已有 `psql`，也可执行：

```powershell
psql "$env:DATABASE_URL" -f app/migrations/001_initial.sql
```

## 2. GitHub

推送仓库后，在仓库 `Settings → Secrets and variables → Actions` 中增加：

- `DATABASE_URL`
- `API_FOOTBALL_KEY`

`CI` 工作流会编译、运行全部测试并执行 Gitleaks。`Collect due match snapshots` 每 15 分钟检查一次已登记比赛；数据库唯一任务锁防止重复快照。

## 3. Render

1. 选择 `New → Blueprint` 并连接 GitHub 仓库；
2. Render 会读取 `render.yaml` 创建 `football-intelligence` 服务；
3. 在服务环境变量中填入本文件列出的五个必需变量；
4. 等待 `/api/health` 返回 `status: ok`；
5. 用真实比赛运行 `scripts/smoke_test.py`，确认分析和持久化均为 `ok`。

Render 免费实例休眠后的首次请求可能较慢。网页会保留三个输入字段，失败后可以直接重试。

## 回滚与恢复

- 应用回滚：在 Render 的 Deploys 页面选择上一个通过健康检查的提交并重新部署；
- 数据恢复：Supabase 是持久数据库，Render 回滚不会覆盖历史分析；
- 采集失败：任务标记为 `failed`，15 分钟后允许重试，成功任务不会重复执行；
- 密钥轮换：先在供应商生成新密钥，再更新 Render 和 GitHub Secrets，验证健康检查后撤销旧密钥；
- 数据库迁移失败：停止部署，保留现有数据库，修复迁移后重新运行；迁移脚本禁止删除表。

## 上线验收

```powershell
python -m scripts.smoke_test https://你的固定网址 --home 主队 --away 客队 --kickoff 2026-10-03T20:00:00+08:00
```

成功输出只包含健康状态、动作状态、持久化状态和耗时，不输出密钥或完整供应商响应。
