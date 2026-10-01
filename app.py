'''

'''
import asyncio
import os
import sys
import tempfile
from pathlib import Path

import gradio as gr
import uvicorn
from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

sys.path.insert(0, str(Path(__file__).resolve().parent / "multi_mqtt"))

import server_http_wsgi
from server_http import start_rpc_server
from server_mqtt import MQTTServer


PUBLIC_KEY = b"ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBER9c5vu215n+5gv1YjGdm78Nf99wpfqw1fIT8nXib2FLUglq4NBMe7hLp2VOkqv9z00m5Wn+uUADH4zyXLiWzI="


async def tts(text: str, voice: str = "zh-CN-XiaoxiaoNeural", fmt: str = "mp3") -> bytes:
    import edge_tts

    buf = b""
    comm = edge_tts.Communicate(text, voice=voice)
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            buf += chunk["data"]
    return buf


async def synthesize(text: str, voice: str) -> str:
    if not text.strip():
        raise gr.Error("请输入要合成的文本。")
    audio = await tts(text, voice)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as output:
        output.write(audio)
        return output.name


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


port = int(os.environ.get("PORT", "7860"))
start_rpc_server(port=port, ip="0.0.0.0", key="", globals=globals(), locals=globals(), listen=False)
api = FastAPI()


@api.get("/health")
def health():
    return {"ok": True}


api = gr.mount_gradio_app(api, demo, path="/ui")
api.add_route("/ui", lambda request: RedirectResponse(url="/ui/"), methods=["GET", "HEAD"], include_in_schema=False)
api.mount("/", WSGIMiddleware(server_http_wsgi.application))
app = api


def main():
    mqtt_server = MQTTServer(request_topic='q',globals=globals(),server_public_key_bytes=PUBLIC_KEY)
    mqtt_server.mqtt_net.is_windows_cmd = False
    mqtt_server.start(block=False)
    try:
        uvicorn.run(app, host="0.0.0.0", port=port)
    finally:
        mqtt_server.mqtt_net.stop()


if __name__ == "__main__":
    main()