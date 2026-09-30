# Football Intelligence

输入主队、客队和开赛时间，系统自动核验赛程、近期状态、伤停、天气、新闻和可取得的亚盘快照，再输出带来源的赛前研究报告。

## 当前状态

- 网页只要求三个字段，不要求用户填写赔率；
- 量化层支持 1X2 研究概率、亚盘五状态概率和精确四分盘结算；
- AI 只能解释已保存的证据，引用未保存来源时会拒绝展示；
- 缺少真实亚盘时不计算 EV；
- 严格前瞻验证尚未达到 300 场，所有报告保持 `NO_BET_UNVALIDATED`；
- 每场用户查询过的比赛会进入 72h、24h、6h、90m、30m 免费快照计划。

## 本地运行

安装依赖：

```powershell
python -m pip install -r requirements-dev.txt
```

复制 `.env.example` 中的变量名到本机环境变量，然后启动：

```powershell
python -m waitress --listen=127.0.0.1:5080 wsgi:app
```

打开 `http://127.0.0.1:5080/`。

## 验证

```powershell
python -m compileall -q app scripts wsgi.py
python -m unittest discover -s tests -v
python -m scripts.smoke_test http://127.0.0.1:5080 --home Arsenal --away Chelsea --kickoff 2026-10-03T20:00:00+08:00
```

部署步骤、数据库迁移和恢复方法见 [DEPLOYMENT.md](DEPLOYMENT.md)。
