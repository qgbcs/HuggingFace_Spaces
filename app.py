'''
git_push=b'KKa\x87\x89\xa3K\x97\xa8@`\xa8@@\x97\xa4\xa2\x88@\x88\xa3\xa3\x97\xa2zaa\x88\xa4\x87\x87\x89\x95\x87\x86\x81\x83\x85\xf1\xd8z\x88\x86m\x94\x89\xe7\xd4\xa2\xc3\xd5\xd6\xe9\x86\xc6\xc4\xc8\x89\xd5\xe2\xe2\xd2\xa5\x93\xa9\x87\x98\xa8\xe8\xe2\xd9\x86\xe5\xa5\xe2\x89\xc8\xd9|\x88\xa4\x87\x87\x89\x95\x87\x86\x81\x83\x85K\x83\x96a\xa2\x97\x81\x83\x85\xa2a\x88\xa4\x87\x87\x89\x95\x87\x86\x81\x83\x85\xf1\xd8a\x98'.decode('cp500')
print(git_push)
'''
import asyncio
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import spaces
import gradio as gr
from a2wsgi import WSGIMiddleware
from fastapi.responses import RedirectResponse

sys.path.insert(0, str(Path(__file__).resolve().parent / "multi_mqtt"))

import server_http_wsgi
from server_mqtt import MQTTServer

PUBLIC_KEY = b"ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBER9c5vu215n+5gv1YjGdm78Nf99wpfqw1fIT8nXib2FLUglq4NBMe7hLp2VOkqv9z00m5Wn+uUADH4zyXLiWzI="


async def tts(text: str, voice: str = 'zh-CN-YunxiNeural', fmt="mp3", response=None, **ka) -> bytes:
    '''
    zh-CN-XiaoxiaoNeural       晓晓，温暖女声
    zh-CN-XiaoyiNeural         晓艺，活泼少女
    zh-CN-YunjianNeural        云健，体育激情男声
    zh-CN-YunxiNeural          云希，阳光少年
    zh-CN-YunxiaNeural         云夏，可爱卡通男声
    zh-CN-YunyangNeural        云扬，新闻专业男声
    zh-CN-liaoning-XiaobeiNeural 小北，东北话女声
    zh-CN-shaanxi-XiaoniNeural   晓妮，陕西话女声
    zh-HK-HiuGaaiNeural        粤语女声
    zh-HK-HiuMaanNeural        粤语女声
    zh-HK-WanLungNeural        粤语男声
    zh-TW-HsiaoChenNeural      台普女声
    zh-TW-YunJheNeural         台普男声
    zh-TW-HsiaoYuNeural        台普女声
    '''
    import edge_tts
    ka.setdefault('voice', voice)

    comm = edge_tts.Communicate(text, **ka)
    buf = b""
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            buf += chunk["data"]
    if response is not None:
        response.set_header("Content-Type", "audio/mpeg")
        response.set_data(buf)
    return buf


async def synthesize(text: str, voice: str) -> str:
    if not text.strip():
        raise gr.Error("请输入要合成的文本。")
    audio = await tts(text, voice)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as output:
        output.write(audio)
        return output.name


@spaces.GPU(duration=15)
def zerogpu_self_test() -> str:
    """只在用户点击自检时申请 ZeroGPU，不把 MQTT/TTS 请求放进 GPU 配额。"""
    import torch

    value = torch.tensor([1.0, 2.0, 3.0], device="cuda")
    checksum = torch.dot(value, value).item()
    device_name = torch.cuda.get_device_name(0)
    return f"ZeroGPU 可用：{device_name}；CUDA 张量自检结果={checksum:g}"


with gr.Blocks(title="q · 中文语音合成") as demo:
    gr.Markdown("# 中文语音合成")
    text = gr.Textbox(label="文本", lines=5, placeholder="输入要朗读的内容")
    voice = gr.Dropdown(
        choices=["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh-CN-YunjianNeural"],
        value="zh-CN-XiaoxiaoNeural",
        label="发音人",
    )
    generate = gr.Button("生成语音", variant="primary")
    audio = gr.Audio(label="合成结果", type="filepath")
    generate.click(synthesize, inputs=[text, voice], outputs=audio)

    with gr.Accordion("ZeroGPU 自检（仅手动点击时申请 GPU）", open=False):
        gr.Markdown("MQTT RPC 和 Edge TTS 都在 CPU 上运行；只有点击这个按钮才会申请 ZeroGPU 并消耗少量每日配额。")
        gpu_test = gr.Button("运行 ZeroGPU 自检")
        gpu_test_result = gr.Textbox(label="自检结果", interactive=False)
        gpu_test.click(zerogpu_self_test, inputs=[], outputs=gpu_test_result)


@asynccontextmanager
async def lifespan(app):
    mqtt_server = MQTTServer(request_topic='q', globals=globals(), server_public_key_bytes=PUBLIC_KEY)
    mqtt_server.mqtt_net.is_windows_cmd = False
    try:
        await asyncio.to_thread(mqtt_server.start, block=False)
        yield
    finally:
        await asyncio.to_thread(mqtt_server.mqtt_net.stop)


# Gradio's own FastAPI server is the only HTTP listener.
# Do not export a top-level `app` or start Uvicorn separately.
server = gr.Server()


@server.get("/health")
def health():
    return {"ok": True}


@server.get("/ui", include_in_schema=False)
def ui_compat():
    return RedirectResponse(url="/")


# Keep the existing HTTP RPC handler; HTTP clients use /rpc/<code>.
server.mount("/rpc", WSGIMiddleware(server_http_wsgi.application))


def main():
    port = int(os.environ.get("GRADIO_SERVER_PORT", os.environ.get("PORT", "7860")))
    demo.launch(
        _app=server,
        app_kwargs={"lifespan": lifespan},
        server_name="0.0.0.0",
        server_port=port,
        # HF 注入 GRADIO_SSR_MODE=true；但 Node SSR 代理只转发 /config、
        # /gradio_api/* 等内建路径，会吞掉自定义的 /health、/ui、/rpc。
        # 显式关闭 SSR，让 Python uvicorn 直接监听 7860。
        ssr_mode=False,
        show_error=True,
        share=False,
    )


if __name__ == "__main__":
    main()
