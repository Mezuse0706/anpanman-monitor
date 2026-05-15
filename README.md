# Anpanman 稀缺货监控

本地可跑、Railway 可部署的轻量 MVP。

第一目标：

- 打开网页
- 添加关键词
- 手动或定时监控公开页面
- A 级稀缺货推送到飞书
- 点击 Buyee / ZenMarket 辅助购买

## 本地运行

```powershell
Copy-Item .env.example .env
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开：

- http://127.0.0.1:8000
- http://127.0.0.1:8000/docs

## 飞书提醒

在飞书群里添加自定义机器人，复制 Webhook，然后写入 `.env`：

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx
```

网页上点击“测试飞书提醒”，能收到消息就说明配置成功。

## Railway 部署

1. 把本项目上传到 GitHub。
2. Railway 新建项目，选择该 GitHub 仓库。
3. 添加环境变量：

```env
FEISHU_WEBHOOK_URL=你的飞书机器人Webhook
MONITOR_INTERVAL_SECONDS=300
ENABLE_BACKGROUND_MONITOR=true
```

4. Railway 会使用 `railway.json` 启动：

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

说明：默认使用 SQLite，适合第一版验证流程。Railway 免费/临时文件系统可能在重启后丢本地数据库；如果后面要长期保存价格库，再接 Railway PostgreSQL，只需要设置 `DATABASE_URL`。

## 当前实现

- 网页 Dashboard：`/`
- 健康检查：`/health`
- 关键词 API：`/keywords`
- 手动监控：`/monitor/run-once`
- 实时新货：`/items/realtime`
- 稀缺榜：`/items/scarce`
- 利润计算：`/items/{item_id}/profit`

## 合规边界

采集层只请求公开可访问页面或公开搜索入口。

禁止：

- 绕过登录
- 绕过验证码
- 模拟真人点击
- 绕过 robots 或平台限制

