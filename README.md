---
title: MQTT RPC + 中文语音合成
emoji: 🚀
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: "6.28.0"
python_version: "3.12"
app_file: app.py
pinned: false
---

# Hugging Face Spaces：MQTT RPC + 中文语音合成

## Space 配置

本仓库使用 **Gradio SDK**。ZeroGPU 目前仅支持 Gradio SDK；请在 Space 的 **Settings → Hardware** 选择 ZeroGPU。README 元数据中不要写 `sdk: docker` 或 `app_port`，也不要保留 Dockerfile 启动配置。

本服务的 MQTT RPC 和 Edge TTS 不使用 GPU。若不需要 GPU 功能，免费 CPU Basic 更合适；选 ZeroGPU 不会加速 MQTT 或 Edge TTS，也不需要 `@spaces.GPU`。

## 文件

保留你的 `multi_mqtt/` 目录以及其中的 RPC 实现。Space 仓库根目录至少应包含：

- `README.md`（本文件及上述 YAML）
- `app.py`
- `requirements.txt`
- `multi_mqtt/server_http_wsgi.py`
- `multi_mqtt/server_mqtt.py`
- `multi_mqtt/server_http.py`
- `multi_mqtt/multi_mqtt.py`
- 这些模块导入的其他 `multi_mqtt/` 文件

不要将 `.env`、私钥、访问令牌或密码提交到 Git。通过 **Settings → Variables and secrets** 注入环境变量。

## 单进程启动

`app.py` 将 FastAPI、Gradio 和 WSGI RPC 挂载到同一个 ASGI 应用，并由文件末尾唯一的 Uvicorn 进程监听 Space 端口。不要额外运行 `demo.launch()`、第二条 `uvicorn` 命令，或 Docker `CMD`；否则可能再次遇到 `7860 address already in use`。

## 路由检查

- `/health`：FastAPI 健康检查。
- `/ui/`：Gradio 中文语音合成界面。
- `/` 及其他原有 RPC 路由：转发给 `server_http_wsgi.application`。

启动后先检查 `/health`、`/ui/`，再用原有客户端验证 RPC 请求。

## 日志说明

- `ZeroGPU is only available on Gradio SDK`：检查 README YAML 的 `sdk: gradio`，并在 Settings 中选择 ZeroGPU。不要将 SDK 设为 Docker。
- `address already in use`：检查仓库中是否还有第二个启动器或旧 Docker 配置；只保留 `app.py` 中的单个 Uvicorn。
- `pip running as root`：这是安装警告，不是启动失败原因。
- `Expecting value: line 1 column 1`：通常是 MQTT 收到空载荷或非 JSON 消息后仍被 JSON 解码；它和 HTTP 端口错误无关。公共测试 broker 会接收任意消息，应在 `server_mqtt` 消息处理位置忽略空消息并捕获 `json.JSONDecodeError`，生产用途优先使用有鉴权的专用 broker。

免费 Space 可能休眠或重启，不能保证 MQTT 长连接及 RPC SLA；客户端应实现断线重连。