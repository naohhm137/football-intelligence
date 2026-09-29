# 免费实时来源核验

核验日期：2026-09-29

## Open-Meteo

官方文档 <https://open-meteo.com/en/docs> 可直接访问。文档当前明确列出本项目使用的逐小时字段：`temperature_2m`、`relative_humidity_2m`、`precipitation`、`wind_speed_10m`，并支持 `timezone` 参数。因此天气适配器只请求这些字段，并把目标时刻固定到比赛开球时间附近的小时。

项目只调用官方公开预报端点 <https://api.open-meteo.com/v1/forecast>，不使用密钥、不绕过登录或验证。无法确认球场坐标时返回缺失，不用球队所在地假冒球场天气。

## GDELT

GDELT 官方发布页 <https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/> 可直接访问，说明 DOC 2.0 API 的文章列表模式、最大记录数和排序能力。本项目使用官方端点 <https://api.gdeltproject.org/api/v2/doc/doc>，请求 `ArtList` JSON，并只保留同时具有 URL、标题与可解析发布时间的文章。

核验时官方 GDELT API 对一次无密钥测试请求返回 HTTP 429。因此实现把限流当作来源失败并降级，不重试轰炸，也不把空结果捏造成新闻事实；缓存窗口固定为30分钟。

## API-Football 上下文与赔率

API-Football 官方接口的来源与认证核验见 `api-football-integration.md`。球队上下文按三小时缓存，新闻按30分钟缓存，天气按一小时缓存。赔率在开赛前90分钟外缓存15分钟，进入90分钟后缓存5分钟。实时亚盘为空时明确返回 `ASIAN_ODDS_NOT_AVAILABLE`，不从1X2赔率推造盘口。

## 一手来源

1. Open-Meteo 官方文档：<https://open-meteo.com/en/docs>
2. Open-Meteo 官方预报 API：<https://api.open-meteo.com/v1/forecast>
3. GDELT 官方 DOC 2.0 发布说明：<https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/>
4. GDELT 官方 DOC API：<https://api.gdeltproject.org/api/v2/doc/doc>
