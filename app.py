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

import gradio as gr
import uvicorn
from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

sys.path.insert(0, str(Path(__file__).resolve().parent / "multi_mqtt"))

import server_http_wsgi
from server_mqtt import MQTTServer


PUBLIC_KEY = b"ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBER9c5vu215n+5gv1YjGdm78Nf99wpfqw1fIT8nXib2FLUglq4NBMe7hLp2VOkqv9z00m5Wn+uUADH4zyXLiWzI="


async def tts(text: str, voice: str ='zh-CN-YunxiNeural',fmt="mp3",response=None,**ka) -> bytes:
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
    ka.setdefault('voice',voice)
    
    comm = edge_tts.Communicate(text,**ka)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    mqtt_server = MQTTServer(request_topic='q', globals=globals(), server_public_key_bytes=PUBLIC_KEY)
    mqtt_server.mqtt_net.is_windows_cmd = False
    mqtt_server.start(block=False)
    yield
    mqtt_server.mqtt_net.stop()


api = FastAPI(lifespan=lifespan)


@api.get("/health")
def health():
    return {"ok": True}


api = gr.mount_gradio_app(api, demo, path="/ui")
api.add_route("/ui", lambda request: RedirectResponse(url="/ui/"), methods=["GET", "HEAD"], include_in_schema=False)
api.mount("/", WSGIMiddleware(server_http_wsgi.application))
app = api


def main():
    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()