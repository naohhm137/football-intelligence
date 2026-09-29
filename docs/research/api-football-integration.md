# API-Football 接入核验

核验日期：2026-09-29

## 已由一手来源确认

- 官方文档入口是 <https://www.api-football.com/documentation-v3>。本次访问遇到官方 Cloudflare 人机验证，因此没有绕过验证，也没有把页面内容当作已读取事实。
- 官方 API 主机 `https://v3.football.api-sports.io` 可达。对 `/status` 和 `/fixtures?date=2026-09-29` 的无密钥请求均返回 HTTP 403 和官方 JSON 错误：缺少应用密钥，且响应维持统一的 `get / parameters / errors / results / paging / response` 外壳。
- 向同一官方 `/status` 端点发送 `x-apisports-key` 测试头后，错误从“缺少应用密钥”变为“无效 API key”。这直接确认了该头名被当前官方端点识别。

## 实现约束

- 客户端只向官方 `v3.football.api-sports.io` 发送 API-Football 密钥，且密钥只放在请求头，绝不进入 URL、缓存键或日志。
- 适配器按官方响应外壳读取 `response`，并把非空 `errors` 当作失败，不把空响应解释成真实“无比赛”。
- 具体数据字段由完整录制夹具锁定；正式密钥配置后还需做一次官方实时契约检查。
- 官方文档被验证页阻挡时不采用绕过手段，符合项目“不绕过验证码/安全验证”的约束。

## 一手来源

1. API-Football 官方文档入口：<https://www.api-football.com/documentation-v3>
2. API-Sports 官方状态端点：<https://v3.football.api-sports.io/status>
3. API-Sports 官方赛程端点：<https://v3.football.api-sports.io/fixtures?date=2026-09-29>
