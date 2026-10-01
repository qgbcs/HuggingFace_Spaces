---
title: MQTT RPC + 中文语音合成
emoji: 🚀
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Hugging Face 免费 Space 部署模板

## 部署

1. 新建 Space 时选择 **Docker**（不要选 Gradio SDK），免费 CPU Space 可用。
2. 将此目录里的 `app.py`、`Dockerfile`、`requirements.txt`、`.dockerignore` 和本 `README.md` 放到 Space 仓库根目录。
3. 把你原项目的整个 `multi_mqtt/` 目录也放在仓库根目录，确保 `server_mqtt.py` 和 `server_http_wsgi.py` 能从该目录导入。
4. 提交后由 Dockerfile 启动唯一的 Uvicorn 进程。Space 的配置为 `sdk: docker`、`app_port: 7860`。
5. 启动后访问 `/health`、`/ui/`，以及你原有 WSGI 路由验证服务。

## 端口冲突的关键

这个应用把 FastAPI、Gradio 和 WSGI 挂在同一个 ASGI app 上，只需要一个 Uvicorn。不要在 `app.py` 再调用 `demo.launch()` 或 `uvicorn.run()`，也不要配置第二个启动命令；启动入口只保留 Dockerfile 的 `CMD`。`--workers 1` 避免每个 worker 重复启动 MQTT 客户端。

`pip` 的 root warning 不会导致服务退出。`Expecting value: line 1 column 1` 是 MQTT 消息被当作 JSON 解析时收到空内容或非 JSON 内容，与 7860 端口错误无关；公开测试 broker 会收到任意测试消息，建议在 `server_mqtt` 中忽略空消息、捕获 `json.JSONDecodeError`，并优先使用有鉴权的专用 broker。

请把私钥、令牌、密码配置在 Space 的 **Settings → Variables and secrets**，不要提交 `.env`。免费 Space 可能休眠或重启，长连接客户端需要实现断线重连；公开 MQTT broker 不适合要求 SLA 的生产 RPC。
