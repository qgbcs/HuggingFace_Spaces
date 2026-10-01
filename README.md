---
title: MQTT RPC + 中文语音合成
emoji: 🚀
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: "6.28.0"
python_version: "3.12.12"
app_file: app.py
pinned: false
---

# MQTT RPC + 中文语音合成

## 配置

本 Space 使用 Gradio SDK，README 中保留上方配置。ZeroGPU 只支持 Gradio SDK。请在 **Settings → Hardware** 检查当前硬件，不要为了改 SDK 同时切换硬件。

如果 Space 提示没有 PRO 就不能切换到 cpu-basic，不要继续尝试该降级；要停止当前付费硬件费用，请在 Space 页面点击 **Pause**。`sdk: gradio` 只修复 ZeroGPU 与 SDK 的配置匹配，不会改变硬件计费类型。只有账户和 Space 设置实际提供 ZeroGPU 时才选择 ZeroGPU；本服务本身不使用 GPU。

## 部署文件

将以下文件放在 Space 仓库根目录：

- `README.md`
- `app.py`
- `requirements.txt`
- `.gitignore`
- 现有完整的 `multi_mqtt/` 目录

如果仓库根目录存在 `Dockerfile`，在使用 Gradio SDK 时删除它，避免保留另一套启动配置。不要提交 `.env`、私钥或令牌；将需要的秘密放进 **Settings → Variables and secrets**。

## 启动与端口

`app.py` 由唯一的 `demo.launch()` 启动。它不调用 `uvicorn.run()`，不导出顶层 `app`，也不另起 Gradio 或 Uvicorn 进程。不要在 Space 的启动配置、shell 命令或 Dockerfile 中再启动第二个服务器。

TTS 界面在 Space 首页 `/`，健康检查为 `/health`。现有 WSGI HTTP RPC 通过 `/rpc` 前缀提供：把客户端 HTTP base URL 设置为 `https://huggingface1Q-q.hf.space/rpc`（使用你的实际 Space 域名），原有路径参数继续追加在 `/rpc/` 后。MQTT RPC topic `q` 不变。

## 日志

`Expecting value: line 1 column 1` 是 MQTT 公共 broker 收到空或非 JSON 消息后被解析的独立问题，不会造成 7860 端口冲突。若需要消除这条噪声，可将 `mqtt_non_json.patch` 放到仓库根目录，在 Space 仓库根目录执行 `git apply mqtt_non_json.patch`，再提交修改。

免费/共享硬件可能休眠、重启或有额度限制；这类 Space 不保证常驻 MQTT 长连接或生产 RPC SLA。