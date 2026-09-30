# 工作续接记录

更新时间：2026-09-30（Asia/Shanghai）

项目目录：

`C:\Users\29755\DoubaoWork\chats\2026-09-27\new-chat\football_ai`

正式网站：

`https://football-intelligence-59lc.onrender.com`

GitHub：

`https://github.com/naohhm137/football-intelligence`

## 当前线上状态

- Render Web Service 已上线，Supabase PostgreSQL 健康检查为 `ok`；
- 用户只需填写主队、客队和带时区的开赛时间；
- API-Football 免费密钥已配置并通过真实赛程查询；
- Ailindo 的 `gpt-5.6-sol` 已配置，流式 JSON 解释已通过真实接口验证；
- 真实比赛 Aurora vs San Antonio Bulo Bulo 已完成三字段烟雾测试；
- 分析、`NO_BET_UNVALIDATED` 安全状态和 Supabase 持久化均已验证；
- 本地 68 项测试和 Python 编译检查全部通过；
- 生产密钥只存放在 Render 环境变量和本机凭据文件中，没有进入 Git 仓库。

## 关键修复

- PostgreSQL 断线自动重连；
- 健康检查释放数据库事务；
- Web Worker 启动时不重复执行 PostgreSQL DDL；
- API-Football 使用供应商支持的 `date` 赛程过滤；
- PostgreSQL 原生 `datetime` 和 JSONB 返回值统一序列化/反序列化；
- Ailindo 按中转站要求使用 SSE 流式响应，支持分段事件和一次格式重试；
- AI 输出限制为单行 ASCII 转义 JSON，避免中转站多行及非 ASCII SSE 兼容问题。

## 关键约束

- 没有真实亚盘时不计算 EV；
- AI 只能解释已保存证据，引用未保存来源时拒绝展示；
- 严格前瞻验证尚未达到 300 场，所有报告保持 `NO_BET_UNVALIDATED`；
- 不宣称模型已经实现稳定盈利或超过 55% 的独立前瞻命中率；
- 每场用户查询过的比赛进入 72h、24h、6h、90m、30m 免费快照计划。

## 复验命令

```powershell
python -m compileall -q app scripts wsgi.py
python -m unittest discover -s tests -v
python -m scripts.smoke_test https://football-intelligence-59lc.onrender.com --home Aurora --away "San Antonio Bulo Bulo" --kickoff 2026-09-30T08:00:00+08:00
```
