# 工作续接记录

更新时间：2026-09-29（Asia/Shanghai）

## 从这里继续

项目目录：

`C:\Users\29755\DoubaoWork\chats\2026-09-27\new-chat\football_ai`

当前分支：`main`

最近完成提交：

`c719d8d feat: establish match-night visual system`

该提交已经完成“比赛之夜情报室”的视觉基础、原创球场背景、只含主队/客队/开赛时间的三字段表单、首页路由和前端契约测试。提交前全套 42 项测试通过，且资源警告已清理。

## 当前精确断点

Task 2 已进入 TDD 的红灯阶段。未提交文件：

`tests/test_frontend_api_contract.py`

这两个测试已实际运行并按预期失败，因为以下生产模块尚未创建：

- `app/static/js/api.js`
- `app/static/js/search.js`
- `app/static/js/progress.js`

测试要求 `submitMatch`：

1. 只向 `/api/analyze` POST 三个公开字段；
2. 自动裁剪队名并把本地开赛时间转成带时区的 ISO 时间；
3. 即使调用方混入赔率字段也绝不发送；
4. 后端返回歧义比赛时，保留错误码、状态码和候选比赛。

继续时先实现最小的 `api.js` 让当前两个测试变绿，再写下一条失败测试覆盖取消旧请求和禁止重复提交，然后实现 `search.js` 与 `progress.js`。页面扫描线只能在真实请求期间运行，响应完成后必须停止。

## 后续计划顺序

1. 完成 Task 2 并提交：`feat: add automatic match research flow`
2. 完成结果叙事、真实赔率快照图和证据链接安全属性；提交：`feat: present evidence-backed match intelligence`
3. 完成移动端、无障碍、离线/超时/部分失败状态和浏览器截图检查；提交：`feat: harden responsive match-night interface`
4. 执行 GitHub + Render + Supabase 部署计划。登录和生产密钥录入需要用户在浏览器中接管。

实现计划：

`C:\Users\29755\DoubaoWork\chats\2026-09-27\new-chat\docs\superpowers\plans\2026-09-29-match-night-interface.md`

部署计划：

`C:\Users\29755\DoubaoWork\chats\2026-09-27\new-chat\docs\superpowers\plans\2026-09-29-github-render-supabase-deployment.md`

## 不可破坏的约束

- 用户只填写主队、客队、开赛时间；赔率和新闻等由系统自动查找。
- AI 只能引用已抓取并保存的证据，不得编造。
- 没有真实亚盘赔率时不得计算或展示伪造 EV。
- 模型尚未通过严格前瞻验证，始终保持 `NO_BET_UNVALIDATED`。
- ailindo 配置只从 `AILINDO_BASE_URL`、`AILINDO_API_KEY`、`AILINDO_MODEL` 读取。
- 聊天中出现过的密钥不得写入代码、测试、日志、Git 或交接文档，上线后应轮换。
- 免费优先；目标是固定 Render 网站和 Supabase 生产数据库。

## 明天的启动检查

```powershell
Set-Location 'C:\Users\29755\DoubaoWork\chats\2026-09-27\new-chat\football_ai'
git status --short
git log --oneline -3
& 'C:\Users\29755\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_frontend_api_contract -v
```

最后一条目前应失败；这是刻意保留的 TDD 红灯，不是仓库损坏。
